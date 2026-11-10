"""FSM-driving actions: drive acq4's PatchPipette state machine from a declared
entry state to one of this action's declared terminal states, mapping unexpected
abnormal states to orchestration exceptions, and retaining each drive's
test-pulse analysis and state transitions for Area 5."""
from __future__ import annotations

import os
import time

import numpy as np

from acq4.util import Qt
from acq4.util.multipatch_log_writer import MultiPatchLogWriter
from acq4.util.task import Empty, Queue, Stopped, check_stop, run_in_gui_thread

from ..exceptions import AdvanceToNextCell, raise_if_abnormal
from ..tube_ids import tube_position


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


def _testPulseHistory(writer):
    """The test-pulse analysis rows `writer` accumulated, or an empty array of the
    same dtype when there is no writer -- so every reader has one shape to handle
    rather than two.
    """
    # Deferred rather than joining the top-of-file imports: importing anything
    # from acq4.filetypes runs that package's __init__, which eagerly imports
    # and registers every sibling FileType module (acq4/filetypes/filetypes.py's
    # module-level listFileTypes() call). Keeping it here means that cost is
    # paid only when a payload is actually being built, not by every import of
    # this module.
    from acq4.filetypes.MultiPatchLog import TEST_PULSE_NUMPY_DTYPE

    if writer is None:
        return np.empty(0, dtype=TEST_PULSE_NUMPY_DTYPE)
    # The writer's own accumulated rows, not clampDevice.testPulseHistory():
    # the device's history is reset mid-patch (approach.py:251), so slicing
    # it by this drive's time window would silently lose whatever preceded
    # the reset. The live plot in _openLivePlot reads the device instead,
    # deliberately, because a live view of "now" should show its own
    # current history.
    return writer.testPulseAnalysis()


# Outcome-record key -> the test-pulse analysis field it averages. `holding_current`
# is renamed from the clamp's own `baseline_current` because the record is read
# alongside the rest of a cell's index by people, not by the clamp.
_QUALITY_FIELDS = {
    "access_resistance": "access_resistance",
    "input_resistance": "input_resistance",
    "capacitance": "capacitance",
    "holding_current": "baseline_current",
}


def _stateDuration(transitions, state) -> float | None:
    """How long `state` ran, from its own entry to the next transition.

    None when the state was never entered, and None when the drive ended inside
    it: such an episode has a lower bound rather than a duration, and reporting
    the bound as a duration would make every interrupted attempt look like a fast
    one to whatever averages these.

    The first visit, not the last. One cell is one attempt, so a second visit is
    not expected -- but a log that holds one is reporting something other than
    this attempt's episode.
    """
    for i, (when, name) in enumerate(transitions):
        if name == state:
            if i + 1 < len(transitions):
                return float(transitions[i + 1][0] - when)
            return None
    return None


def _stateEntryTime(transitions, state) -> float | None:
    """When `state` was entered, in wall-clock seconds, or None if it never was.

    Absolute rather than relative to the drive, because what reads it compares it
    against *other cells'* episodes: the gap from one seal ending to the next
    beginning is how the restart overhead is measured.
    """
    return next((float(when) for when, name in transitions if name == state), None)


def _clampQuality(history, transitions) -> dict:
    """Mean clamp quality over the test pulses recorded after whole-cell was
    reached: what the recording this attempt won was actually like.

    Empty when no whole-cell was reached or no pulse followed it -- there is no
    recording to judge, and a zero here would be read as a measured zero.

    NaN measurements are dropped per field rather than per row. A test pulse with
    no transient to fit reports NaN, and averaging one in would poison every field
    it touched; dropping the whole row instead would discard the fields that did
    fit. A field that is NaN throughout is omitted, for the same reason an absent
    whole-cell is.
    """
    start = next((when for when, name in transitions if name == "whole cell"), None)
    if start is None or len(history) == 0:
        return {}
    fields = history.dtype.names or ()
    if "event_time" not in fields:
        return {}
    rows = history[history["event_time"] >= start]
    if len(rows) == 0:
        return {}
    quality = {}
    for key, field in _QUALITY_FIELDS.items():
        if field not in fields:
            continue
        values = rows[field]
        values = values[~np.isnan(values)]
        if len(values) > 0:
            quality[key] = float(np.mean(values))
    return quality


