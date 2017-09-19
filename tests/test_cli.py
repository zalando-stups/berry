
import botocore.exceptions
import logging
import os
import pytest
import yaml
import dns

from berry.cli import use_aws_credentials, run_berry, main, UsageError
import berry.cli
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
    monkeypatch.setattr('boto3.session.Session', mock_session(s3))
    monkeypatch.setattr('time.sleep', lambda x: 0)

    args = MagicMock()
    args.application_id = 'myapp'
    args.config_file = str(tmpdir.join('taupage.yaml'))
    args.once = True
    args.aws_credentials_file = None
    args.local_directory = str(tmpdir.join('credentials'))

    os.makedirs(args.local_directory)

    logging.basicConfig(level=logging.INFO)
    assert run_berry(args) is True
    out, err = capsys.readouterr()
    assert 'Rotated user credentials for myapp' in err
    assert 'Rotated client credentials for myapp' in err

    # https://github.com/zalando-stups/berry/issues/4
    # check that we don't rotate/write the file if it wasn't changed
    assert run_berry(args) is True
    out, err = capsys.readouterr()
    assert 'Rotated' not in err


def test_rotate_credentials_with_file_config(monkeypatch, tmpdir):
    response = MagicMock()
    response['Body'].read.return_value = b'{"application_username": "myteam_myapp", "application_password": "secret"}'

    s3 = MagicMock()
    s3.get_object.return_value = response
    monkeypatch.setattr('boto3.session.Session', mock_session(s3))
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

    assert run_berry(args) is True
    log_info.assert_called_with('Rotated client credentials for someapp')

    args.application_id = 'wrongapp'
    with pytest.raises(UsageError) as excinfo:
        assert run_berry(args) is False
    assert 'No AWS credentials found for application "wrongapp" in' in excinfo.value.msg


def test_main_noargs(monkeypatch):
    monkeypatch.setattr('sys.argv', ['berry'])
    try:
        main()
        assert False
    except SystemExit:
        pass


def test_run_berry_status(monkeypatch):
    orig_run_berry = berry.cli.run_berry
    orig_configure = berry.cli.configure
    try:
        args = {11: 22}
        berry.cli.run_berry = MagicMock()
        berry.cli.configure = lambda: args

        berry.cli.run_berry.return_value = False
        assert main() == 1

        berry.cli.run_berry.assert_called_with(args)

        berry.cli.run_berry.return_value = True
        assert main() == 0
    finally:
        berry.cli.run_berry = orig_run_berry
        berry.cli.configure = orig_configure


def test_main_missingargs(monkeypatch):
    monkeypatch.setattr('sys.argv', ['berry', './'])
    log_error = MagicMock()
    monkeypatch.setattr('logging.warn', MagicMock())
    monkeypatch.setattr('logging.error', log_error)
    main()
    log_error.assert_called_with(
        ('Usage Error: Application ID missing, please set "application_id" in your '
         'configuration YAML')
    )
    args = MagicMock()
    args.config_file = None
    args.application_id = 'myapp'
    args.aws_credentials_file = None
    args.mint_bucket = None

    with pytest.raises(UsageError) as excinfo:
        assert run_berry(args) is False
        assert ('Usage Error: Mint Bucket is not configured, please set "mint_bucket" in '
                'your configuration YAML') in str(excinfo.value)


