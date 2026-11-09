"""Patch-profile action: change the configuration the patch states run under for
as long as a protocol needs it changed."""
from __future__ import annotations

from copy import deepcopy

from ..exceptions import OrchestrationError

# Stands in for a parameter the profile does not pin, which is not the same thing
# as one pinned to None: an unpinned parameter inherits, so restoring it means
# taking its key back out rather than writing a value into it.
_UNPINNED = object()

_CHANGE = "Change Patch Profile Params"
_RESTORE = "Restore Patch Profile Params"


def _stateManager():
    # Deferred rather than imported at the top of this module, for the reason
    # actions.fsm defers its pipetteControl import: acq4.experiment must stay
    # importable without the device packages.
    from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager

    return PatchPipetteStateManager


def _profileConfig(manager, profile, action_name):
    try:
        return deepcopy(manager.getProfileConfig(profile))
    except KeyError as exc:
        available = ", ".join(sorted(manager.listProfiles())) or "none are configured"
        raise OrchestrationError(
            f"{action_name}: unknown patch profile {profile!r} (available: {available})"
        ) from exc


def _store(manager, profile, config, action_name):
    """Write `config` back as `profile`, the way an operator editing the profile
    tree does.

    addProfile validates a whole configuration before storing any of it, so a
    parameter this action cannot set leaves the profile exactly as it was.
    """
    try:
        manager.addProfile(profile, config, overwrite=True)
    except ValueError as exc:
        raise OrchestrationError(f"{action_name}: {exc}") from exc


class PatchProfileParamChange:
    """A change made to a patch profile, and the means to put it back.

    What change_patch_profile_params returns. The change is applied by that
    call, not by entering this; what entering a `with` buys is the restore on
    the way out.
    """

    def __init__(self, ctx, profile, previous, created_states):
        self._ctx = ctx
        self._profile = profile
        self._previous = previous
        self._created_states = created_states

    def __enter__(self) -> "PatchProfileParamChange":
        return self

    def __exit__(self, *exc_info) -> bool:
        self.restore()
        return False

    def restore(self) -> None:
        """Put this change's parameters back the way they were.

        Parameter by parameter against the profile as it stands now, rather than
        by restoring the configuration wholesale: an operator may have edited the
        same profile while the protocol ran, and this action putting its own
        parameters back is no reason to undo theirs.

        Its log entry is not a pause boundary. The body it is unwinding has
        already finished, and on the failing path a pause honored here would
        raise in place of whatever exception is propagating.
        """
        manager = _stateManager()
        with self._ctx.log_action(_RESTORE, pausable=False) as action_entry:
            config = _profileConfig(manager, self._profile, _RESTORE)
            lines = []
            for state, params in self._previous.items():
                state_config = config.setdefault(state, {})
                for name, value in params.items():
                    if value is _UNPINNED:
                        state_config.pop(name, None)
                        lines.append(f"{state}.{name}: unpinned")
                    else:
                        state_config[name] = value
                        lines.append(f"{state}.{name} = {value!r}")
                if state in self._created_states and not state_config:
                    del config[state]
            _store(manager, self._profile, config, _RESTORE)
            action_entry.set_details("text", {"lines": [self._profile] + lines})


def change_patch_profile_params(
    ctx, params: dict, profile: str | None = None
) -> PatchProfileParamChange:
    """Pin patch-state parameters on a patch profile, and return the scope that
    unpins them again.

        with change_patch_profile_params(ctx, {"seal": {"autoSealTimeout": 12.0}}):
            patch(ctx)

    `params` is keyed by patch state name, then by that state's parameter name --
    the same shape a profile is configured with. The change is applied by this
    call and undone by leaving the `with`, parameter by parameter (see
    PatchProfileParamChange.restore). Calling this without a `with` therefore
    pins the parameters for good, which is the same thing an operator typing
    them into the profile editor does.

    `profile` names the profile to change; by default it is the one this
    pipette's state manager is set to, which is the profile a patch run by this
    protocol will actually use. Changing a profile changes it for every pipette
    on it, not just this one.

    Everything watching the profile store sees the change -- an open profile
    editor follows it, and the MultiPatch log records it -- the same as if it had
    been typed in.
    """
    manager = _stateManager()
    if profile is None:
        profile = ctx.pipette.stateManager().getProfile()
        if profile is None:
            raise OrchestrationError(
                f"{_CHANGE}: no patch profile is selected on {ctx.pipette.name()}"
            )
    with ctx.log_action(_CHANGE) as action_entry:
        config = _profileConfig(manager, profile, _CHANGE)
        created_states = {state for state in params if state not in config}
        previous = {}
        lines = []
        for state, values in params.items():
            before = config.get(state, {})
            previous[state] = {name: before.get(name, _UNPINNED) for name in values}
            for name, value in values.items():
                was = previous[state][name]
                shown = "unpinned" if was is _UNPINNED else repr(was)
                lines.append(f"{state}.{name}: {shown} -> {value!r}")
            config.setdefault(state, {}).update(values)
        _store(manager, profile, config, _CHANGE)
        action_entry.set_details("text", {"lines": [profile] + lines})
    return PatchProfileParamChange(ctx, profile, previous, created_states)
