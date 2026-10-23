"""FSM-driving actions: drive acq4's PatchPipette state machine from a declared
entry state to one of this action's declared terminal states, mapping unexpected
abnormal states to orchestration exceptions, and retaining each drive's
test-pulse analysis and state transitions for Area 5."""
from __future__ import annotations

import os
import time

import numpy as np

from acq4.util import Qt
from acq4.util.multipatch_log_recorder import MultiPatchLogWriter
from acq4.util.task import Empty, Queue, Stopped, check_stop, run_in_gui_thread

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
    """Start a MultiPatchLogWriter for this drive's pipette in the current storage
    directory, or return None if it could not be started.

    Never raises: a failure to record must not stop a patch attempt. The reason
    goes to the cell's log instead.
    """
    pip = ctx.pipette
    try:
        return MultiPatchLogWriter(
            ctx.manager.getCurrentDir(),
            pipettes=(pip,),
            full_test_pulse_pipettes=(pip,) if record_full_test_pulses else (),
        ).start()
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

    Built and connected through run_in_gui_thread because this runs on the
    orchestrator's worker thread: a widget must not be constructed off the GUI
    thread, and PyQt gives a plain callable slot the affinity of the thread that
    called connect(). Connecting from the worker thread -- which is a gentletask
    ThreadTask with no Qt event loop -- would queue every test pulse to a thread
    that never pumps events, so the plot would mount and never update.
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

        def onTestPulse(_device, testPulse):
            # Deliberately clamp.testPulseHistory(), not the recorder's: a live
            # view of "now" should show the device's own current history. The
            # frozen payload below reads the recorder instead, because the
            # device's history is reset mid-patch (approach.py:251) and would
            # silently lose whatever preceded the reset -- see _setFsmDetails.
            widget.newTestPulse(testPulse, clamp.testPulseHistory())

        # Default (queued) connection deliberately: PatchPipetteState connects
        # to this same signal with an explicit DirectConnection, which is
        # correct for a state machine and wrong for a widget -- it would mutate
        # the plot from the clamp's thread.
        clamp.sigTestPulseFinished.connect(onTestPulse)
        return widget, onTestPulse

    widget, onTestPulse = run_in_gui_thread(build)

    def teardown():
        # A live connection from a device signal into a widget the panel has
        # moved on from is the cross-module reference neither Autopatch's widget
        # -tree teardown nor unbindOrchestrator reaches (design doc §4.5).
        Qt.disconnect(clamp.sigTestPulseFinished, onTestPulse)

    try:
        action_entry.set_details_widget(widget)
    except Exception:
        # The connection is live but the caller never receives the teardown that
        # would drop it, so nothing else would ever disconnect the clamp from
        # this now-ownerless widget. Drop it here before the failure propagates.
        teardown()
        raise

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
    pausable=True,
) -> str:
    """Drive the PatchPipette FSM from entry_state and return the terminal state
    it reaches. Abnormal states not in `terminals` raise (see raise_if_abnormal).

    With `record` true, this action retains a "test_pulse_history" details
    payload for Area 5 -- the test-pulse analysis observed during the drive, and
    the pipette states it walked -- and mounts the live Rss plot. `clean` passes
    `record=False`, which short-circuits both regardless of record_events (clean
    has no record_events parameter): there is nothing an operator reads off a
    clean (design doc §4.5).

    With `record` true, `record_events` starts a MultiPatchLogWriter for the
    drive's events; `record_full_test_pulses` makes it also save the full test
    pulses (meaningless without `record_events`). Neither affects the Area 5
    payload or plot; without an event log the payload's history is empty.

    States are followed through pip.sigStateChanged, subscribed before the entry
    state is requested, so every transition is seen however briefly it lasts.
    `poll_interval` bounds how long a stop or next-cell request waits to be noticed.

    `pausable` governs only the boundary *before* the drive starts. Nothing
    pauses once the FSM is driving: it runs on its own thread, so holding this
    poll loop would park the observer while the pipette kept going.
    """
    with ctx.log_action(name, pausable=pausable) as action_entry:
        pip = ctx.pipette
        action_entry.set_status(f"driving FSM from {entry_state!r}")
        # Initialised before the try so the finally can tear down whatever opened.
        recorder = None
        teardownPlot = None
        states = Queue()

        def onStateChanged(_pip, state, _oldState):
            states.put((time.time(), state))

        connected = False
        # (timestamp, state) for the entry state and every transition after it.
        # Reading a failed patch is mostly "where did it stall", and this answers it.
        transitions = []
        reached = None
        try:
            if record and record_events:
                recorder = _openRecorder(ctx, record_full_test_pulses)
            if record:
                try:
                    teardownPlot = _openLivePlot(ctx, action_entry)
                except Exception as exc:
                    # A display failure must not fail the patch attempt.
                    ctx.log(f"could not start live plot: {exc}")
            # DirectConnection: states arrive on whichever thread changes them.
            # PatchPipette emits each state_change event (which the recorder
            # queues) before sigStateChanged, so a terminal state seen here is
            # already queued for the log.
            pip.sigStateChanged.connect(onStateChanged, Qt.Qt.DirectConnection)
            connected = True
            # Fresh dict per call so no caller shares a mutable default.
            pip.setState(entry_state, **dict(entry_config or {}))
            entered = False
            while True:
                check_stop()
                if ctx.next_cell_requested():
                    ctx.next_cell()
                try:
                    when, state = states.get(timeout=poll_interval)
                except Empty:
                    continue
                if not entered:
                    # Anything before the entry state's own change (e.g. an old
                    # job finishing as it was replaced) belongs to no drive.
                    if state != entry_state:
                        continue
                    entered = True
                elif state not in terminals:
                    action_entry.set_status(f"now in {state!r}")
                transitions.append((when, state))
                if state in terminals:
                    action_entry.set_status(f"reached {state!r}")
                    reached = state
                    return state
                raise_if_abnormal(state, terminals, name)
        except (Stopped, AdvanceToNextCell):
            _safe_abort(ctx)
            raise
        finally:
            # Inside the `with`, so this runs before the entry finishes -- a
            # payload set afterwards has no timeline row to attach to (see
            # ActionLogEntry.set_details). And in a finally, so a stopped,
            # abandoned, or failed attempt retains its plot too, which is
            # exactly when an operator wants to read one.
            #
            # Each step guarded independently: a raise here would skip the
            # remaining teardown and replace any exception already propagating.
            if connected:
                try:
                    Qt.disconnect(pip.sigStateChanged, onStateChanged)
                except Exception as exc:
                    ctx.log(f"could not stop following pipette states: {exc}")
            if teardownPlot is not None:
                try:
                    teardownPlot()
                except Exception as exc:
                    ctx.log(f"could not tear down live plot: {exc}")
            if recorder is not None:
                try:
                    recorder.stop()
                except Exception as exc:
                    ctx.log(f"could not stop event recording: {exc}")
            if record:
                # After stop(), so the log file named in the payload is complete.
                try:
                    _setFsmDetails(
                        action_entry, entry_state, reached, transitions, recorder
                    )
                except Exception as exc:
                    ctx.log(f"could not retain test-pulse details: {exc}")