def test_s3_error_message(monkeypatch, tmpdir):
    log_error = MagicMock()
    log_info = MagicMock()
    log_debug = MagicMock()
    monkeypatch.setattr('logging.warn', MagicMock())
    monkeypatch.setattr('logging.error', log_error)
    monkeypatch.setattr('logging.info', log_info)
    monkeypatch.setattr('logging.debug', log_debug)

    s3 = MagicMock()
    s3.get_object.side_effect = botocore.exceptions.ClientError(
        {'ResponseMetadata': {'HTTPStatusCode': 403},
         'Error': {'Message': 'Access Denied'}}, 'get_object')
    monkeypatch.setattr('boto3.session.Session', mock_session(s3))
    monkeypatch.setattr('time.sleep', lambda x: 0)

    dns_resolver = MagicMock()
    monkeypatch.setattr('dns.resolver.query', dns_resolver)

    args = MagicMock()
    args.application_id = 'myapp'
    args.config_file = str(tmpdir.join('taupage.yaml'))
    args.once = True
    args.aws_credentials_file = None
    args.mint_bucket = 'my-mint-bucket'
    args.local_directory = str(tmpdir.join('credentials'))

    os.makedirs(args.local_directory)

    logging.basicConfig(level=logging.INFO)

    assert run_berry(args) is False
    log_error.assert_called_with(
        ('Access denied while trying to read "myapp/client.json" from mint S3 bucket '
         '"my-mint-bucket". Check your IAM role/user policy to allow read access! '
         '(S3 error message: Access Denied)'))

    s3.get_object.side_effect = botocore.exceptions.ClientError(
        {'ResponseMetadata': {'HTTPStatusCode': 404},
         'Error': {}}, 'get_object')
    assert run_berry(args) is False
    log_error.assert_called_with(
        'Credentials file "myapp/client.json" not found in mint S3 bucket "my-mint-bucket". '
        'Mint either did not sync them yet or the mint configuration is wrong. (S3 error message: None)')

    s3.get_object.side_effect = botocore.exceptions.ClientError(
        {'Error': {'Bucket': 'my-mint-bucket',
                   'Code': 'PermanentRedirect',
                   'Endpoint': 'my-mint-bucket.s3-eu-foobar-1.amazonaws.com',
                   'Message': 'The bucket you are attempting to access must be '
                              'addressed using the specified endpoint. Please send '
                              'all future requests to this endpoint.'},
         'ResponseMetadata': {'HTTPStatusCode': 301,
                              'HostId': '',
                              'RequestId': ''}}, 'get_object')
    s3.get_bucket_location.return_value = {'LocationConstraint': 'eu-foobar-1'}
    assert run_berry(args) is True
    log_debug.assert_called_with(
        ('Got Redirect while trying to read "myapp/client.json" from mint S3 bucket '
         '"my-mint-bucket". Retrying with region eu-foobar-1, endpoint '
         'my-mint-bucket.s3-eu-foobar-1.amazonaws.com! (S3 error message: The bucket '
         'you are attempting to access must be addressed using the specified '
         'endpoint. Please send all future requests to this endpoint.)'))

    s3.get_object.side_effect = botocore.exceptions.ClientError(
        {'Error': {'Bucket': 'my-mint-bucket',
                   'Code': 'PermanentRedirect',
                   'Endpoint': 'my-mint-bucket.s3-eu-foobar-1.amazonaws.com',
                   'Message': 'The bucket you are attempting to access must be '
                              'addressed using the specified endpoint. Please send '
                              'all future requests to this endpoint.'},
         'ResponseMetadata': {'HTTPStatusCode': 301,
                              'HostId': '',
                              'RequestId': ''}}, 'get_object')
    s3.get_bucket_location.side_effect = botocore.exceptions.ClientError(
        {'Error': {'Code': 'UnknownError',
                   'Message': 'Unknown Error, only for Test'},
         'ResponseMetadata': {'HTTPStatusCode': 403,
                              'HostId': '',
                              'RequestId': ''}}, 'get_bucket_location')
    assert run_berry(args) is True
    log_debug.assert_called_with(
        ('Got Redirect while trying to read "myapp/client.json" from mint S3 bucket '
         '"my-mint-bucket". Retrying with region eu-foobar-1, endpoint '
         'my-mint-bucket.s3-eu-foobar-1.amazonaws.com! (S3 error message: The bucket '
         'you are attempting to access must be addressed using the specified '
         'endpoint. Please send all future requests to this endpoint.)'))

    s3.get_object.side_effect = botocore.exceptions.ClientError(
        {'Error': {'Bucket': 'my-mint-bucket',
                   'Code': 'PermanentRedirect',
                   'Endpoint': 'my-mint-bucket.s3.amazonaws.com',
                   'Message': 'The bucket you are attempting to access must be '
                              'addressed using the specified endpoint. Please send '
                              'all future requests to this endpoint.'},
         'ResponseMetadata': {'HTTPStatusCode': 301,
                              'HostId': '',
                              'RequestId': ''}}, 'get_object')
    s3.get_bucket_location.side_effect = botocore.exceptions.ClientError(
        {'Error': {'Code': 'UnknownError',
                   'Message': 'Unknown Error, only for Test'},
         'ResponseMetadata': {'HTTPStatusCode': 403,
                              'HostId': '',
                              'RequestId': ''}}, 'get_bucket_location')
    message_text = """id 1234
opcode QUERY
rcode NOERROR
flags QR AA RD
;QUESTION
my-mint-bucket.s3.amazonaws.com. IN CNAME
;ANSWER
my-mint-bucket.s3.amazonaws.com. 1 IN CNAME s3.eu-foobar-1.amazonaws.com.
;AUTHORITY
;ADDITIONAL
"""
    dns_resolver.return_value = (dns.resolver.Answer(
        dns.name.from_text('my-mint-bucket.s3.amazonaws.com.'),
        dns.rdatatype.CNAME,
        dns.rdataclass.IN,
        dns.message.from_text(message_text)))
    assert run_berry(args) is True
    log_debug.assert_called_with(
        ('Got Redirect while trying to read "myapp/client.json" from mint S3 bucket '
         '"my-mint-bucket". Retrying with region eu-foobar-1, endpoint '
         'my-mint-bucket.s3.amazonaws.com! (S3 error message: The bucket you are '
         'attempting to access must be addressed using the specified endpoint. '
         'Please send all future requests to this endpoint.)'))

    message_text = """id 1234
opcode QUERY
rcode NOERROR
flags QR AA RD
;QUESTION
my-mint-bucket.s3.amazonaws.com. IN CNAME
;ANSWER
my-mint-bucket.s3.amazonaws.com. 1 IN CNAME s3-eu-foobar-1.amazonaws.com.
;AUTHORITY
;ADDITIONAL
"""
    dns_resolver.return_value = (dns.resolver.Answer(
        dns.name.from_text('my-mint-bucket.s3.amazonaws.com.'),
        dns.rdatatype.CNAME,
        dns.rdataclass.IN,
        dns.message.from_text(message_text)))
    assert run_berry(args) is True
    log_debug.assert_called_with(
        ('Got Redirect while trying to read "myapp/client.json" from mint S3 bucket '
         '"my-mint-bucket". Retrying with region eu-foobar-1, endpoint '
         'my-mint-bucket.s3.amazonaws.com! (S3 error message: The bucket you are '
         'attempting to access must be addressed using the specified endpoint. '
         'Please send all future requests to this endpoint.)'))

    message_text = """id 1234
opcode QUERY
rcode NOERROR
flags QR AA RD
;QUESTION
my-mint-bucket.s3.amazonaws.com. IN CNAME
;ANSWER
my-mint-bucket.s3.amazonaws.com. 1 IN CNAME s3.amazonaws.com.
;AUTHORITY
;ADDITIONAL
"""
    dns_resolver.return_value = (dns.resolver.Answer(
        dns.name.from_text('my-mint-bucket.s3.amazonaws.com.'),
        dns.rdatatype.CNAME,
        dns.rdataclass.IN,
        dns.message.from_text(message_text)))
    assert run_berry(args) is True
    log_debug.assert_called_with(
        ('Got Redirect while trying to read "myapp/client.json" from mint S3 bucket '
         '"my-mint-bucket". Retrying with region None, endpoint '
         'my-mint-bucket.s3.amazonaws.com! (S3 error message: The bucket you are '
         'attempting to access must be addressed using the specified endpoint. '
         'Please send all future requests to this endpoint.)'))

    dns_resolver.side_effect = dns.resolver.NXDOMAIN
    assert run_berry(args) is True
    log_debug.assert_called_with(
        ('Got Redirect while trying to read "myapp/client.json" from mint S3 bucket '
         '"my-mint-bucket". Retrying with region None, endpoint '
         'my-mint-bucket.s3.amazonaws.com! (S3 error message: The bucket you are '
         'attempting to access must be addressed using the specified endpoint. '
         'Please send all future requests to this endpoint.)'))

    s3.get_object.side_effect = botocore.exceptions.ClientError(
        {'Error': {'Code': 'InvalidRequest',
                   'Message': 'The authorization mechanism you have provided is not '
                              'supported. Please use AWS4-HMAC-SHA256.'},
         'ResponseMetadata': {'HTTPStatusCode': 400,
                              'HostId': '',
                              'RequestId': ''}}, 'get_object')
    assert run_berry(args) is True
    log_debug.assert_called_with(
        ('Invalid Request while trying to read "myapp/client.json" from mint S3 '
         'bucket "my-mint-bucket". Retrying with signature version v4! (S3 error '
         'message: The authorization mechanism you have provided is not supported. '
         'Please use AWS4-HMAC-SHA256.)'))

    # generic ClientError
    s3.get_object.side_effect = botocore.exceptions.ClientError(
        {'ResponseMetadata': {'HTTPStatusCode': 999}, 'Error': {}}, 'get_object')
    assert run_berry(args) is False
    log_error.assert_called_with(
        ('Could not read from mint S3 bucket "my-mint-bucket": An error occurred '
         '(Unknown) when calling the get_object operation: Unknown'))

    # generic Exception
    s3.get_object.side_effect = Exception('foobar')
    assert run_berry(args) is False
    log_error.assert_called_with('Failed to download client credentials', exc_info=True)
