# Tests for saving cell tracker history, both to a demo's cell_dir and to the
# current storage directory via the "save last tracking log" button.
from unittest.mock import MagicMock, patch
import pytest

from acq4.modules.AutomationDebug.autopatch import Autopatcher
from acq4.modules.AutomationDebug.feature_tracking import FeatureTracker


@pytest.fixture
def autopatcher():
    win = MagicMock()
    return Autopatcher(win)


@pytest.fixture
def cell_dir(tmp_path):
    d = tmp_path / "Cell_001"
    d.mkdir()
    mock = MagicMock()
    mock.name.return_value = str(d)
    return mock


def _make_cell(tracking_results=None):
    cell = MagicMock()
    cell._tracker = MagicMock()
    cell._tracker.tracking_results = tracking_results if tracking_results is not None else [MagicMock()]
    return cell


class TestSaveTrackingHistory:
    def test_skips_when_cell_is_none(self, autopatcher, cell_dir):
        autopatcher._saveTrackingHistory(None, cell_dir)
        cell_dir.writeFile.assert_not_called()

    def test_skips_when_tracker_is_none(self, autopatcher, cell_dir):
        cell = MagicMock()
        cell._tracker = None
        autopatcher._saveTrackingHistory(cell, cell_dir)
        cell_dir.writeFile.assert_not_called()

    def test_skips_when_no_tracking_results(self, autopatcher, cell_dir):
        cell = _make_cell(tracking_results=[])
        autopatcher._saveTrackingHistory(cell, cell_dir)
        cell_dir.writeFile.assert_not_called()

    def test_saves_to_cell_dir(self, autopatcher, cell_dir, tmp_path):
        """Write through the DirHandle, not with a raw path: writeFile is what indexes
        the file's type and emits the 'children' change that refreshes the file tree."""
        cell = _make_cell()
        autopatcher._saveTrackingHistory(cell, cell_dir)
        cell_dir.writeFile.assert_called_once_with(
            cell._tracker, "tracking_history", fileType="AcqTrackFile", autoIncrement=False
        )

    def test_logs_and_continues_on_save_error(self, autopatcher, cell_dir, caplog):
        cell = _make_cell()
        cell_dir.writeFile.side_effect = OSError("disk full")
        import logging
        with caplog.at_level(logging.ERROR):
            autopatcher._saveTrackingHistory(cell, cell_dir)
        assert any("tracking history" in r.message.lower() for r in caplog.records)


@pytest.fixture
def tracker(cell_dir):
    """A FeatureTracker whose manager reports cell_dir as the current directory."""
    win = MagicMock()
    win.patchPipetteDevice = None
    win._cell = None
    ft = FeatureTracker(win)
    with patch(
        "acq4.modules.AutomationDebug.feature_tracking.getManager"
    ) as getManager:
        getManager.return_value.getCurrentDir.return_value = cell_dir
        yield ft


class TestSaveLastTrackingLog:
    def test_saves_the_patch_pipette_cell(self, tracker, cell_dir):
        cell = _make_cell()
        tracker._window.patchPipetteDevice = MagicMock(cell=cell)
        tracker._saveLastTrackingLog()
        cell_dir.writeFile.assert_called_once_with(
            cell._tracker, "tracking_history", fileType="AcqTrackFile", autoIncrement=True
        )

    def test_falls_back_to_the_windows_cell(self, tracker, cell_dir):
        """Standalone tracking runs stash their cell on the window, not on a patch
        pipette; the button has to save those too."""
        cell = _make_cell()
        tracker._window.patchPipetteDevice = MagicMock(cell=None)
        tracker._window._cell = cell
        tracker._saveLastTrackingLog()
        cell_dir.writeFile.assert_called_once_with(
            cell._tracker, "tracking_history", fileType="AcqTrackFile", autoIncrement=True
        )

    def test_tolerates_no_patch_pipette(self, tracker, cell_dir):
        cell = _make_cell()
        tracker._window._cell = cell
        tracker._saveLastTrackingLog()
        assert cell_dir.writeFile.call_count == 1

    def test_logs_when_there_is_nothing_to_save(self, tracker, cell_dir, caplog):
        import logging
        with caplog.at_level(logging.ERROR):
            tracker._saveLastTrackingLog()
        cell_dir.writeFile.assert_not_called()
        assert any("no cell" in r.message.lower() for r in caplog.records)