def _patchOutcomeInfo(reached, transitions, history, patch_record) -> dict:
    """This attempt's outcome, as plain scalars for the Cell directory's index.

    Scalars only, and every one converted: the .index is written with repr() and
    read back with eval(), so a numpy scalar left in here is written as a tagged
    object that no plain reader can load.

    `sealed` and `break_in_succeeded` come from the pipette's own patch record
    rather than from the states walked, because the record is what the states
    themselves set when they decided. `reached` is consulted for break-in as well,
    since a spontaneous break-in routes straight to whole cell without the break-in
    state ever reporting on itself.
    """
    record = patch_record or {}
    info = {
        "patch_outcome": str(reached) if reached is not None else "unknown",
        "sealed": bool(record.get("sealSuccessful")),
        "break_in_succeeded": bool(
            record.get("breakinSuccessful")
            or record.get("spontaneousBreakin")
            or reached == "whole cell"
        ),
        "give_up_reason": str(record.get("sealGiveUpReason") or "none"),
    }
    entered = _stateEntryTime(transitions, "seal")
    if entered is not None:
        info["seal_entered_at"] = entered
    duration = _stateDuration(transitions, "seal")
    if duration is not None:
        info["seal_duration_s"] = duration
    info.update(_clampQuality(history, transitions))
    return info


def _resealOutcomeInfo(reached, transitions, patch_record=None) -> dict:
    """The reseal drive's equivalent of _patchOutcomeInfo. No clamp quality: the
    recording being judged happened before the reseal, and is recorded by the
    patch drive that won it.
    """
    record = patch_record or {}
    info = {
        "reseal_outcome": str(reached) if reached is not None else "unknown",
        "reseal_give_up_reason": str(record.get("resealGiveUpReason") or "none"),
    }
    duration = _stateDuration(transitions, "reseal")
    if duration is not None:
        info["reseal_duration_s"] = duration
    return info


def _patchOutcome(reached, transitions, history, pip) -> dict:
    return _patchOutcomeInfo(
        reached, transitions, history, pip.patchRecord() if pip is not None else {}
    )


def _resealOutcome(reached, transitions, _history, pip) -> dict:
    return _resealOutcomeInfo(
        reached, transitions, pip.patchRecord() if pip is not None else {}
    )


def _recordPatchOutcome(ctx, info) -> None:
    """Write an outcome record onto the cell's own data directory index.

    Never raises, for the reason _recordNucleusTube does not: the cell has
    already been patched by the time this runs, and an unset storage directory or
    an unwritable index must not turn a finished attempt into a failed run.

    NOTE this is the orchestrator's job by rights -- it owns the cell's lifecycle
    -- and is done here because nothing lets the orchestrator see an action's
    result. See `(seal-economics-outcome-record)` in docs/architecture-friction.md.
    """
    if not info:
        return
    try:
        ctx.manager.getCurrentDir().setInfo(**info)
    except Exception as exc:
        ctx.log(f"could not record this cell's patch outcome: {exc}")


def _setFsmDetails(action_entry, entry_state, reached, transitions, writer=None) -> None:
    """Retain this drive's Area 5 payload: the test-pulse analysis observed
    during it, and the states it walked.

    An empty history rather than None when there is no writer, so the renderer
    has one payload shape to handle rather than two.
    """
    history = _testPulseHistory(writer)
    if writer is None:
        log_file = None
    else:
        log_file = writer.logFileName()
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


