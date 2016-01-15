
import botocore.exceptions
import logging
import os
import pytest
import yaml

from berry.cli import use_aws_credentials, run_berry, main, UsageError
from mock import MagicMock


def test_use_aws_credentials(tmpdir):
    p = tmpdir.join('aws-creds')
    p.write('# my comment\nsomeapp:foo:bar\nmyapp:abc123:456789\nblub:a:b')
    creds = use_aws_credentials('myapp', str(p))

    assert creds == {'aws_access_key_id': 'abc123', 'aws_secret_access_key': '456789'}


def mock_session(client):
    session = MagicMock()
    session.client.return_value = client
    return lambda **kwargs: session


def test_rotate_credentials(monkeypatch, tmpdir, capsys):
    response = MagicMock()
    response['Body'].read.return_value = b'{"application_username": "myteam_myapp", "application_password": "secret"}'

    s3 = MagicMock()
    s3.get_object.return_value = response
    monkeypatch.setattr('boto3.Session', mock_session(s3))
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


def test_rotate_credentials_with_file_config(monkeypatch, tmpdir):
    response = MagicMock()
    response['Body'].read.return_value = b'{"application_username": "myteam_myapp", "application_password": "secret"}'

    s3 = MagicMock()
    s3.get_object.return_value = response
    monkeypatch.setattr('boto3.Session', mock_session(s3))
    monkeypatch.setattr('time.sleep', lambda x: 0)

    log_info = MagicMock()
    monkeypatch.setattr('logging.warn', MagicMock())
    monkeypatch.setattr('logging.info', log_info)

    config_path = str(tmpdir.join('taupage.yaml'))
    with open(config_path, 'w') as fd:
        yaml.safe_dump({'application_id': 'someapp'}, fd)

    credentials_path = str(tmpdir.join('credentials'))
    with open(credentials_path, 'w') as fd:
        fd.write('someapp:foo:bar')

    args = MagicMock()
    args.application_id = None
    args.config_file = config_path
    args.once = True
    args.aws_credentials_file = credentials_path
    args.local_directory = str(tmpdir.join('out'))

    os.makedirs(args.local_directory)

    run_berry(args)
    log_info.assert_called_with('Rotated client credentials for someapp')

    args.application_id = 'wrongapp'
    with pytest.raises(UsageError) as excinfo:
        run_berry(args)
    assert 'No AWS credentials found for application "wrongapp" in' in excinfo.value.msg


def test_main_noargs(monkeypatch):
    monkeypatch.setattr('sys.argv', ['berry'])
    try:
        main()
        assert False
    except SystemExit:
        pass


def test_main_missingargs(monkeypatch):
    monkeypatch.setattr('sys.argv', ['berry', './'])
    log_error = MagicMock()
    monkeypatch.setattr('logging.warn', MagicMock())
    monkeypatch.setattr('logging.error', log_error)
    main()
    log_error.assert_called_with('Usage Error: Application ID missing, please set "application_id" in your configuration YAML')


def test_s3_error_message(monkeypatch, tmpdir):
    log_error = MagicMock()
    monkeypatch.setattr('logging.warn', MagicMock())
    monkeypatch.setattr('logging.error', log_error)

    s3 = MagicMock()
    s3.get_object.side_effect = botocore.exceptions.ClientError({'ResponseMetadata': {'HTTPStatusCode': 403}, 'Error': {'Message': 'Access Denied'}}, 'get_object')
    monkeypatch.setattr('boto3.Session', mock_session(s3))
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

    log_error.assert_called_with('Access denied while trying to read "myapp/client.json" from mint S3 bucket "my-mint-bucket". Check your IAM role/user policy to allow read access! (S3 error message: Access Denied)')

    s3.get_object.side_effect = botocore.exceptions.ClientError({'ResponseMetadata': {'HTTPStatusCode': 404}, 'Error': {}}, 'get_object')
    run_berry(args)

    log_error.assert_called_with('Credentials file "myapp/client.json" not found in mint S3 bucket "my-mint-bucket". Mint either did not sync them yet or the mint configuration is wrong. (S3 error message: None)')

    # generic ClientError
    s3.get_object.side_effect = botocore.exceptions.ClientError({'ResponseMetadata': {'HTTPStatusCode': 999}, 'Error': {}}, 'get_object')
    run_berry(args)
    log_error.assert_called_with('Could not read from mint S3 bucket "my-mint-bucket": An error occurred (Unknown) when calling the get_object operation: Unknown')

    # generic Exception
    s3.get_object.side_effect = Exception('foobar')
    run_berry(args)
    log_error.assert_called_with('Failed to download client credentials', exc_info=True)
