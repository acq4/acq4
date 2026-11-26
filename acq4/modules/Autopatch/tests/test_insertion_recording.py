"""The window records a survey-exposure insertion each time the selected pipette
enters `cell detect`, and follows the pipette selection."""

import threading

import pytest

from acq4.experiment.search_region import RectRegion
from acq4.util import Qt

from .fakes import FakePatchPipette, FakePipetteSelector
from .test_window_integration import _makeWindow


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def makeWindow(tmp_path, pipette):
    selector = FakePipetteSelector(pipette)
    win = _makeWindow(tmp_path, pipetteSelector=selector)
    win.newSlice()
    win.slice.addRegion(RectRegion(0.0, 0.0, 1e-3, 1e-3))
    return win, selector


def test_entering_cell_detect_records_one_insertion_at_the_target(qapp, tmp_path):
    pipette = FakePatchPipette(target=(3e-4, 4e-4, -30e-6))
    win, _ = makeWindow(tmp_path, pipette)
    try:
        win._onStartRun()

        pipette.setState("cell detect")

        [(x, y, t)] = win.slice.insertions
        assert (x, y) == (3e-4, 4e-4)
        assert t > 0
    finally:
        win.teardown()


def test_other_states_record_nothing(qapp, tmp_path):
    pipette = FakePatchPipette()
    win, _ = makeWindow(tmp_path, pipette)
    try:
        win._onStartRun()

        for state in ("approach", "seal", "whole cell", "bath"):
            pipette.setState(state)

        assert win.slice.insertions == ()
    finally:
        win.teardown()


def test_no_slice_is_a_no_op(qapp, tmp_path):
    pipette = FakePatchPipette()
    win, _ = makeWindow(tmp_path, pipette)
    try:
        win._onStartRun()
        win.slice = None

        pipette.setState("cell detect")
    finally:
        win.teardown()


def test_switching_pipette_disconnects_the_old_one(qapp, tmp_path):
    first, second = FakePatchPipette(), FakePatchPipette(target=(5e-4, 5e-4, 0.0))
    win, selector = makeWindow(tmp_path, first)
    try:
        win._onStartRun()
        selector.pipette = second
        win._onStartRun()

        first.setState("cell detect")
        assert win.slice.insertions == ()
        second.setState("cell detect")

        [(x, y, _)] = win.slice.insertions
        assert (x, y) == (5e-4, 5e-4)
    finally:
        win.teardown()


def test_restarting_with_the_same_pipette_does_not_double_count(qapp, tmp_path):
    pipette = FakePatchPipette()
    win, _ = makeWindow(tmp_path, pipette)
    try:
        win._onStartRun()
        win._onStartRun()

        pipette.setState("cell detect")

        assert len(win.slice.insertions) == 1
    finally:
        win.teardown()


def test_teardown_disconnects_the_pipette(qapp, tmp_path):
    pipette = FakePatchPipette()
    win, _ = makeWindow(tmp_path, pipette)
    win._onStartRun()
    slice_ = win.slice
    win.teardown()

    pipette.setState("cell detect")

    assert slice_.insertions == ()


def test_a_state_change_from_another_thread_is_recorded_on_the_gui_thread(
    qapp, tmp_path, qtbot
):
    pipette = FakePatchPipette()
    win, _ = makeWindow(tmp_path, pipette)
    try:
        win._onStartRun()
        recordedOn = []
        record = win.slice.recordInsertion

        def spy(xy, t):
            recordedOn.append(threading.current_thread())
            record(xy, t)

        win.slice.recordInsertion = spy
        worker = threading.Thread(target=pipette.setState, args=("cell detect",))
        worker.start()
        worker.join()

        qtbot.waitUntil(lambda: len(win.slice.insertions) == 1, timeout=2000)
        assert recordedOn == [threading.main_thread()]
    finally:
        win.teardown()
