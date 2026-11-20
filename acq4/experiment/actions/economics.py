"""Economics action: measure what this slice has been yielding and pin it onto
the patch profile for the length of a block, so the patch states' stopping rule
runs on numbers rather than guesses."""
from __future__ import annotations

from ..exceptions import OrchestrationError
from ..slice_statistics import DEFAULT_MIN_CELLS, SealTerms, SliceStatistics
from .profile import change_patch_profile_params

_ACTION = "Tune Patch Economics"


def _stateManager():
    # Deferred: acq4.experiment must stay importable without the device packages.
    from acq4.devices.PatchPipette.statemanager import PatchPipetteStateManager

    return PatchPipetteStateManager


def _sealDefaultConfig():
    from acq4.devices.PatchPipette.states.seal import SealState

    return SealState.defaultConfig()


def _sliceDir(dirHandle):
    """The Slice directory above `dirHandle`, or None if there is not one.

    Walks up the way storage.create_data_dir does, and stops at the same depth:
    a managed tree is Day/Slice/Cell, so anything further up is not a slice this
    run belongs to.
    """
    check = dirHandle
    for _ in range(5):
        if check is None or not check.isManaged():
            return None
        if check.info().get("dirType") == "Slice":
            return check
        parent = check.parent()
        if parent is check:
            return None
        check = parent
    return None


def _profileDefaults(profile, manager) -> SealTerms:
    """The hand-set economics already configured on this profile's seal state.

    These are the cold-start values: what the rule runs on until the slice has
    enough finished cells to speak for itself. They live on the profile rather
    than in this module because that is where every other belief about patching
    this preparation already lives, which means an operator tunes them in the
    profile editor and a protocol can override them for a block.
    """
    config = dict(_sealDefaultConfig())
    config.update(manager.getProfileConfig(profile).get("seal") or {})
    return SealTerms(
        restart_cost=float(config.get("restartCost", 0.0)),
        seal_probability=float(config.get("sliceSealProbability", 0.0)),
        expected_seal_duration=float(config.get("expectedSealDuration", 0.0)),
        expected_failed_seal_duration=float(
            config.get("expectedFailedSealDuration", 0.0)
        ),
        probability_decay_tau=float(config.get("sealProbabilityDecayTau", 0.0)),
    )


def _minCells(ctx, min_cells):
    if min_cells is not None:
        return int(min_cells)
    misc = (getattr(ctx.manager, "config", None) or {}).get("misc") or {}
    return int(misc.get("minCellsForSliceStats", DEFAULT_MIN_CELLS))


def tune_patch_economics(
    ctx, profile: str | None = None, min_cells: int | None = None
):
    """Pin this slice's measured economics onto the patch profile, and return the
    scope that unpins them again.

        with tune_patch_economics(ctx):
            patch(ctx)

    What gets pinned is the seal state's view of this slice -- the odds a fresh
    cell seals, how long a seal takes when it works and when it does not, and the
    overhead of getting back into seal on another cell -- plus the reseal state's
    `prizeValue` for the cell in hand. Below `min_cells` finished cells the
    profile's own hand-set values are pinned back unchanged, so the rule always
    runs on *something* and an operator can see which.

    Worth calling twice in a protocol that reseals: before the patch the cell has
    no recording to be judged on and its prize value is 1, and only afterwards
    does its clamp quality exist to compare against the slice.

    `min_cells` defaults to the rig's `misc.minCellsForSliceStats`, then to
    DEFAULT_MIN_CELLS. `profile` defaults to the one this pipette's state manager
    is set to; profiles are shared, so this changes every pipette on it.

    Never fails over missing storage. A run outside a managed slice, or one whose
    storage cannot be reached, pins the profile's own values and says so -- the
    alternative is a protocol that cannot run at all because a directory was not
    where it was expected.
    """
    manager = _stateManager()
    if profile is None:
        profile = ctx.pipette.stateManager().getProfile()
        if profile is None:
            raise OrchestrationError(
                f"{_ACTION}: no patch profile is selected on {ctx.pipette.name()}"
            )
    defaults = _profileDefaults(profile, manager)
    min_cells = _minCells(ctx, min_cells)

    current = None
    try:
        current = ctx.manager.getCurrentDir()
    except Exception as exc:
        ctx.log(
            f"{_ACTION}: could not reach the storage directory ({exc}); "
            f"using the profile's own values"
        )
    sliceDir = _sliceDir(current)
    if sliceDir is None and current is not None:
        ctx.log(
            f"{_ACTION}: no slice directory above the current one; "
            f"using the profile's own values"
        )

    stats = SliceStatistics(dirHandle=sliceDir, defaults=defaults, min_cells=min_cells)
    terms = stats.sealTerms()
    try:
        cell_info = current.info() if current is not None else {}
    except Exception:
        cell_info = {}
    prize = stats.prizeValue(cell_info, terms)

    return change_patch_profile_params(
        ctx,
        {
            "seal": {
                "restartCost": terms.restart_cost,
                "sliceSealProbability": terms.seal_probability,
                "expectedSealDuration": terms.expected_seal_duration,
                "expectedFailedSealDuration": terms.expected_failed_seal_duration,
                # Pinned back as it was found: fitting a survival curve is the
                # offline calibration pass's job, and SliceStatistics never
                # measures this one.
                "sealProbabilityDecayTau": terms.probability_decay_tau,
            },
            "reseal": {"prizeValue": prize},
        },
        profile=profile,
    )
