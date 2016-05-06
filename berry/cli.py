#!/usr/bin/env python3

import argparse
import boto3.session
import botocore.exceptions
import json
import logging
import os
import yaml
import time
import dns.resolver
from botocore.client import Config


class UsageError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return 'Usage Error: {}'.format(self.msg)


def get_bucket_region(client, bucket_name, endpoint):
    try:
        return client.get_bucket_location(Bucket=bucket_name).get('LocationConstraint')
    except botocore.exceptions.ClientError as e:
        if e.response['Error'].get('Code') != 'AccessDenied':
            logging.error('Unkown Error on get_bucket_location({})! (S3 error message: {})'.format(bucket_name, e))
    if endpoint.endswith('.amazonaws.com'):
        endpoint_parts = endpoint.split('.')
        if endpoint_parts[-3].startswith('s3-'):
            return endpoint_parts[-3].replace('s3-', '')
    bucket_dns = '{}.s3.amazonaws.com'.format(bucket_name)
    try:
        answers = dns.resolver.query(bucket_dns, 'CNAME')
        if len(answers) == 1:
            answer = answers[0]
            if (len(answer.target) == 5 and
                    str(answer.target).endswith('.amazonaws.com.') and
                    str(answer.target).startswith('s3')):
                return answer.target.labels[1].decode()
            if (len(answer.target) == 4 and
                    str(answer.target).endswith('.amazonaws.com.') and
                    str(answer.target).startswith('s3-')):
                return answer.target.labels[0].decode().replace('s3-', '')
            logging.error('Unsupportet DNS response for {}: {}'.format(bucket_dns, answer))
        logging.error('Two many entrys ({}) for DNS Name {}'.format(len(answers), bucket_dns))
    except Exception as e:
        logging.exception('Unsupportet Exception: {}'.format(e))
    return None


def lookup_aws_credentials(application_id, path):
    with open(path) as fd:
        for line in fd:
            line = line.strip()
            if not line.startswith('#'):
                parts = line.split(':')
                if parts[0] == application_id:
                    return parts[1], parts[2]
    return None, None


def use_aws_credentials(application_id, path):
    access_key_id, secret_access_key = lookup_aws_credentials(application_id, path)
    if not access_key_id:
        raise UsageError('No AWS credentials found for application "{}" in {}'.format(application_id, path))
    return {'aws_access_key_id': access_key_id, 'aws_secret_access_key': secret_access_key}


def run_berry(args):
    try:
        with open(args.config_file) as fd:
            config = yaml.load(fd)
    except Exception as e:
        logging.warn('Could not load configuration from {}: {}'.format(args.config_file, e))
        config = {}

    application_id = args.application_id or config.get('application_id')
    mint_bucket = args.mint_bucket or config.get('mint_bucket')
    local_directory = args.local_directory

    if not application_id:
        raise UsageError('Application ID missing, please set "application_id" in your configuration YAML')

    if not mint_bucket:
        raise UsageError('Mint Bucket is not configured, please set "mint_bucket" in your configuration YAML')

    if args.aws_credentials_file:
        aws_credentials = use_aws_credentials(application_id, args.aws_credentials_file)
    else:
        aws_credentials = {}

    session = boto3.session.Session(**aws_credentials)
    s3 = session.client('s3')
    while True:
        for fn in ['user', 'client']:
            key_name = '{}/{}.json'.format(application_id, fn)
            try:
                local_file = os.path.join(local_directory, '{}.json'.format(fn))
                tmp_file = local_file + '.tmp'
                response = None
                retry = 3
                while retry:
                    try:
                        response = s3.get_object(Bucket=mint_bucket, Key=key_name)
                        retry = False
                    except botocore.exceptions.ClientError as e:
                        # more friendly error messages
                        # https://github.com/zalando-stups/berry/issues/2
                        status_code = e.response.get('ResponseMetadata', {}).get('HTTPStatusCode')
                        msg = e.response['Error'].get('Message')
                        error_code = e.response['Error'].get('Code')
                        endpoint = e.response['Error'].get('Endpoint', '')
                        retry -= 1
                        if error_code == 'InvalidRequest' and 'Please use AWS4-HMAC-SHA256.' in msg:
                            logging.debug(('Invalid Request while trying to read "{}" from mint S3 bucket "{}". ' +
                                           'Retrying with signature version v4! ' +
                                           '(S3 error message: {})').format(
                                         key_name, mint_bucket, msg))
                            s3 = session.client('s3', config=Config(signature_version='s3v4'))
                        elif error_code == 'PermanentRedirect' and endpoint.endswith('.amazonaws.com'):
                            region = get_bucket_region(s3, mint_bucket, endpoint)
                            logging.debug(('Got Redirect while trying to read "{}" from mint S3 bucket "{}". ' +
                                           'Retrying with region {}, endpoint {}! ' +
                                           '(S3 error message: {})').format(
                                         key_name, mint_bucket, region, endpoint, msg))
                            s3 = session.client('s3', region)
                        elif status_code == 403:
                            logging.error(('Access denied while trying to read "{}" from mint S3 bucket "{}". ' +
                                           'Check your IAM role/user policy to allow read access! ' +
                                           '(S3 error message: {})').format(
                                          key_name, mint_bucket, msg))
                            retry = False
                        elif status_code == 404:
                            logging.error(('Credentials file "{}" not found in mint S3 bucket "{}". ' +
                                           'Mint either did not sync them yet or the mint configuration is wrong. ' +
                                           '(S3 error message: {})').format(
                                          key_name, mint_bucket, msg))
                            retry = False
                        else:
                            logging.error('Could not read from mint S3 bucket "{}": {}'.format(
                                          mint_bucket, e))
                            retry = False

                if response:
                    body = response['Body']
                    json_data = body.read()

                    # check that the file contains valid JSON
                    new_data = json.loads(json_data.decode('utf-8'))

                    try:
                        with open(local_file, 'r') as fd:
                            old_data = json.load(fd)
                    except:
                        old_data = None
                    # check whether the file contents changed
                    if new_data != old_data:
                        with open(tmp_file, 'wb') as fd:
                            fd.write(json_data)
                        os.rename(tmp_file, local_file)
                        logging.info('Rotated {} credentials for {}'.format(fn, application_id))
            except:
                logging.exception('Failed to download {} credentials'.format(fn))

        if args.once:
            break

        time.sleep(args.interval)  # pragma: no cover


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('local_directory', help='Local directory to write credentials to')
    parser.add_argument('-f', '--config-file', help='Read berry settings from given YAML file',
                        default='/etc/taupage.yaml')
    parser.add_argument('-a', '--application-id', help='Application ID as registered in Kio')
    parser.add_argument('-m', '--mint-bucket', help='Mint S3 bucket name')
    parser.add_argument('-c', '--aws-credentials-file',
                        help='Lookup AWS credentials by application ID in the given file')
    parser.add_argument('-i', '--interval', help='Interval in seconds', default=120)
    parser.add_argument('--once', help='Download credentials once and exit', action='store_true')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    # do not log new HTTPS connections (INFO level):
    logging.getLogger('botocore.vendored.requests').setLevel(logging.WARN)
    try:
        run_berry(args)
    except UsageError as e:
        logging.error(str(e))

if __name__ == '__main__':
    main()
