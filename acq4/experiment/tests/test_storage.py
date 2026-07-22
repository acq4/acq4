"""Registration test for storage Actions (behavior needs a managed data tree,
so it is verified live rather than headlessly)."""
from acq4.experiment.actions.storage import NewDataDirAction
from acq4.experiment.registry import get_action_class


def test_newdatadir_registered():
    assert get_action_class("NewDataDir") is NewDataDirAction
    assert NewDataDirAction.outcomes == ("created",)
