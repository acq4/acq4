# Tests for saving cell tracker history, both to a demo's cell_dir and to the
# current storage directory via the "save last tracking log" button.
from unittest.mock import MagicMock, patch
import pytest

from acq4.modules.AutomationDebug.autopatch import Autopatcher
from acq4.modules.AutomationDebug.feature_tracking import FeatureTracker
from acq4.util.task import Stopped


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


def _make_cell(tracking_results=None, object_stacks=None):
    """A cell whose tracker holds the two things save_history writes.

    Both are spelled out rather than left to MagicMock's auto-attributes,
    because "the tracker holds nothing at all" is a case the save has to
    distinguish and an auto-attribute is never empty.
    """
    cell = MagicMock()
    cell._tracker = MagicMock()
    cell._tracker.tracking_results = tracking_results if tracking_results is not None else [MagicMock()]
    cell._tracker.motion_estimator.object_stacks = (
        object_stacks if object_stacks is not None else [MagicMock()]
    )
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

    def test_skips_when_the_tracker_holds_nothing_at_all(self, autopatcher, cell_dir):
        """Tracking genuinely never happened: a tracker was constructed and never
        initialized, so there is neither a result nor a reference stack. A file
        recording that is an empty container in every cell directory of every
        run, saying nothing an absent file does not say more clearly."""
        cell = _make_cell(tracking_results=[], object_stacks=[])
        autopatcher._saveTrackingHistory(cell, cell_dir)
        cell_dir.writeFile.assert_not_called()

    def test_saves_a_reference_stack_with_no_tracking_results(
        self, autopatcher, cell_dir
    ):
        """The case that used to be dropped entirely: a cell detected in a tile,
        seeded with a reference cube cut from that tile's stack, queued, and then
        abandoned before a single tracking frame. It has no results, so the old
        early return wrote no file at all and the cube that shows what the
        detector saw went with it. save_history writes a zero-result history
        quite happily."""
        cell = _make_cell(tracking_results=[])
        autopatcher._saveTrackingHistory(cell, cell_dir)
        cell_dir.writeFile.assert_called_once_with(
            cell._tracker, "tracking_history", fileType="AcqTrackFile", autoIncrement=False
        )

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


class TestFindCellSavesACellItGivesUpOn:
    """_autopatchFindCell re-verifies the tracker of the cell it selects, which
    records a tracking result whether the re-verify succeeds or fails. The demo
    loop only learns the cell's name once this method returns, so a cell it gives
    up on inside here is one the loop's own save will never see: the next
    setCell() closes it out of reach, still unsaved."""

    @staticmethod
    def _window(current_dir, cells):
        win = MagicMock()
        win._mockDemo = False
        win._unranked_cells = list(cells)
        win._ranked_cells = []
        win.module.manager.getCurrentDir.return_value = current_dir
        return win

    def test_a_cell_the_tracker_loses_is_saved_before_the_demo_moves_on(self, cell_dir):
        lost, replacement = _make_cell(), _make_cell()
        lost.initializeTracker.side_effect = ValueError("cell moved too much")
        autopatcher = Autopatcher(self._window(cell_dir, [lost, replacement]))

        assert autopatcher._autopatchFindCell() is replacement

        # Auto-incremented: the directory it goes into is this cell's, and the
        # cell that actually gets worked writes its own history there as the
        # demo's loop ends.
        cell_dir.writeFile.assert_called_once_with(
            lost._tracker, "tracking_history", fileType="AcqTrackFile", autoIncrement=True
        )

    def test_a_cell_interrupted_mid_verify_is_saved_before_the_stop_propagates(
        self, cell_dir
    ):
        # An operator's Stop lands here as readily as anywhere, and what the
        # tracker recorded before it is the record of the cell the demo was
        # part-way through checking.
        cell = _make_cell()
        cell.initializeTracker.side_effect = Stopped("operator pressed stop")
        autopatcher = Autopatcher(self._window(cell_dir, [cell]))

        with pytest.raises(Stopped):
            autopatcher._autopatchFindCell()

        cell_dir.writeFile.assert_called_once_with(
            cell._tracker, "tracking_history", fileType="AcqTrackFile", autoIncrement=True
        )
