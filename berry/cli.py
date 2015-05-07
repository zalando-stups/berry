#!/usr/bin/env python3

import argparse
import boto.s3
import json
import logging
import os
import yaml
import requests
import string
import time


def get_region():
    r = requests.get('http://169.254.169.254/latest/meta-data/placement/availability-zone')
    az = r.text
    return az.rstrip(string.ascii_lowercase)


def run_berry(args):
    try:
        with open('/etc/zalando.yaml') as fd:
            config = yaml.load(fd)
    except Exception as e:
        logging.warn('Could not load configuration from zalando.yaml: {}'.format(e))
        config = {}

    application_id = args.application_id or config['application_id']
    mint_bucket = args.mint_bucket or config['mint_bucket']
    local_directory = args.local_directory

    # region?
    s3 = boto.s3.connect_to_region(args.region or os.environ.get('AWS_DEFAULT_REGION') or get_region())

    if not s3:
        raise Exception('Could not connect to S3')

    bucket = s3.get_bucket(mint_bucket)

    while True:

        # download credentials

        for fn in ['user', 'client']:
            try:
                local_file = os.path.join(local_directory, '{}.json'.format(fn))
                tmp_file = local_file + '.tmp'
                key = bucket.get_key('{}/{}.json'.format(application_id, fn), validate=False)
                json_data = key.get_contents_as_string()
                # check that the file contains valid JSON
                json.loads(json_data.decode('utf-8'))
                # TODO: check whether the file contents changed
                with open(tmp_file, 'wb') as fd:
                    fd.write(json_data)
                os.rename(tmp_file, local_file)
            except:
                logging.exception('Failed to download credentials')

        time.sleep(args.interval)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('local_directory')
    parser.add_argument('--application-id')
    parser.add_argument('--mint-bucket')
    parser.add_argument('--region')
    parser.add_argument('-i', '--interval', help='Interval in seconds', default=120)
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARN)
    run_berry(args)

if __name__ == '__main__':
    main()
