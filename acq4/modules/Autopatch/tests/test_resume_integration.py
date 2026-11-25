"""End to end: a window surveys and works a cell, is torn down, and a fresh window
resumes the slice directory and carries on from the same next pick."""

import importlib

import numpy as np
import pytest
from coorx import SRT3DTransform

from acq4.experiment import tile_detector
from acq4.experiment.search_region import RectRegion
from acq4.experiment.tests.test_tile_detector import FakeCamera, FakeScope
from acq4.modules.Autopatch.Autopatch import UPCOMING_ROWS
from acq4.util import Qt
from acq4.util.imaging.frame import Frame

from .test_window_integration import (
    _FakeCamera,
    _FakeCameraWithDevice,
    _makeWindow,
    _upcomingIds,
    _write_protocol,
)

FOV = (100e-6, 100e-6)
PIXEL = 1e-6

_ONE_SURVEY_CELL_PROTOCOL = '''"""Resume test fixture: presses Stop on its own run once a survey cell is in hand."""
from acq4.util.task import current_task


def run(ctx, **kwargs):
    task = current_task()
    if task is not None and ctx.cell.source == "survey":
        task.stop("one survey cell is enough")
'''


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def _cameraSelector():
    return _FakeCameraWithDevice(_FakeCamera(roi_fov=FOV, roi_center=(0.0, 0.0, 0.0)))


def _syntheticSurvey(monkeypatch):
    """Route the window's real tile detector through synthetic imaging and
    detections, the way buildSurveyedSlice does; returns the scope it drives.

    Each tile reports two cells 40 um apart, either side of its centre."""
    camera = FakeCamera()
    scope = FakeScope(camera)

    def acquire(cam, start_z, stop_z, step_z):
        x, y, _ = scope.moves[-1]
        frames = []
        for i in range(3):
            transform = SRT3DTransform(
                scale=(PIXEL, PIXEL, 1.0),
                offset=(x - FOV[0] / 2, y - FOV[1] / 2, start_z + i * step_z),
                from_cs="frame",
                to_cs="global",
            ).as_affine()
            m = transform.matrix
            m[:, 2] = m[:, 2] / np.linalg.norm(m[:, 2]) * step_z
            transform.matrix = m
            frames.append(Frame(np.zeros((8, 8)), {"transform": transform}))
        return frames

    def detect(stack, xy_scale, z_scale, models, min_volume_m3, save_prefix):
        with open(f"{save_prefix}.ma", "wb") as fh:
            fh.write(b"stack")
        with open(f"{save_prefix}_cellpose_masks.npy", "wb") as fh:
            fh.write(b"masks")
        x, y, _ = scope.moves[-1]
        return [
            ((x - 20e-6, y, -30e-6), 0.9, 1.5e-16, 8e-11),
            ((x + 20e-6, y, -30e-6), 0.8, 1.5e-16, 8e-11),
        ]

    monkeypatch.setattr(tile_detector, "_acquire", acquire)
    monkeypatch.setattr(tile_detector, "_detect", detect)
    # The window's own camera and scope fakes answer only what a producer's
    # install asks; the detector itself needs focus control and a scope position.
    autopatchModule = importlib.import_module("acq4.modules.Autopatch.Autopatch")
    real = tile_detector.make_tile_detector
    monkeypatch.setattr(
        autopatchModule,
        "make_tile_detector",
        lambda **kwargs: real(**{**kwargs, "camera": camera, "scope": scope}),
    )
    return scope


def _recordFinished(win):
    finished = []
    win.orchestrator.sigCellFinished.connect(
        lambda cell, status: finished.append((cell.candidate_id, cell.source, status))
    )
    return finished


def test_a_fresh_window_resumes_a_surveyed_slice_where_the_last_one_stopped(
    qapp, qtbot, tmp_path, monkeypatch
):
    scope = _syntheticSurvey(monkeypatch)
    _write_protocol(tmp_path, "one_survey_cell.py", _ONE_SURVEY_CELL_PROTOCOL)

    win = _makeWindow(tmp_path, cameraSelector=_cameraSelector())
    try:
        win.protocolPanel.refreshFileList()
        assert win.protocolPanel.selectProtocol("one_survey_cell")
        win.newSlice()
        win.regionPanel.sigRegionsChanged.emit([RectRegion(-75e-6, -30e-6, 75e-6, 30e-6)])
        assert len(win.slice.tileGrid()) == 2
        win._onManualSeedsRequested([(0.0, 20e-6, -30e-6)])
        finished = _recordFinished(win)

        win.statusPanel.startBtn.click()
        qtbot.waitUntil(
            lambda: win.orchestrator._task is None and not win.statusPanel.isRunInFlight(),
            timeout=10000,
        )

        assert [(source, status) for _, source, status in finished] == [
            ("manual", "done"),
            ("survey", "done"),
        ]
        survey = win.slice.survey
        preview = [
            e["candidate_id"]
            for e in survey.preview(win.slice.constraints, win.slice.containsPoint, UPCOMING_ROWS)
        ]
        handedOut = set(survey.handedOutIds())
        assert handedOut == {cid for cid, _, _ in finished}
        assert preview
        imaged = {(x, y) for x, y, _ in scope.moves}
        assert len(imaged) == 1
        sliceDir = win.slice.dirHandle
    finally:
        win.teardown()

    resumed = _makeWindow(tmp_path, cameraSelector=_cameraSelector())
    try:
        resumed.resumeSlice(sliceDir)

        assert resumed.slice.dirHandle is sliceDir
        assert _upcomingIds(resumed) == preview

        movesBefore = len(scope.moves)
        finishedAfter = _recordFinished(resumed)
        resumed._onStartRun()
        resumed.orchestrator.run_sync()

        ranIds = [cid for cid, _, _ in finishedAfter]
        assert ranIds[0] == preview[0]
        assert not handedOut & set(ranIds)
        assert len(ranIds) == len(set(ranIds)) == 3
        assert all(status == "done" for _, _, status in finishedAfter)
        imagedAfter = [(x, y) for x, y, _ in scope.moves[movesBefore:]]
        assert len(imagedAfter) == 1
        assert not imaged & set(imagedAfter)
    finally:
        resumed.teardown()
