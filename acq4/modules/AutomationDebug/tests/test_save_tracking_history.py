# Tests for Autopatcher._saveTrackingHistory — saving cell tracker history to cell_dir.
from unittest.mock import MagicMock, patch
import pytest

from acq4.modules.AutomationDebug.autopatch import Autopatcher


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
            cell._tracker, "tracking_history", fileType="AcqTrackFile"
        )

    def test_logs_and_continues_on_save_error(self, autopatcher, cell_dir, caplog):
        cell = _make_cell()
        cell_dir.writeFile.side_effect = OSError("disk full")
        import logging
        with caplog.at_level(logging.ERROR):
            autopatcher._saveTrackingHistory(cell, cell_dir)
        assert any("tracking history" in r.message.lower() for r in caplog.records)
