"""FSM-driving actions: drive acq4's PatchPipette state machine from a declared
entry state to one of this action's declared terminal states, mapping unexpected
abnormal states to orchestration exceptions, and retaining each drive's
test-pulse analysis and state transitions for Area 5."""
from __future__ import annotations

import os
import time

import numpy as np

from acq4.util import Qt
from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder
from acq4.util.task import Stopped, check_stop, run_in_gui_thread, sleep

from ..exceptions import AdvanceToNextCell, raise_if_abnormal


def _safe_abort(ctx) -> None:
    """Mirror the MultiPatch "Cancel" button (pipetteControl._cancelClicked):
    stop the current FSM state's job, which switches the pipette to that
    state's declared fallback state rather than forcing a single hard-coded
    holding state."""
    pip = getattr(ctx, "pipette", None)
    if pip is not None:
        state_job = pip.getState()
        if state_job is not None:
            state_job.stop("orchestration abort", wait=True)


def _setFsmDetails(action_entry, entry_state, reached, transitions, recorder=None) -> None:
    """Retain this drive's Area 5 payload: the test-pulse analysis observed
    during it, and the states it walked.

    An empty history rather than None when there is no recorder, so the renderer
    has one payload shape to handle rather than two.
    """
    # Deferred rather than joining the top-of-file imports: importing anything
    # from acq4.filetypes runs that package's __init__, which eagerly imports
    # and registers every sibling FileType module (acq4/filetypes/filetypes.py's
    # module-level listFileTypes() call). Keeping it here means that cost is
    # paid only when a payload is actually being built, not by every import of
    # this module.
    from acq4.filetypes.MultiPatchLog import TEST_PULSE_NUMPY_DTYPE

    if recorder is None:
        history = np.empty(0, dtype=TEST_PULSE_NUMPY_DTYPE)
        log_file = None
    else:
        # The recorder's own accumulated rows, not clampDevice.testPulseHistory():
        # the device's history is reset mid-patch (approach.py:251), so slicing
        # it by this drive's time window would silently lose whatever preceded
        # the reset. The live plot in _openLivePlot reads the device instead,
        # deliberately, because a live view of "now" should show its own
        # current history.
        history = recorder.testPulseAnalysis()
        log_file = recorder.logFileName()
        if log_file is not None:
            log_file = os.path.basename(log_file)
    action_entry.set_details(
        "test_pulse_history",
        {
            "history": history,
            "transitions": list(transitions),
            "entry_state": entry_state,
            "reached": reached,
            "log_file": log_file,
        },
    )


def _openRecorder(ctx, record_full_test_pulses: bool):
    """A recorder writing this drive's events into the current storage
    directory, or None if one could not be opened.

    Never raises: the patch attempt is the experiment and the log is a record of
    it, so an unset storage directory or a full disk must not stop a pipette
    from patching. The reason goes to the cell's log instead.
    """
    try:
        return MultiPatchLogRecorder(
            ctx.manager.getCurrentDir(),
            pipettes=(ctx.pipette,),
            record_full_test_pulses=record_full_test_pulses,
        )
    except Exception as exc:
        ctx.log(f"could not start event recording: {exc}")
        return None


