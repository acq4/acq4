"""FSM-driving actions: drive acq4's PatchPipette state machine from a declared
entry state to one of this action's declared terminal states, mapping unexpected
abnormal states to orchestration exceptions."""
from __future__ import annotations

from acq4.util.task import check_stop, sleep

from ..exceptions import raise_if_abnormal


def _drive_fsm(ctx, name, entry_state, terminals, entry_config=None, poll_interval=0.1) -> str:
    """Drive the PatchPipette FSM from entry_state and return the terminal state
    it reaches. Abnormal states not in `terminals` raise (see raise_if_abnormal)."""
    with ctx.log_action(name) as entry:
        pip = ctx.pipette
        entry.set_status(f"driving FSM from {entry_state!r}")
        try:
            # Fresh dict per call so no caller shares a mutable default.
            pip.setState(entry_state, **dict(entry_config or {}))
            while True:
                check_stop()
                state = pip.getState().stateName
                if state in terminals:
                    entry.set_status(f"reached {state!r}")
                    return state
                raise_if_abnormal(state, terminals, name)
                sleep(poll_interval)
        finally:
            # Mirror the MultiPatch "Cancel" button (pipetteControl._cancelClicked):
            # stop the current FSM state's job, which switches the pipette to that
            # state's declared fallback state rather than forcing a single hard-coded
            # holding state.
            pip = getattr(ctx, "pipette", None)
            if pip is not None:
                state_job = pip.getState()
                if state_job is not None:
                    state_job.stop("orchestration abort", wait=True)


def patch(ctx, **entry_config) -> str:
    """Drive approach through detection, sealing, and break-in to a resting
    terminal state."""
    return _drive_fsm(
        ctx,
        "Patch",
        "approach",
        {"whole cell", "cell attached", "bath", "broken", "fouled"},
        entry_config,
    )


def reseal(ctx, **entry_config) -> str:
    """Reseal from whole-cell toward an outside-out patch, else fall back to
    whole cell."""
    return _drive_fsm(ctx, "Reseal", "reseal", {"outside out", "whole cell"}, entry_config)


def clean(ctx, **entry_config) -> str:
    """Run the pipette-cleaning cycle and return once it settles at its resting
    state (``out``)."""
    return _drive_fsm(ctx, "Clean", "clean", {"out"}, entry_config)