def _openWriter(ctx, record_full_test_pulses: bool):
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
            # Deliberately clamp.testPulseHistory(), not the writer's: a live
            # view of "now" should show the device's own current history. The
            # frozen payload below reads the writer instead, because the
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
    outcome_info=None,
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

    `outcome_info`, when given, is called as
    `(reached, transitions, history, pipette)` once the drive has ended and is
    expected to return the plain-scalar outcome record for the cell's own data
    directory index. Independent of `record`: the outcome record is what the
    slice statistics read, while `record` governs what an operator reads.

    `pausable` governs only the boundary *before* the drive starts. Nothing
    pauses once the FSM is driving: it runs on its own thread, so holding this
    poll loop would park the observer while the pipette kept going.
    """
    with ctx.log_action(name, pausable=pausable) as action_entry:
        pip = ctx.pipette
        action_entry.set_status(f"driving FSM from {entry_state!r}")
        # Initialised before the try so the finally can tear down whatever opened.
        writer = None
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
                writer = _openWriter(ctx, record_full_test_pulses)
            if record:
                try:
                    teardownPlot = _openLivePlot(ctx, action_entry)
                except Exception as exc:
                    # A display failure must not fail the patch attempt.
                    ctx.log(f"could not start live plot: {exc}")
            # DirectConnection: states arrive on whichever thread changes them.
            # PatchPipette emits each state_change event (which the writer
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
            if writer is not None:
                try:
                    writer.stop()
                except Exception as exc:
                    ctx.log(f"could not stop event recording: {exc}")
            if record:
                # After stop(), so the log file named in the payload is complete.
                try:
                    _setFsmDetails(
                        action_entry, entry_state, reached, transitions, writer
                    )
                except Exception as exc:
                    ctx.log(f"could not retain test-pulse details: {exc}")
            if outcome_info is not None:
                # After stop(), for the reason the details payload is: the
                # writer's final rows are what the clamp quality averages over.
                try:
                    _recordPatchOutcome(
                        ctx,
                        outcome_info(
                            reached, transitions, _testPulseHistory(writer), pip
                        ),
                    )
                except Exception as exc:
                    ctx.log(f"could not record this cell's outcome: {exc}")


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
        outcome_info=_patchOutcome,
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
        outcome_info=_resealOutcome,
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


def home_with_nucleus(ctx, **entry_config) -> str:
    """Carry an outside-out nucleus back to the home position under negative
    pressure, and return once the pipette settles at ``out``.

    Records nothing, for the reason `clean` does not: there is nothing an
    operator reads off the trip home.
    """
    return _drive_fsm(
        ctx,
        "Home With Nucleus",
        "home with nucleus",
        {"out"},
        entry_config,
        record=False,
    )


def collect(ctx, mark_used: bool = True, **entry_config) -> str:
    """Deposit the nucleus into this pipette's nucleus site and return once the
    pipette settles at ``out``.

    With `mark_used` (this action's own option, consumed here and never
    forwarded to pip.setState), the deposited-into site is marked used up and
    the cell's data directory records which tube it went into. Unset, the drive
    runs and nothing else happens.

    ``out`` is this action's only declared terminal, so a drive that ends any
    other way raises out of _drive_fsm and never reaches the marking: a tube
    that did not receive a nucleus is never consumed.

    The site is resolved here as well as inside NucleusCollectState, which
    resolves it again when it runs. The two agree because getFirstAvailableSite
    is deterministic and nothing mutates used_up between the calls; a second
    pipette depositing into the same rack concurrently would break that.
    """
    site = ctx.pipette.pipetteDevice.getSiteFor("nucleus") if mark_used else None
    reached = _drive_fsm(ctx, "Collect Nucleus", "collect", {"out"}, entry_config)
    if site is not None:
        site.used_up = True
        _recordNucleusTube(ctx, site)
    return reached


def _recordNucleusTube(ctx, site) -> None:
    """Record on the cell's data directory which tube its nucleus went into.

    Never raises, for the reason storage.mark_important does not: the nucleus is
    already in the tube by the time this runs, and an unset storage directory or
    an unwritable index must not turn a successful deposit into a failed run.
    """
    try:
        ctx.manager.getCurrentDir().setInfo(
            {
                "nucleus_tube_id": site.tube_id or "",
                "nucleus_tube_position": tube_position(site),
            }
        )
    except Exception as exc:
        ctx.log(f"could not record the nucleus tube: {exc}")
