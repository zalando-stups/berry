#!/usr/bin/env python3

import boto.s3
import json
import logging
import os
import yaml


def main(args):
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
    s3 = boto.s3.connect_to_region()
    bucket = s3.get_bucket(mint_bucket)

    while True:

        # download credentials

        for fn in ('user', 'client'):
            try:
                local_file = os.path.join(local_directory, 'user.json')
                tmp_file = local_file + '.tmp'
                with open(tmp_file, 'wb') as fd:
                    key = bucket.get_key('/{}/{}.json'.format(application_id, fn))
                    key.get_contents_to_file(fd)
                    fd.seek(0)
                    data = json.load(fd)
                    os.rename(fd.name, local_file)
            except:
                logging.exception('Failed to download credentials')

        time.sleep(args.interval)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('local-directory')
    parser.add_argument('--application-id')
    parser.add_argument('--mint-bucket')
    parser.add_argument('-i', '--interval', help='Interval in seconds', default=120)
    args = parser.parse()

    logging.basicConfig(level=logging.WARN)
    main(args)

