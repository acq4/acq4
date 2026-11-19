"""Arm-time conflict checks between mutators, and install/uninstall of the tuning runtime."""

from dataclasses import dataclass, field
from itertools import combinations

from acq4.util import tuning_points
from acq4.util.tuning_points import POINTS, Runtime, TuningPointError

from .mutators.base import ProfileParamMutator, ScopeMutator, ValueMutator


@dataclass
class CheckResult:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def check(mutators) -> CheckResult:
    result = CheckResult()
    for m in mutators:
        if len(m.conditions) < 2:
            result.errors.append(
                f"{m.name}: needs at least two conditions, has {len(m.conditions)}"
            )
        if isinstance(m, ProfileParamMutator):
            names = [param for _, param in m.params]
            for param in sorted({p for p in names if names.count(p) > 1}):
                result.errors.append(f"{m.name}: param name {param!r} appears twice")
        if isinstance(m, ValueMutator):
            points, kind = m.answers, "value"
        elif isinstance(m, ScopeMutator):
            points, kind = m.wraps, "scope"
        else:
            result.errors.append(
                f"{m.name}: is neither a ValueMutator nor a ScopeMutator"
            )
            continue
        for point in sorted(points):
            if point not in POINTS:
                result.errors.append(f"{m.name}: unknown tuning point {point!r}")
            elif POINTS[point].kind != kind:
                result.errors.append(
                    f"{m.name}: a {kind} mutator cannot use {POINTS[point].kind} point {point!r}"
                )

    for a, b in combinations(mutators, 2):
        if isinstance(a, ValueMutator) and isinstance(b, ValueMutator):
            for point in sorted(a.answers & b.answers):
                result.errors.append(
                    f"{a.name} and {b.name} both answer value point {point!r}"
                )
        elif isinstance(a, ScopeMutator) and isinstance(b, ScopeMutator):
            both_profile = isinstance(a, ProfileParamMutator) and isinstance(
                b, ProfileParamMutator
            )
            if both_profile:
                for state, param in sorted(set(a.params) & set(b.params)):
                    result.errors.append(
                        f"{a.name} and {b.name} both set profile param {state}.{param}"
                    )
            else:
                for point in sorted(a.wraps & b.wraps):
                    result.warnings.append(
                        f"{a.name} and {b.name} both wrap scope point {point!r}"
                    )
    return result


def install(run_id, mutators, ledger, cell_close_hook=None):
    errors = check(mutators).errors
    if errors:
        raise TuningPointError("; ".join(errors))
    tuning_points.install(
        Runtime(run_id, mutators, ledger, cell_close_hook=cell_close_hook)
    )


def uninstall():
    tuning_points.uninstall()


def refuse_reason(orchestrator_running, slice_dir):
    if orchestrator_running:
        return "the orchestrator is running"
    if slice_dir is None:
        return "no slice directory: press New slice"
    if "__uuid__" not in slice_dir.info():
        return "slice directory has no uuid (made before uuids): press New slice"
    return None


def _orchestrator_running(window):
    return window.orchestrator is not None and window.orchestrator.isRunning()


def arm(window, run_id, mutators, ledger, cell_close_hook=None):
    slice_dir = window.slice.dirHandle if window.slice is not None else None
    reason = refuse_reason(_orchestrator_running(window), slice_dir)
    if reason is not None:
        raise TuningPointError(reason)
    install(run_id, mutators, ledger, cell_close_hook=cell_close_hook)
    window._tuningSliceUnit = tuning_points.open_unit("slice", slice_dir=slice_dir)


def disarm(window):
    if _orchestrator_running(window):
        raise TuningPointError("the orchestrator is running")
    release(window)


def release(window):
    """Close the window's slice unit and uninstall, without the running check; for callers that have stopped the run."""
    tuning_points.close_unit(window._tuningSliceUnit)
    window._tuningSliceUnit = None
    uninstall()