def _openLivePlot(ctx, action_entry) -> object | None:
    """Mount a live steady-state resistance plot for this drive, returning a
    zero-argument teardown to call when it ends, or None if there is no clamp to
    plot from.

    Rss over time is the measurement an operator watches to judge whether a seal
    is forming, so it is what Area 5 shows while the FSM drives (design doc
    §4.5). Reuses MultiPatch's PlotWidget rather than reimplementing it.

    Built through run_in_gui_thread because this runs on the orchestrator's
    worker thread and a widget must not be constructed off the GUI thread.
    """
    clamp = getattr(ctx.pipette, "clampDevice", None)
    if clamp is None:
        return None

    def build():
        # Imported here: pipetteControl pulls in the MultiPatch module's device
        # imports, and acq4.experiment must stay importable without them.
        from acq4.modules.MultiPatch.pipetteControl import PlotWidget

        widget = PlotWidget(mode="ss resistance")
        # Autopatch picks the mode; the operator does not need the combo while
        # an action is driving (design doc §4.5). The frozen plot shows it.
        widget.hideHeader()
        return widget

    widget = run_in_gui_thread(build)

    def onTestPulse(_device, testPulse):
        # Deliberately clamp.testPulseHistory(), not the recorder's: a live view
        # of "now" should show the device's own current history. The frozen
        # payload below reads the recorder instead, because the device's history
        # is reset mid-patch (approach.py:251) and would silently lose whatever
        # preceded the reset -- see _setFsmDetails.
        widget.newTestPulse(testPulse, clamp.testPulseHistory())

    # Default (queued) connection deliberately: PatchPipetteState connects to
    # this same signal with an explicit DirectConnection, which is correct for a
    # state machine and wrong for a widget -- it would mutate the plot from the
    # clamp's thread.
    clamp.sigTestPulseFinished.connect(onTestPulse)
    action_entry.set_details_widget(widget)

    def teardown():
        # A live connection from a device signal into a widget the panel has
        # moved on from is the cross-module reference neither Autopatch's widget
        # -tree teardown nor unbindOrchestrator reaches (design doc §4.5).
        Qt.disconnect(clamp.sigTestPulseFinished, onTestPulse)

    return teardown


def _drive_fsm(
    ctx,
    name,
    entry_state,
    terminals,
    entry_config=None,
    poll_interval=0.1,
    record=True,
    record_events=True,
    record_full_test_pulses=True,
) -> str:
    """Drive the PatchPipette FSM from entry_state and return the terminal state
    it reaches. Abnormal states not in `terminals` raise (see raise_if_abnormal).

    With `record` true, this action retains a "test_pulse_history" details
    payload for Area 5 -- the test-pulse analysis observed during the drive, and
    the pipette states it walked -- and mounts the live Rss plot. `clean` passes
    `record=False`, which short-circuits both regardless of record_events (clean
    has no record_events parameter): there is nothing an operator reads off a
    clean (design doc §4.5).

    With `record` and `record_events` both true, this action also opens a
    MultiPatchLogRecorder that writes the drive's events to disk; `record_events`
    is the disk-side switch alone, so turning it off still leaves the Area 5
    payload (and its plot) intact, just with an empty history.
    """
    with ctx.log_action(name) as action_entry:
        pip = ctx.pipette
        action_entry.set_status(f"driving FSM from {entry_state!r}")
        # Both initialised before the try so that if one opener succeeds and
        # the other raises, the finally below still sees whichever one opened
        # and tears it down -- otherwise a raise from the second opener would
        # leak whatever the first one already opened.
        recorder = None
        teardownPlot = None
        last_state = entry_state
        # (timestamp, state) for the entry state and every change the poll loop
        # observes. Reading a failed patch is mostly "where did it stall", and
        # this is what answers it; the loop already detects the changes.
        transitions = [(time.time(), entry_state)]
        reached = None
        try:
            # record_events gates the disk recorder alone -- record gates the
            # whole Area 5 payload (and the live plot that shares its life),
            # which is why `clean` (record=False) opens neither regardless of
            # record_events.
            recorder = _openRecorder(ctx, record_full_test_pulses) if record and record_events else None
            if record:
                try:
                    teardownPlot = _openLivePlot(ctx, action_entry)
                except Exception as exc:
                    # A live plot is a display convenience layered on top of the
                    # drive, not the drive itself -- mirrors _openRecorder's own
                    # never-raises contract so a widget-construction failure
                    # cannot fail a patch attempt. The recorder opened above, if
                    # any, is still torn down by the finally below.
                    ctx.log(f"could not start live plot: {exc}")
            # Fresh dict per call so no caller shares a mutable default.
            pip.setState(entry_state, **dict(entry_config or {}))
            while True:
                check_stop()
                if ctx.next_cell_requested():
                    ctx.next_cell()
                state = pip.getState().stateName
                if state in terminals:
                    action_entry.set_status(f"reached {state!r}")
                    if state != last_state:
                        transitions.append((time.time(), state))
                    reached = state
                    return state
                if state != last_state:
                    # Only on change: re-setting the same string every poll
                    # would spam the UI callback for no new information, and
                    # would hide a pipette parked in a non-terminal state
                    # (e.g. "cell attached") behind a stale row otherwise.
                    action_entry.set_status(f"now in {state!r}")
                    transitions.append((time.time(), state))
                    last_state = state
                raise_if_abnormal(state, terminals, name)
                sleep(poll_interval)
        except (Stopped, AdvanceToNextCell):
            _safe_abort(ctx)
            raise
        finally:
            # Inside the `with`, so this runs before the entry finishes -- a
            # payload set afterwards has no timeline row to attach to (see
            # ActionLogEntry.set_details). And in a finally, so a stopped,
            # abandoned, or failed attempt retains its plot too, which is
            # exactly when an operator wants to read one.
            if teardownPlot is not None:
                teardownPlot()
            if recorder is not None:
                recorder.stop()
            if record:
                # recorder.stop() above must run first: the payload below names
                # the log file, and the file has to be flushed and closed before
                # anything is told where to find it.
                _setFsmDetails(
                    action_entry, entry_state, reached, transitions, recorder
                )


