"""The Camera module's depth gauge must not keep a target the stage never went to.

Both halves are exercised here:

* ``ZPositionWidget`` moves its target line only on ``setTargetDepth`` or a user
  drag; showing the focus depth never touches it.
* ``ScopeCameraModInterface`` supplies the focus device's commanded target and
  puts the line back on it when a dragged request fails to reach the device.

A dragged request can fail two ways: ``setFocusDepth()`` raises synchronously, or
it returns an already-finished task. The second is the Panic Lock refusal path --
``MotionPlanner.execute()`` is ``@asynch_with_qt_signals``, so the guard fails the
returned ``QtFriendlyTask`` before ``connect()`` runs and the slot never fires.
"""

from __future__ import annotations

import pytest

from acq4.devices.Microscope.Microscope import ScopeCameraModInterface
from acq4.panic import GlobalHalt, GlobalHaltException
from acq4.util.ui.ZPositionWidget import ZPositionWidget


@pytest.fixture
def widget(qtbot):
    import pyqtgraph as pg

    plot = pg.PlotWidget()
    qtbot.addWidget(plot)
    w = ZPositionWidget(plot.getPlotItem(), movable=True)
    # Keep the PlotWidget alive for the test: ZPositionWidget stores only the
    # PlotItem, and a collected PlotWidget takes the InfiniteLines with it.
    w._testPlotWidget = plot
    return w


class TestTheLinesAreIndependent:
    """The widget is told the target; it never infers one from the focus."""

    def test_showing_the_focus_does_not_move_the_target_line(self, widget):
        widget.setTargetDepth(-400e-6)

        widget.setFocusDepth(-100e-6)

        assert widget.getTargetDepth() == pytest.approx(-400e-6)
        assert widget.focusLine.value() == pytest.approx(-100e-6)

    def test_setting_the_target_does_not_look_like_a_drag(self, widget):
        requested = []
        widget.sigTargetChangeRequested.connect(requested.append)

        widget.setTargetDepth(-400e-6)

        assert requested == []

    def test_dragging_the_line_requests_the_depth_it_was_dropped_at(self, widget):
        requested = []
        widget.sigTargetChangeRequested.connect(requested.append)

        widget.targetLine.setValue(-400e-6)
        widget.targetLine.sigPositionChangeFinished.emit(widget.targetLine)

        assert requested == [pytest.approx(-400e-6)]


class _FakeFocusDevice:
    """The stage behind the microscope: an idle one, whose target equals its position."""

    def __init__(self, z=0.0):
        self.z = z

    def globalPosition(self):
        return [0, 0, self.z]

    def globalTargetPosition(self):
        return [0, 0, self.z]


class _FakeScope:
    """Stands in for the microscope device behind the Z widget."""

    def __init__(self, globalHalt, focus=-100e-6):
        self._globalHalt = globalHalt
        self._focus = focus
        self._focusDevice = _FakeFocusDevice()
        self.requested = []

    def name(self):
        return "Microscope"

    def getFocusDepth(self):
        return self._focus

    def focusDevice(self):
        return self._focusDevice

    def setFocusDepth(self, depth, speed="fast", name=None):
        # The real path is Microscope -> Stage.move(), which is where the guard
        # lives. Refusing here reproduces that synchronous raise.
        self._globalHalt.check()
        self.requested.append(depth)
        self._focus = depth
        raise AssertionError("unreachable in these tests")


class _Interface:
    """A minimal stand-in for the *self* that ScopeCameraModInterface needs.

    The real class cannot be constructed headlessly, but the methods under test
    touch only ``getDevice()`` and ``zPositionWidget``, so they are bound here
    off the real class rather than copied.
    """

    focusChangedFromWidget = ScopeCameraModInterface.focusChangedFromWidget
    _handleRefocusFinished = ScopeCameraModInterface._handleRefocusFinished
    updateTargetDepth = ScopeCameraModInterface.updateTargetDepth

    def __init__(self, dev, zPositionWidget):
        self._dev = dev
        self.zPositionWidget = zPositionWidget

    def getDevice(self):
        return self._dev


