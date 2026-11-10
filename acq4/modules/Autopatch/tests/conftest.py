import pytest

import acq4.util.DataManager as dm

from .fakes import FakeManager


@pytest.fixture(autouse=True)
def fakeManager(monkeypatch, tmp_path):
    """A FakeManager installed as getManager() for each test, storing data under tmp_path/storage."""
    manager = FakeManager(dm.getDirHandle(str(tmp_path / "storage"), create=True))
    monkeypatch.setattr("acq4.Manager.Manager.single", manager, raising=False)
    return manager