def patch(ctx, record_events: bool = True, record_full_test_pulses: bool = True, **entry_config) -> str:
    """Drive approach through detection, sealing, and break-in to a resting
    terminal state.

    `record_events` and `record_full_test_pulses` are this action's own options,
    consumed here and never forwarded to pip.setState; a protocol may expose
    them to its author. `record_events=False` opens no MultiPatchLogRecorder for
    this drive, so nothing is written to disk; `record_full_test_pulses=False`
    forwards to the recorder that does open, so it captures test-pulse analysis
    without the full waveform sidecar. Neither disables the Area 5 payload or its
    live plot -- turning off the disk-side recording they will draw from is not
    a reason to lose the pane; with no recorder the payload's history is simply
    empty. Only `clean` opts out of the payload and plot entirely.
    """
    return _drive_fsm(
        ctx,
        "Patch",
        "approach",
        # "cell attached" is not a resting state on these rigs: it exits via
        # spontaneous break-in (routed to "whole cell" by
        # spontaneousBreakInState) or spontaneous detachment (routed to
        # "fouled"), so it is an internal hop the poll continues through
        # rather than a patch outcome. autoBreakInDelay is an optional
        # wall-clock fallback that ships disabled (None) on both active rig
        # profiles.
        {"whole cell", "bath", "broken", "fouled"},
        entry_config,
        record_events=record_events,
        record_full_test_pulses=record_full_test_pulses,
    )


def reseal(ctx, record_events: bool = True, record_full_test_pulses: bool = True, **entry_config) -> str:
    """Reseal from whole-cell toward an outside-out patch, else fall back to
    whole cell.

    `record_events` and `record_full_test_pulses` are this action's own options,
    consumed here and never forwarded to pip.setState; a protocol may expose
    them to its author. `record_events=False` opens no MultiPatchLogRecorder for
    this drive, so nothing is written to disk; `record_full_test_pulses=False`
    forwards to the recorder that does open, so it captures test-pulse analysis
    without the full waveform sidecar. Neither disables the Area 5 payload or its
    live plot -- turning off the disk-side recording they will draw from is not
    a reason to lose the pane; with no recorder the payload's history is simply
    empty.
    """
    return _drive_fsm(
        ctx,
        "Reseal",
        "reseal",
        {"outside out", "whole cell"},
        entry_config,
        record_events=record_events,
        record_full_test_pulses=record_full_test_pulses,
    )


def clean(ctx, **entry_config) -> str:
    """Run the pipette-cleaning cycle and return once it settles at its resting
    state (``out``).

    Records nothing: there is nothing an operator reads off a clean (design doc
    §4.5), so it gets neither a details payload nor an event log.
    """
    return _drive_fsm(ctx, "Clean Pipette", "clean", {"out"}, entry_config, record=False)