class TestDraggingWhileHalted:
    def test_the_bar_snaps_back_when_the_halt_refuses_the_move(self, widget):
        """The reported bug."""
        globalHalt = GlobalHalt()
        scope = _FakeScope(globalHalt, focus=-100e-6)
        iface = _Interface(scope, widget)
        widget.sigTargetChangeRequested.connect(iface.focusChangedFromWidget)
        widget.setFocusDepth(-100e-6)

        globalHalt.halt("operator pressed ESC")

        # A real drag: pyqtgraph emits sigPositionChangeFinished on release.
        widget.targetLine.setValue(-400e-6)
        widget.targetLine.sigPositionChangeFinished.emit(widget.targetLine)

        assert scope.requested == [], "a halted rig must not be commanded to move"
        assert widget.getTargetDepth() == pytest.approx(-100e-6), (
            "the bar stayed where it was dropped, advertising a depth the stage "
            "is not at and will not reach"
        )

    def test_the_focus_line_never_moved(self, widget):
        globalHalt = GlobalHalt()
        scope = _FakeScope(globalHalt, focus=-100e-6)
        iface = _Interface(scope, widget)
        widget.sigTargetChangeRequested.connect(iface.focusChangedFromWidget)
        widget.setFocusDepth(-100e-6)
        globalHalt.halt("operator pressed ESC")

        widget.targetLine.setValue(-400e-6)
        widget.targetLine.sigPositionChangeFinished.emit(widget.targetLine)

        assert widget.focusLine.value() == pytest.approx(-100e-6)

    def test_no_error_dialog_for_a_refused_drag(self, widget):
        """A halt is expected, not exceptional -- the panic dialog already says so.

        One popup per drag attempt would bury it.
        """
        globalHalt = GlobalHalt()
        scope = _FakeScope(globalHalt, focus=-100e-6)
        iface = _Interface(scope, widget)
        widget.setFocusDepth(-100e-6)
        globalHalt.halt("operator pressed ESC")

        iface.focusChangedFromWidget(-400e-6)  # must not raise

    def test_a_non_halt_failure_still_surfaces(self, widget):
        """Correcting the line must not swallow genuine faults."""

        class _BrokenScope(_FakeScope):
            def setFocusDepth(self, depth, speed="fast", name=None):
                raise RuntimeError("limit switch")

        widget.setFocusDepth(-100e-6)
        iface = _Interface(_BrokenScope(GlobalHalt()), widget)
        widget.setTargetDepth(-400e-6)

        with pytest.raises(RuntimeError, match="limit switch"):
            iface.focusChangedFromWidget(-400e-6)

        assert widget.getTargetDepth() == pytest.approx(-100e-6)

    def test_dragging_works_again_after_resume(self, widget):
        globalHalt = GlobalHalt()
        scope = _FakeScope(globalHalt, focus=-100e-6)
        iface = _Interface(scope, widget)
        widget.setFocusDepth(-100e-6)

        globalHalt.halt("operator pressed ESC")
        iface.focusChangedFromWidget(-400e-6)
        assert scope.requested == []

        globalHalt.resume()
        with pytest.raises(AssertionError, match="unreachable"):
            iface.focusChangedFromWidget(-400e-6)
        assert scope.requested == [-400e-6], "the move must be commanded again once armed"


class _DoneTask:
    """A task that is already finished when it is handed back.

    This is what MotionPlanner.execute() returns for a refused move: the guard
    runs inside the task body, so the task is failed before the caller can even
    connect to sigFinished.
    """

    def __init__(self):
        self.is_done = True
        self.connected = []

    class _Sig:
        def __init__(self, owner):
            self._owner = owner

        def connect(self, slot):
            # Already emitted -- connecting now can never fire, which is exactly
            # the failure being reproduced.
            self._owner.connected.append(slot)

    @property
    def sigFinished(self):
        return self._Sig(self)


class TestRefusalReportedAsAnAlreadyFailedTask:
    """The live-rig bug: refused via a finished task, not via a raise."""

    def test_the_bar_snaps_back_when_the_move_comes_back_already_finished(self, widget):
        class _AsyncRefusingScope(_FakeScope):
            def setFocusDepth(self, depth, speed="fast", name=None):
                return _DoneTask()  # refused inside the task body; never raises

        widget.setFocusDepth(-100e-6)
        iface = _Interface(_AsyncRefusingScope(GlobalHalt()), widget)
        widget.sigTargetChangeRequested.connect(iface.focusChangedFromWidget)

        widget.targetLine.setValue(-400e-6)
        widget.targetLine.sigPositionChangeFinished.emit(widget.targetLine)

        assert widget.getTargetDepth() == pytest.approx(-100e-6), (
            "sigFinished had already fired before connect(), so the slot never ran "
            "and the line stayed where the user dropped it"
        )

    def test_a_still_running_move_leaves_the_line_where_it_was_dropped(self, widget):
        """A move under way announces its own target through
        ``Stage.sigTargetChanged``; nothing here may pre-empt that."""

        class _RunningTask(_DoneTask):
            def __init__(self):
                super().__init__()
                self.is_done = False

        class _SlowScope(_FakeScope):
            def setFocusDepth(self, depth, speed="fast", name=None):
                return _RunningTask()

        widget.setFocusDepth(-100e-6)
        iface = _Interface(_SlowScope(GlobalHalt()), widget)
        widget.sigTargetChangeRequested.connect(iface.focusChangedFromWidget)

        widget.targetLine.setValue(-400e-6)
        widget.targetLine.sigPositionChangeFinished.emit(widget.targetLine)

        assert widget.getTargetDepth() == pytest.approx(-400e-6)
