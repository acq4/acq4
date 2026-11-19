"""Registry, call API and installed runtime for performance tuning points.

Inert unless a Runtime is installed; then asks are answered per slice/survey/cell unit.
"""

import threading
import uuid
import warnings
from contextlib import ExitStack, contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone

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


class TuningPointWarning(UserWarning):
    pass


class _Ineligible:
    def __repr__(self):
        return "INELIGIBLE"


INELIGIBLE = _Ineligible()
_UNDECIDED = object()
UNIT_KINDS = ("slice", "survey", "cell")


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
    return _runtime.value(point, default, facts or {})


def scope(point, facts=None):
    check_call(point, "scope", facts)
    if _runtime is None:
        return nullcontext()
    return _runtime.scope(point, facts or {})


def install(runtime):
    global _runtime
    if _runtime is not None:
        raise TuningPointError("a tuning runtime is already installed")
    _runtime = runtime


def uninstall():
    global _runtime
    _runtime = None


def installed():
    return _runtime


def open_unit(kind, **ids):
    if _runtime is None:
        return None
    return _runtime.open_unit(kind, **ids)


def close_unit(unit):
    if unit is None:
        return {}
    return unit.runtime.close_unit(unit)


@contextmanager
def unit(kind, **ids):
    opened = open_unit(kind, **ids)
    try:
        yield opened
    finally:
        close_unit(opened)


def current_slice():
    if _runtime is None:
        return None
    return _runtime.current_slice


@dataclass(eq=False)
class Unit:
    kind: str
    id: str
    parent: "Unit | None"
    runtime: "Runtime" = field(repr=False)
    slice_dir: "str | None" = None
    cell_dir: object = field(default=None, repr=False)
    survey_id: "str | None" = None
    closed: bool = False
    decisions: dict = field(default_factory=dict)
    fired: dict = field(default_factory=dict)
    asked: set = field(default_factory=set)

    @property
    def slice_unit(self):
        return self if self.kind == "slice" else self.parent


def _now():
    return datetime.now(timezone.utc).isoformat()


