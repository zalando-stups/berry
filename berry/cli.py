#!/usr/bin/env python3

import argparse
import boto.s3
import boto.utils
import json
import logging
import os
import yaml
import time


class UsageError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return 'Usage Error: {}'.format(self.msg)


def get_region():
    identity = boto.utils.get_instance_identity()['document']
    return identity['region']


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
    os.environ['AWS_ACCESS_KEY_ID'] = access_key_id
    os.environ['AWS_SECRET_ACCESS_KEY'] = secret_access_key


def run_berry(args):
    try:
        with open('/etc/taupage.yaml') as fd:
            config = yaml.load(fd)
    except Exception as e:
        logging.warn('Could not load configuration from taupage.yaml: {}'.format(e))
        config = {}

    application_id = args.application_id or config.get('application_id')
    mint_bucket = args.mint_bucket or config.get('mint_bucket')
    local_directory = args.local_directory

    if not application_id:
        raise UsageError('Application ID missing, please set "application_id" in your Taupage user data YAML')

    if not mint_bucket:
        raise UsageError('Mint Bucket is not configured, please set "mint_bucket" in your Taupage user data YAML')

    if args.aws_credentials_file:
        use_aws_credentials(application_id, args.aws_credentials_file)

    # region?
    s3 = boto.s3.connect_to_region(args.region or os.environ.get('AWS_DEFAULT_REGION') or get_region())

    if not s3:
        raise Exception('Could not connect to S3')

    bucket = s3.get_bucket(mint_bucket, validate=False)

    while True:

        # download credentials

        for fn in ['user', 'client']:
            try:
                local_file = os.path.join(local_directory, '{}.json'.format(fn))
                tmp_file = local_file + '.tmp'
                key = bucket.get_key('{}/{}.json'.format(application_id, fn), validate=False)
                json_data = key.get_contents_as_string()
                # check that the file contains valid JSON
                new_data = json.loads(json_data.decode('utf-8'))

                try:
                    with open(local_file, 'rb') as fd:
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

        time.sleep(args.interval)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('local_directory', help='Local directory to write credentials to')
    parser.add_argument('-a', '--application-id', help='Application ID as registered in Kio')
    parser.add_argument('-m', '--mint-bucket', help='Mint S3 bucket name')
    parser.add_argument('--region', help='AWS region ID')
    parser.add_argument('-c', '--aws-credentials-file',
                        help='Lookup AWS credentials by application ID in the given file')
    parser.add_argument('-i', '--interval', help='Interval in seconds', default=120)
    parser.add_argument('--once', help='Download credentials once and exit', action='store_true')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    try:
        run_berry(args)
    except UsageError as e:
        logging.error(e)

if __name__ == '__main__':
    main()
