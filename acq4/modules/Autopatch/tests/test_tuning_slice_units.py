"""Tests that the tuning slice unit follows AutopatchWindow's slices, and that arming refuses when it cannot key on one."""

import random

import pytest

from acq4.experiment.actions.storage import create_data_dir
from acq4.Manager import getManager
from acq4.modules.Autopatch.performance_tuning import arming
from acq4.modules.Autopatch.performance_tuning.mutators.base import ValueMutator
from acq4.util import tuning_points
from acq4.util.tests.data_dir_helpers import strip_uuid
from acq4.util.tests.memory_ledger import MemoryLedger
from acq4.util.tuning_points import TuningPointError, TuningPointWarning

from .test_window_integration import (
    _FakeCameraWithDevice,
    _FakePipetteSelector,
    _makeWindow,
    _write_slow_protocol,
    qapp,
)


class _Detector(ValueMutator):
    name = "detector"
    unit = "slice"
    answers = {"pipette_detector_class"}
    conditions = ["A", "B"]

    def value(self, point, default, condition, facts):
        return condition


class _MinHealth(ValueMutator):
    name = "min_health"
    unit = "survey"
    answers = {"min_health"}
    conditions = [0.5, 0.7]

    def value(self, point, default, condition, facts):
        return condition


class _CameraUnpluggedAfterFirstLook(_FakeCameraWithDevice):
    """A camera selector whose camera is gone after the first time anyone asks for it."""

    def __init__(self):
        super().__init__()
        self._looks = 0

    def getSelectedObj(self):
        self._looks += 1
        return self.camera if self._looks == 1 else None


@pytest.fixture(autouse=True)
def _clean():
    tuning_points.uninstall()
    yield
    tuning_points.uninstall()


@pytest.fixture
def win(qapp, tmp_path):
    w = _makeWindow(tmp_path)
    yield w
    w.teardown()


@pytest.fixture
def ledger():
    return MemoryLedger(random.Random(0))


def _uuid(dirHandle):
    return dirHandle.info()["__uuid__"]


def _unit_lines(ledger, event):
    return [
        (line["unit"], line["unit_id"])
        for line in ledger.lines
        if line["event"] == event
    ]


def test_arm_opens_slice_unit_for_current_slice(win, ledger):
    win.newSlice()
    arming.arm(win, "run-1", [_MinHealth()], ledger)
    unit = win._tuningSliceUnit
    assert unit is tuning_points.current_slice()
    assert unit.id == _uuid(win.slice.dirHandle)
    assert not unit.closed
    assert _unit_lines(ledger, "unit_open") == [("slice", unit.id)]


def test_disarm_closes_slice_unit_and_uninstalls(win, ledger):
    win.newSlice()
    arming.arm(win, "run-1", [_MinHealth()], ledger)
    unit = win._tuningSliceUnit
    arming.disarm(win)
    assert unit.closed
    assert win._tuningSliceUnit is None
    assert tuning_points.installed() is None
    assert _unit_lines(ledger, "unit_close") == [("slice", unit.id)]


def test_new_slice_closes_old_and_opens_new_unit(win, ledger):
    win.newSlice()
    oldId = _uuid(win.slice.dirHandle)
    arming.arm(win, "run-1", [_MinHealth()], ledger)
    old = win._tuningSliceUnit
    win.newSlice()
    newId = _uuid(win.slice.dirHandle)
    assert newId != oldId
    assert old.closed
    assert win._tuningSliceUnit is tuning_points.current_slice()
    assert win._tuningSliceUnit.id == newId
    assert [
        (line["event"], line["unit_id"])
        for line in ledger.lines
        if line["event"] in ("unit_open", "unit_close")
    ] == [("unit_open", oldId), ("unit_close", oldId), ("unit_open", newId)]


def test_new_slice_while_disarmed_opens_no_unit(win):
    win.newSlice()
    assert win._tuningSliceUnit is None


def test_new_slice_mid_cell_keeps_in_flight_cell_on_old_slice(win, ledger):
    win.newSlice()
    oldId = _uuid(win.slice.dirHandle)
    arming.arm(win, "run-1", [_Detector()], ledger)
    cellDir = create_data_dir(getManager(), level="Cell")
    cell = tuning_points.open_unit("cell", cell_dir=cellDir)
    with pytest.warns(TuningPointWarning, match="'detector'"):
        win.newSlice()
    assert win._tuningSliceUnit.id != oldId
    tuning_points.value("pipette_detector_class", "default")
    summary = tuning_points.close_unit(cell)
    (decision,) = ledger.decision_lines("detector")
    assert (decision["unit"], decision["unit_id"]) == ("slice", oldId)
    assert summary["assigned_by"] == {"detector": "slice"}


