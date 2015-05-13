
from berry.cli import *
from mock import MagicMock

def test_get_region(monkeypatch):
    monkeypatch.setattr('boto.utils.get_instance_identity', lambda: {'document': {'region': 'test1'}})
    assert 'test1' == get_region()
