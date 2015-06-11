
import boto
import boto.exception
import logging
import os
import pytest
import sys
import time

from berry.cli import *
from mock import MagicMock


def test_use_aws_credentials(tmpdir):
    p = tmpdir.join('aws-creds')
    p.write('# my comment\nsomeapp:foo:bar\nmyapp:abc123:456789\nblub:a:b')
    use_aws_credentials('myapp', str(p))

    assert 'abc123' == os.environ.get('AWS_ACCESS_KEY_ID')
    assert '456789' == os.environ.get('AWS_SECRET_ACCESS_KEY')


def test_rotate_credentials(monkeypatch, tmpdir, capsys):
    bucket = MagicMock()
    bucket.get_key.return_value.get_contents_as_string.return_value = b'{"application_username": "myteam_myapp", "application_password": "secret"}'

    s3 = MagicMock()
    s3.get_bucket.return_value = bucket
    monkeypatch.setattr('boto.connect_s3', lambda: s3)
    monkeypatch.setattr('time.sleep', lambda x: 0)

    args = MagicMock()
    args.application_id = 'myapp'
    args.config_file = str(tmpdir.join('taupage.yaml'))
    args.once = True
    args.aws_credentials_file = None
    args.local_directory = str(tmpdir.join('credentials'))

    os.makedirs(args.local_directory)

    logging.basicConfig(level=logging.INFO)
    run_berry(args)

    out, err = capsys.readouterr()
    assert 'Rotated user credentials for myapp' in err
    assert 'Rotated client credentials for myapp' in err

    # https://github.com/zalando-stups/berry/issues/4
    # check that we don't rotate/write the file if it wasn't changed
    run_berry(args)
    out, err = capsys.readouterr()
    assert 'Rotated' not in err


def test_main_noargs(monkeypatch):
    monkeypatch.setattr('sys.argv', ['berry'])
    try:
        main()
        assert False
    except SystemExit:
        pass


@pytest.mark.skipif(sys.version_info < (3, 0),
                    reason='fails with "ValueError: I/O operation on closed file" on Python 2.7')
def test_s3_error_message(monkeypatch, tmpdir, capsys):
    bucket = MagicMock()
    bucket.get_key.side_effect = boto.exception.S3ResponseError(403, 'Forbbiden', {'message': 'Access Denied'})

    s3 = MagicMock()
    s3.get_bucket.return_value = bucket
    monkeypatch.setattr('boto.connect_s3', lambda: s3)
    monkeypatch.setattr('time.sleep', lambda x: 0)

    args = MagicMock()
    args.application_id = 'myapp'
    args.config_file = str(tmpdir.join('taupage.yaml'))
    args.once = True
    args.aws_credentials_file = None
    args.local_directory = str(tmpdir.join('credentials'))
    args.mint_bucket = 'my-mint-bucket'

    os.makedirs(args.local_directory)

    logging.basicConfig(level=logging.INFO)
    run_berry(args)

    out, err = capsys.readouterr()
    assert 'Access denied while trying to read "myapp/client.json" from mint S3 bucket "my-mint-bucket"' in err

    bucket.get_key.side_effect = boto.exception.S3ResponseError(404, 'Not Found')
    run_berry(args)

    out, err = capsys.readouterr()
    assert 'Credentials file "myapp/client.json" not found in mint S3 bucket "my-mint-bucket"' in err