def test_new_slice_that_fails_to_start_leaves_armed_without_slice_unit(
    qapp, tmp_path, ledger
):
    win = _makeWindow(tmp_path)
    try:
        win.newSlice()
        old = win.slice
        arming.arm(win, "run-1", [_Detector()], ledger)
        oldUnit = win._tuningSliceUnit
        win.cameraSelector = _CameraUnpluggedAfterFirstLook()
        with pytest.warns(TuningPointWarning, match="has not fired"):
            win.newSlice()
        assert win.slice is old
        assert oldUnit.closed
        assert win._tuningSliceUnit is None
        assert tuning_points.installed() is not None
        with pytest.warns(TuningPointWarning, match="outside any slice unit"):
            assert tuning_points.value("pipette_detector_class", "default") == "default"
    finally:
        win.teardown()


def test_arm_refused_without_slice_dir(win, ledger):
    win.addRegionHere()
    assert win.slice is not None and win.slice.dirHandle is None
    with pytest.raises(TuningPointError, match="no slice directory: press New slice"):
        arming.arm(win, "run-1", [_MinHealth()], ledger)
    assert tuning_points.installed() is None
    assert win._tuningSliceUnit is None


def test_arm_refused_without_any_slice(win, ledger):
    assert win.slice is None
    with pytest.raises(TuningPointError, match="no slice directory: press New slice"):
        arming.arm(win, "run-1", [_MinHealth()], ledger)
    assert tuning_points.installed() is None


def test_arm_refused_when_slice_dir_lacks_uuid(win, ledger):
    win.newSlice()
    strip_uuid(win.slice.dirHandle)
    assert "__uuid__" not in win.slice.dirHandle.info()
    with pytest.raises(TuningPointError, match="slice directory has no uuid"):
        arming.arm(win, "run-1", [_MinHealth()], ledger)
    assert tuning_points.installed() is None
    assert win._tuningSliceUnit is None


def test_arm_refused_while_already_installed(win, ledger):
    win.newSlice()
    arming.arm(win, "run-1", [_MinHealth()], ledger)
    first = win._tuningSliceUnit
    with pytest.raises(TuningPointError, match="already installed"):
        arming.arm(win, "run-2", [_MinHealth()], ledger)
    assert win._tuningSliceUnit is first
    assert tuning_points.installed().run_id == "run-1"
    assert _unit_lines(ledger, "unit_open") == [("slice", first.id)]


def test_arm_and_disarm_refused_while_running(qapp, qtbot, tmp_path, ledger):
    _write_slow_protocol(tmp_path, "slow.py")
    win = _makeWindow(
        tmp_path, pipetteSelector=_FakePipetteSelector(target=(1e-3, 2e-3, 3e-3))
    )
    try:
        win.newSlice()
        win.protocolPanel.fileCombo.setCurrentText("slow")
        arming.arm(win, "run-1", [_MinHealth()], ledger)
        unit = win._tuningSliceUnit
        win.cellPanel.addFromTargetBtn.click()
        win.statusPanel.startBtn.click()
        qtbot.wait(50)
        assert win.orchestrator.isRunning()
        with pytest.raises(TuningPointError, match="running"):
            arming.arm(win, "run-2", [_MinHealth()], ledger)
        with pytest.raises(TuningPointError, match="running"):
            arming.disarm(win)
        assert not unit.closed
        assert tuning_points.installed().run_id == "run-1"
        win.orchestrator.stop()
        win.orchestrator.wait(timeout=5.0, updates=True)
        assert not win.orchestrator.isRunning()
        arming.disarm(win)
        assert unit.closed
        assert tuning_points.installed() is None
    finally:
        win.teardown()


def test_cell_dir_under_new_slice_carries_slice_id(win):
    win.newSlice()
    cellDir = create_data_dir(getManager(), level="Cell")
    assert cellDir.parent() == win.slice.dirHandle
    assert cellDir.info()["slice_id"] == _uuid(win.slice.dirHandle)


def test_teardown_of_armed_window_closes_slice_unit_and_uninstalls(
    qapp, tmp_path, ledger
):
    win = _makeWindow(tmp_path)
    try:
        win.newSlice()
        arming.arm(win, "run-1", [_MinHealth()], ledger)
        unit = win._tuningSliceUnit
    finally:
        win.teardown()
    assert unit.closed
    assert win._tuningSliceUnit is None
    assert tuning_points.installed() is None
    assert _unit_lines(ledger, "unit_close") == [("slice", unit.id)]


def test_arm_succeeds_after_armed_window_torn_down(qapp, tmp_path, ledger):
    first = _makeWindow(tmp_path)
    first.newSlice()
    arming.arm(first, "run-1", [_MinHealth()], ledger)
    first.teardown()
    second = _makeWindow(tmp_path)
    try:
        second.newSlice()
        arming.arm(second, "run-2", [_MinHealth()], ledger)
        assert tuning_points.installed().run_id == "run-2"
        assert second._tuningSliceUnit.id == _uuid(second.slice.dirHandle)
    finally:
        second.teardown()


def test_teardown_of_unarmed_window_leaves_tuning_alone(qapp, tmp_path, ledger):
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.teardown()
    assert win._tuningSliceUnit is None
    assert tuning_points.installed() is None
    assert ledger.lines == []
