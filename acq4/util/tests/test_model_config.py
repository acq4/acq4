"""Tests for the single accessor to the rig's configured cellpose checkpoint.

Detection and tracking have to segment with the same model. Tracking had no way
to name one, so it silently ran stock cpsam, which finds nothing on this rig's
DIC crops.
"""

from acq4.util.model_config import segmenter_path


class _Manager:
    def __init__(self, config):
        self.config = config


def test_the_path_comes_from_the_misc_config():
    manager = _Manager({"misc": {"segmenterPath": "/models/tuned"}})
    assert segmenter_path(manager) == "/models/tuned"


def test_an_unconfigured_rig_leaves_cellpose_on_its_stock_model():
    assert segmenter_path(_Manager({"misc": {}})) is None
    assert segmenter_path(_Manager({})) is None


def test_no_manager_is_not_an_error():
    """A headless or partially-configured rig must not raise here, the same way
    detect_neurons accepts None for every model."""
    assert segmenter_path(None) is None


def test_the_running_manager_is_the_default(monkeypatch):
    from acq4.Manager import Manager

    monkeypatch.setattr(
        Manager,
        "single",
        _Manager({"misc": {"segmenterPath": "/models/from-manager"}}),
        raising=False,
    )
    assert segmenter_path() == "/models/from-manager"


def test_no_manager_running_is_not_an_error(monkeypatch):
    from acq4.Manager import Manager

    monkeypatch.setattr(Manager, "single", None, raising=False)
    assert segmenter_path() is None
