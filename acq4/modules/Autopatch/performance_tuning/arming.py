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
                for state, param in sorted(
                    set(a.params.items()) & set(b.params.items())
                ):
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
    return None
