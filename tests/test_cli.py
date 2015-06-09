
import os

from berry.cli import *
from mock import MagicMock


def test_use_aws_credentials(tmpdir):
    p = tmpdir.join('aws-creds')
    p.write('# my comment\nsomeapp:foo:bar\nmyapp:abc123:456789\nblub:a:b')
    use_aws_credentials('myapp', str(p))

    assert 'abc123' == os.environ.get('AWS_ACCESS_KEY_ID')
    assert '456789' == os.environ.get('AWS_SECRET_ACCESS_KEY')
