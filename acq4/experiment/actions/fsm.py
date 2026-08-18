"""FSM-driving actions: drive acq4's PatchPipette state machine from a declared
entry state to one of this action's declared terminal states, mapping unexpected
abnormal states to orchestration exceptions, and retaining each drive's
test-pulse analysis and state transitions for Area 5."""
from __future__ import annotations

import os
import time

import numpy as np

from acq4.util.task import Stopped, check_stop, sleep

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
    from acq4.filetypes.MultiPatchLog import TEST_PULSE_NUMPY_DTYPE

    if recorder is None:
        history = np.empty(0, dtype=TEST_PULSE_NUMPY_DTYPE)
        log_file = None
    else:
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


def _drive_fsm(
    ctx,
    name,
    entry_state,
    terminals,
    entry_config=None,
    poll_interval=0.1,
    record=True,
    record_full_test_pulses=True,
) -> str:
    """Drive the PatchPipette FSM from entry_state and return the terminal state
    it reaches. Abnormal states not in `terminals` raise (see raise_if_abnormal).

    With `record` true, this action also retains a "test_pulse_history" details
    payload for Area 5 -- the test-pulse analysis observed during the drive, and
    the pipette states it walked. `clean` passes false: there is nothing an
    operator reads off a clean (design doc §4.5).
    """
    with ctx.log_action(name) as action_entry:
        pip = ctx.pipette
        action_entry.set_status(f"driving FSM from {entry_state!r}")
        last_state = entry_state
        # (timestamp, state) for the entry state and every change the poll loop
        # observes. Reading a failed patch is mostly "where did it stall", and
        # this is what answers it; the loop already detects the changes.
        transitions = [(time.time(), entry_state)]
        reached = None
        try:
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
            if record:
                _setFsmDetails(action_entry, entry_state, reached, transitions)


def patch(ctx, record_events: bool = True, record_full_test_pulses: bool = True, **entry_config) -> str:
    """Drive approach through detection, sealing, and break-in to a resting
    terminal state.

    `record_events` and `record_full_test_pulses` are this action's own options,
    consumed here and never forwarded to pip.setState; a protocol may expose
    them to its author. See _drive_fsm for what they control. Neither disables
    the Area 5 payload -- turning off the disk-side recording they will govern
    is not a reason to lose the pane's plot; only `clean` opts out of that.
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
        record_full_test_pulses=record_full_test_pulses,
    )


def reseal(ctx, record_events: bool = True, record_full_test_pulses: bool = True, **entry_config) -> str:
    """Reseal from whole-cell toward an outside-out patch, else fall back to
    whole cell."""
    return _drive_fsm(
        ctx,
        "Reseal",
        "reseal",
        {"outside out", "whole cell"},
        entry_config,
        record_full_test_pulses=record_full_test_pulses,
    )


def clean(ctx, **entry_config) -> str:
    """Run the pipette-cleaning cycle and return once it settles at its resting
    state (``out``).

    Records nothing: there is nothing an operator reads off a clean (design doc
    §4.5), so it gets neither a details payload nor an event log.
    """
    return _drive_fsm(ctx, "Clean Pipette", "clean", {"out"}, entry_config, record=False)
