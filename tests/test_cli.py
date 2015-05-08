
from berry.cli import *
from mock import MagicMock

def test_get_region(monkeypatch):
    r = MagicMock(text='test1a')
    monkeypatch.setattr('requests.get', MagicMock(return_value=r))
    assert 'test1' == get_region()
