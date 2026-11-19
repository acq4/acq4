"""Registry and call API for performance tuning points; inert unless a runtime is installed."""

from contextlib import nullcontext
from dataclasses import dataclass

_runtime = None


@dataclass(frozen=True)
class Point:
    kind: str
    unit_hint: str
    facts: tuple
    doc: str
    site: str


class TuningPointError(Exception):
    pass


POINTS = {
    "min_health": Point(
        "value",
        "survey",
        ("score",),
        "Minimum health score for a surveyed cell to be considered patchable.",
        "acq4/experiment/cell_producer.py CellProducer._isHealthy",
    ),
    "pipette_detector_class": Point(
        "value",
        "slice",
        (),
        "Detector class used to find the pipette tip in a frame.",
        "acq4/devices/Pipette/tracker.py PipetteTracker.measureTipPosition",
    ),
    "patching": Point(
        "scope",
        "cell",
        ("ctx",),
        "Wraps the patch attempt for one cell.",
        "acq4/experiment/actions/fsm.py patch",
    ),
    "whole_cell": Point(
        "scope",
        "cell",
        ("ctx", "access_resistance"),
        "Wraps the whole-cell phase of a patch attempt.",
        "none yet — reserved",
    ),
}


def resolve_fact(facts, name):
    fact = facts[name]
    return fact() if callable(fact) else fact


def check_call(point, kind, facts):
    if point not in POINTS:
        raise TuningPointError(f"unknown tuning point {point!r}")
    spec = POINTS[point]
    if spec.kind != kind:
        raise TuningPointError(
            f"tuning point {point!r} is a {spec.kind} point, not a {kind} point"
        )
    if set(facts or {}) != set(spec.facts):
        raise TuningPointError(
            f"tuning point {point!r} takes facts {sorted(spec.facts)}, got {sorted(facts or {})}"
        )
    return spec


def value(point, default, facts=None):
    check_call(point, "value", facts)
    if _runtime is None:
        return default
    raise NotImplementedError("installed runtime path")


def scope(point, facts=None):
    check_call(point, "scope", facts)
    if _runtime is None:
        return nullcontext()
    raise NotImplementedError("installed runtime path")
