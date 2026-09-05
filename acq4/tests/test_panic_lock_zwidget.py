"""The Camera module's depth gauge must not keep a target the stage never went to.

Reported from a live rig: with the Panic Lock latched, dragging the focus bar in
the Camera module's depth gauge correctly moved no devices, but the bar stayed
where it was dropped -- showing a focus depth the microscope was not at and was
never going to reach.

The mechanism is in two halves, and both are exercised here:

* ``ZPositionWidget`` latches its target line while a move is in flight
  (``_movingToTarget``) so that position updates during the move do not drag the
  line out from under the device. It is released by ``setMovingToTarget(False)``.
* ``MicroscopeCameraModInterface.focusChangedFromWidget`` starts the move and
  releases the latch when the move future finishes.

There are two ways the release can be missed, and the live rig hit the second one.

1. ``setFocusDepth()`` raises synchronously -- no future is created, so nothing was
   left to release the latch.
2. ``setFocusDepth()`` returns a task that is **already finished**. This is the
   normal path for a Panic Lock refusal: ``MotionPlanner.execute()`` is decorated
   with ``@asynch_with_qt_signals``, so it returns a ``QtFriendlyTask`` instead of
   running inline, and the guard at the top of its body fails that task almost
   immediately -- without raising in the caller at all. ``sigFinished`` has been
   emitted before ``connect()`` runs, so the slot never fires.

Case 2 is what shipped broken: the guard correctly stopped the move, but the bar
stayed where it was dropped.
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


class TestSnapBackContract:
    """``setMovingToTarget(False)`` must do what its docstring has always said."""

    def test_releasing_the_latch_snaps_the_target_line_to_the_focus(self, widget):
        widget.setFocusDepth(-100e-6)
        widget.setMovingToTarget(True)
        widget.setTargetDepth(-400e-6)
        assert widget.getTargetDepth() == pytest.approx(-400e-6)

        widget.setMovingToTarget(False)

        assert widget.getTargetDepth() == pytest.approx(-100e-6)

    def test_snapping_back_does_not_re_request_a_move(self, widget):
        """The snap must not look like the user dragging the line."""
        requested = []
        widget.sigTargetChangeRequested.connect(requested.append)

        widget.setFocusDepth(-100e-6)
        widget.setMovingToTarget(True)
        widget.setTargetDepth(-400e-6)
        widget.setMovingToTarget(False)

        assert requested == []

    def test_a_completed_move_leaves_the_line_where_the_device_arrived(self, widget):
        """The success path is unchanged: focus and target already agree."""
        widget.setFocusDepth(-100e-6)
        widget.setMovingToTarget(True)
        widget.setTargetDepth(-400e-6)
        widget.setFocusDepth(-400e-6)  # the device arrives

        widget.setMovingToTarget(False)

        assert widget.getTargetDepth() == pytest.approx(-400e-6)

    def test_the_latch_still_holds_the_line_during_a_move(self, widget):
        """Regression guard: releasing must not become unconditional."""
        widget.setFocusDepth(-100e-6)
        widget.setMovingToTarget(True)
        widget.setTargetDepth(-400e-6)

        widget.setFocusDepth(-250e-6)  # a position update partway through

        assert widget.getTargetDepth() == pytest.approx(-400e-6)


class _FakeScope:
    """Stands in for the microscope device behind the Z widget."""

    def __init__(self, globalHalt, focus=-100e-6):
        self._globalHalt = globalHalt
        self._focus = focus
        self.requested = []

    def name(self):
        return "Microscope"

    def getFocusDepth(self):
        return self._focus

    def setFocusDepth(self, depth, speed="fast", name=None):
        # The real path is Microscope -> Stage.move(), which is where the guard
        # lives (§6.2). Refusing here reproduces that synchronous raise.
        self._globalHalt.check()
        self.requested.append(depth)
        self._focus = depth
        raise AssertionError("unreachable in these tests")


class _Interface:
    """A minimal stand-in for the *self* that ScopeCameraModInterface needs.

    The real class is a CameraModuleInterface bound to a live camera window and
    cannot be constructed headlessly, but the two methods under test touch only
    ``getDevice()`` and ``zPositionWidget``. So the methods below are the **real**
    ones, taken off the real class and bound here -- reverting the fix in
    Microscope.py fails these tests, which is the whole point of doing it this way
    rather than copying the logic.
    """

    focusChangedFromWidget = ScopeCameraModInterface.focusChangedFromWidget
    _handleRefocusFinished = ScopeCameraModInterface._handleRefocusFinished

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

        # The user drags the bar and lets go. pyqtgraph emits
        # sigPositionChangeFinished on release; _onTargetLineMoved latches and
        # re-emits, exactly as it does for a real drag.
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
        """Releasing the latch must not swallow genuine faults."""

        class _BrokenScope(_FakeScope):
            def setFocusDepth(self, depth, speed="fast", name=None):
                raise RuntimeError("limit switch")

        widget.setFocusDepth(-100e-6)
        iface = _Interface(_BrokenScope(GlobalHalt()), widget)
        widget.setMovingToTarget(True)
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
        assert widget._movingToTarget is False

    def test_a_still_running_move_keeps_the_line_latched(self, widget):
        """The fix must not release the latch on a move that is genuinely in flight."""

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
        assert widget._movingToTarget is True
