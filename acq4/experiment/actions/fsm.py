"""FSM-driving actions: drive acq4's PatchPipette state machine from a declared
entry state to one of this action's declared terminal states, mapping unexpected
abnormal states to orchestration exceptions."""
from __future__ import annotations

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


def _drive_fsm(ctx, name, entry_state, terminals, entry_config=None, poll_interval=0.1) -> str:
    """Drive the PatchPipette FSM from entry_state and return the terminal state
    it reaches. Abnormal states not in `terminals` raise (see raise_if_abnormal)."""
    with ctx.log_action(name) as action_entry:
        pip = ctx.pipette
        action_entry.set_status(f"driving FSM from {entry_state!r}")
        last_state = entry_state
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
                    return state
                if state != last_state:
                    # Only on change: re-setting the same string every poll
                    # would spam the UI callback for no new information, and
                    # would hide a pipette parked in a non-terminal state
                    # (e.g. "cell attached") behind a stale row otherwise.
                    action_entry.set_status(f"now in {state!r}")
                    last_state = state
                raise_if_abnormal(state, terminals, name)
                sleep(poll_interval)
        except (Stopped, AdvanceToNextCell):
            _safe_abort(ctx)
            raise


def patch(ctx, **entry_config) -> str:
    """Drive approach through detection, sealing, and break-in to a resting
    terminal state."""
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
    )


def reseal(ctx, **entry_config) -> str:
    """Reseal from whole-cell toward an outside-out patch, else fall back to
    whole cell."""
    return _drive_fsm(ctx, "Reseal", "reseal", {"outside out", "whole cell"}, entry_config)


def clean(ctx, **entry_config) -> str:
    """Run the pipette-cleaning cycle and return once it settles at its resting
    state (``out``)."""
    return _drive_fsm(ctx, "Clean Pipette", "clean", {"out"}, entry_config)