class Runtime:
    def __init__(self, run_id, mutators, ledger, cell_close_hook=None):
        self.run_id = run_id
        self.mutators = list(mutators)
        self.ledger = ledger
        self.cell_close_hook = cell_close_hook
        self.current_slice = None
        self._answering = {}
        self._wrapping = {}
        for m in self.mutators:
            for point in getattr(m, "answers", ()):
                self._answering.setdefault(point, []).append(m)
            for point in getattr(m, "wraps", ()):
                self._wrapping.setdefault(point, []).append(m)
        self._lock = threading.RLock()
        self._local = threading.local()
        self._surveys = {}
        self._fired_anywhere = set()
        self._warned_outside = set()

    def _open_stack(self):
        if not hasattr(self._local, "stack"):
            self._local.stack = []
        return self._local.stack

    def open_unit(self, kind, **ids):
        if kind not in UNIT_KINDS:
            raise TuningPointError(f"unknown unit kind {kind!r}")
        with self._lock:
            if kind == "slice":
                if self.current_slice is not None and not self.current_slice.closed:
                    raise TuningPointError(
                        f"slice unit {self.current_slice.id} is still open"
                    )
                slice_dir = ids["slice_dir"]
                u = Unit(
                    "slice",
                    slice_dir.info()["__uuid__"],
                    None,
                    self,
                    slice_dir=slice_dir.name(),
                )
                self.current_slice = u
            else:
                parent = self.current_slice
                if parent is not None and parent.closed:
                    raise TuningPointError(
                        f"cannot open a {kind} unit under closed slice {parent.id}"
                    )
                if kind == "survey":
                    u = Unit("survey", uuid.uuid4().hex, parent, self)
                    self._surveys[u.id] = u
                else:
                    cell_dir = ids["cell_dir"]
                    u = Unit(
                        "cell",
                        cell_dir.info()["__uuid__"],
                        parent,
                        self,
                        cell_dir=cell_dir,
                        survey_id=ids.get("survey_id"),
                    )
                self._open_stack().append(u)
            if kind in ("slice", "cell"):
                for m in self.mutators:
                    if m.unit == kind:
                        prior = self.ledger.decisions(m.name, kind, u.id)
                        if prior is not None:
                            u.decisions[m.name] = prior
            self.ledger.record(self._unit_line("unit_open", u))
        return u

    def close_unit(self, u):
        with self._lock:
            if u.closed:
                raise TuningPointError(f"{u.kind} unit {u.id} is already closed")
            if u.kind != "slice":
                stack = self._open_stack()
                if u not in stack:
                    raise TuningPointError(
                        f"{u.kind} unit {u.id} was not opened on this thread"
                    )
                stack.remove(u)
            u.closed = True
            line = self._unit_line("unit_close", u)
            line["asked"] = sorted(u.asked)
            if u.kind == "survey":
                line["fired"] = {name: dict(c) for name, c in u.fired.items()}
            self.ledger.record(line)
            unfired = [
                m
                for m in self.mutators
                if m.unit == u.kind and m.name not in self._fired_anywhere
            ]
            summary = self._cell_summary(u) if u.kind == "cell" else None
        for m in unfired:
            points = sorted(
                set(getattr(m, "answers", ())) | set(getattr(m, "wraps", ()))
            )
            warnings.warn(
                f"tuning mutator {m.name!r} has not fired in this run (points: {points})",
                TuningPointWarning,
                stacklevel=3,
            )
        if summary is None:
            return {}
        if self.cell_close_hook is not None:
            summary["provenance"] = self.cell_close_hook(u.cell_dir)
        return summary

    def _cell_summary(self, cell):
        sources = [cell, self._surveys.get(cell.survey_id), cell.parent]
        conditions = {}
        assigned_by = {}
        for source in sources:
            if source is None:
                continue
            for name, decision in source.decisions.items():
                if decision is not INELIGIBLE:
                    conditions[name] = decision
                    assigned_by[name] = source.kind
        return {
            "run_id": self.run_id,
            "survey_id": cell.survey_id,
            "conditions": conditions,
            "assigned_by": assigned_by,
            "fired": {name: dict(c) for name, c in cell.fired.items()},
        }

    def _unit_line(self, event, u):
        slice_unit = u.slice_unit
        return {
            "event": event,
            "unit": u.kind,
            "unit_id": u.id,
            "parent_id": u.parent.id if u.parent is not None else None,
            "slice_id": slice_unit.id if slice_unit is not None else None,
            "slice_dir": slice_unit.slice_dir if slice_unit is not None else None,
            "thread": threading.current_thread().name,
            "t": _now(),
        }

    def _owner(self, kind):
        stack = self._open_stack()
        if kind == "slice":
            if stack:
                return stack[-1].parent
            if self.current_slice is not None and not self.current_slice.closed:
                return self.current_slice
            return None
        for u in reversed(stack):
            if u.kind == kind:
                return u
        if kind == "survey":
            for u in reversed(stack):
                if u.kind == "cell":
                    return self._surveys.get(u.survey_id)
        return None

    def _decide(self, m, point, facts):
        """Return the condition `m` applies to this ask, or INELIGIBLE when it does not apply."""
        warn_outside = False
        with self._lock:
            owner = self._owner(m.unit)
            stack = self._open_stack()
            if stack:
                stack[-1].asked.add(m.name)
            if owner is None:
                warn_outside = point not in self._warned_outside
                self._warned_outside.add(point)
                decision = INELIGIBLE
            else:
                owner.asked.add(m.name)
                decision = owner.decisions.get(m.name, _UNDECIDED)
                if decision is _UNDECIDED:
                    decision = self._assign(m, owner, facts)
                if decision is not INELIGIBLE:
                    counts = owner.fired.setdefault(m.name, {})
                    counts[point] = counts.get(point, 0) + 1
                    self._fired_anywhere.add(m.name)
        if warn_outside:
            warnings.warn(
                f"tuning point {point!r} asked outside any {m.unit} unit; "
                f"mutator {m.name!r} did not answer",
                TuningPointWarning,
                stacklevel=4,
            )
        return decision

    def _assign(self, m, owner, facts):
        slice_unit = owner.slice_unit
        line = {
            "event": "decision",
            "mutator": m.name,
            "unit": owner.kind,
            "unit_id": owner.id,
            "slice_id": slice_unit.id if slice_unit is not None else None,
            "slice_dir": slice_unit.slice_dir if slice_unit is not None else None,
            "t": _now(),
        }
        if not m.eligible(facts):
            owner.decisions[m.name] = INELIGIBLE
            line["eligible"] = False
            self.ledger.record(line)
            return INELIGIBLE
        condition = self.ledger.choose(
            m.name, owner.kind, m.conditions, line["slice_id"]
        )
        if "ctx" in facts:
            with resolve_fact(facts, "ctx").log_action(
                f"Assign Condition: {m.name}={condition!r}", pausable=False
            ):
                self._store(m, owner, condition, line)
        else:
            self._store(m, owner, condition, line)
        return condition

    def _store(self, m, owner, condition, line):
        owner.decisions[m.name] = condition
        line["condition"] = condition
        self.ledger.record(line)

    def value(self, point, default, facts):
        answering = self._answering.get(point)
        if not answering:
            return default
        m = answering[0]
        condition = self._decide(m, point, facts)
        if condition is INELIGIBLE:
            return default
        return m.value(point, default, condition, facts)

    @contextmanager
    def scope(self, point, facts):
        applied = []
        for m in self._wrapping.get(point, ()):
            condition = self._decide(m, point, facts)
            if condition is not INELIGIBLE:
                applied.append((m, condition))
        with ExitStack() as stack:
            for m, condition in applied:
                stack.enter_context(m.around(point, condition, facts))
            yield