def patch(ctx, record_events: bool = True, record_full_test_pulses: bool = True, **entry_config) -> str:
    """Drive approach through detection, sealing, and break-in to a resting
    terminal state.

    `record_events` and `record_full_test_pulses` are this action's own options,
    consumed here and never forwarded to pip.setState; a protocol may expose
    them to its author. `record_events` starts the drive's event log and
    `record_full_test_pulses` adds its full-test-pulse sidecar, which needs the
    event log (see _drive_fsm); neither disables the Area 5 payload or its live
    plot.
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
        # The tip is already parked at the target in tissue; a pause requested
        # during the approach is honored at the next action instead.
        pausable=False,
    )


def reseal(ctx, record_events: bool = True, record_full_test_pulses: bool = True, **entry_config) -> str:
    """Reseal from whole-cell toward an outside-out patch, else fall back to
    whole cell.

    `record_events` and `record_full_test_pulses` are this action's own options,
    consumed here and never forwarded to pip.setState; a protocol may expose
    them to its author. `record_events` starts the drive's event log and
    `record_full_test_pulses` adds its full-test-pulse sidecar, which needs the
    event log (see _drive_fsm); neither disables the Area 5 payload or its live
    plot.
    """
    return _drive_fsm(
        ctx,
        "Reseal",
        "reseal",
        {"outside out", "whole cell"},
        entry_config,
        record_events=record_events,
        record_full_test_pulses=record_full_test_pulses,
        # Entered holding a cell in whole cell; as with patch, not a boundary
        # to hold at.
        pausable=False,
    )


def _tipReportsClean(ctx) -> bool:
    """Whether the pipette says its own tip is still clean.

    "Clean" here is the PatchPipette's own bookkeeping flag (isTipClean), not a
    measurement of anything. It starts True on a freshly constructed device and
    on newPipette(); the clean state's success path sets it back to True
    alongside bumping cleanCount and starting a fresh patch attempt; and it is
    set False by the two states that dirty a tip against tissue -- `seal`, once
    it has actually sealed onto a cell, and `fouled`. An operator can also set
    it by hand from MultiPatch's "fouled" checkbox. So a tip reads dirty
    exactly when this pipette has been onto a cell since its last clean, which
    is the question a start-of-run clean wants answered.

    No pipette to ask reads as *not* clean rather than as clean: this flag is
    the only thing that can authorize skipping a cleaning cycle, and a context
    carrying no pipette has nothing to authorize it with. That leaves a
    pipette-less clean() failing exactly the way it always has -- in _drive_fsm,
    on the pipette it does not have -- rather than letting a mis-built context
    turn into a step that silently did nothing.
    """
    pip = getattr(ctx, "pipette", None)
    if pip is None:
        return False
    return bool(pip.isTipClean())


def clean(ctx, only_if_needed: bool = False, **entry_config) -> str:
    """Run the pipette-cleaning cycle and return once it settles at its resting
    state (``out``).

    `only_if_needed` is this action's own option, consumed here and never
    forwarded to pip.setState -- the same convention `patch`/`reseal` follow for
    their recording options. Set, it asks the pipette whether its tip is still
    clean (see _tipReportsClean) and skips the cycle when the answer is yes;
    unset, it cleans whatever the pipette reports, which is what forcing a clean
    looks like.

    It defaults to False -- unconditional -- even though the start of a run
    wants the conditional form. `clean()` has always cleaned when called, and a
    default that silently skipped would change what every existing protocol's
    existing clean() call does without that protocol being touched, on a rig
    where the cost of a wrongly skipped clean is a fouled tip driven at tissue.
    A protocol that wants the check therefore asks for it at its own call site,
    where an operator reading the protocol can see that it is being asked.

    A skipped cycle still opens the same "Clean Pipette" entry and finishes it
    saying it was skipped. Area 5 is the operator's account of what the run
    actually did, and an action that produced no row at all reads as one that
    never ran rather than one that was not needed. The skip returns the same
    ``out`` the drive returns, so a protocol reading the result has one string
    to compare against either way; that string names this action's declared
    terminal state, not a claim about where the pipette is now -- a skipped
    clean moves nothing.

    Records nothing: there is nothing an operator reads off a clean (design doc
    §4.5), so it gets neither a details payload nor an event log.
    """
    name = "Clean Pipette"
    if only_if_needed and _tipReportsClean(ctx):
        # The skip opens its own entry here, rather than the check living inside
        # _drive_fsm: _drive_fsm opens (and finishes) the only other entry this
        # action can produce, and the two paths are mutually exclusive, so one
        # clean is one row whichever way it goes. A check wrapped *around* the
        # drive would report two.
        with ctx.log_action(name) as action_entry:
            action_entry.set_status("skipped: pipette reports a clean tip")
        return "out"
    return _drive_fsm(ctx, name, "clean", {"out"}, entry_config, record=False)
