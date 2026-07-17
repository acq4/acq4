"""Parse MultiPatch autopatch logs into per-attempt records.

Reads the newline-delimited JSON ``MultiPatch_*.log`` files written by the
MultiPatch module and reconstructs one :class:`Attempt` per patch attempt,
deriving how far each attempt progressed through the find/seal/break-in funnel.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Iterable

# Fields carried on every ``test_pulse`` event (see MultiPatchLog.TEST_PULSE_METAARRAY_INFO).
TEST_PULSE_FIELDS = (
    "baseline_potential",
    "baseline_current",
    "input_resistance",
    "access_resistance",
    "steady_state_resistance",
    "capacitance",
    "time_constant",
)

# Gigaseal threshold used to cross-check the state machine's seal claim.
GIGASEAL_OHMS = 1e9

# Ordered funnel stages an attempt can reach. Higher index == further progress.
STAGE_NAMES = ("attempted", "approached", "found", "sealed", "whole_cell")
ATTEMPTED, APPROACHED, FOUND, SEALED, WHOLE_CELL = range(len(STAGE_NAMES))

# Minimum funnel stage implied by entering a given patch state. States that do
# not represent forward progress (idle/reset/failure) map to ATTEMPTED so they
# never inflate an attempt's best stage.
#   - approach/cell detect/contact cell: hunting for a cell membrane
#   - seal: a cell was detected/contacted (you only enter seal on detectedCell)
#   - cell attached: gigaseal formed
#   - break in: sealed, now rupturing the membrane
#   - whole cell (and post-success reseal/collect/home): broke in
STATE_STAGE = {
    "out": ATTEMPTED,
    "bath": ATTEMPTED,
    "clean": ATTEMPTED,
    "fouled": ATTEMPTED,
    "broken": ATTEMPTED,
    "blowout": ATTEMPTED,
    "approach": APPROACHED,
    "cell detect": APPROACHED,
    "contact cell": APPROACHED,
    "seal": FOUND,
    "cell attached": SEALED,
    "break in": SEALED,
    "whole cell": WHOLE_CELL,
    "reseal": WHOLE_CELL,
    "home with nucleus": WHOLE_CELL,
    "collect": WHOLE_CELL,
}

# States that indicate an attempt has ended without a live whole-cell recording.
FAILURE_STATES = frozenset({"broken", "fouled", "clean", "out", "bath", "blowout"})


def parse_log_events(path: str) -> list[dict[str, Any]]:
    """Read a MultiPatch log file into a list of event dicts.

    Each non-blank line is a JSON object with a trailing comma (as written by
    the MultiPatch module). Blank lines and unparseable lines are skipped.
    """
    events: list[dict[str, Any]] = []
    with open(path, "rb") as fh:
        for line in fh:
            line = line.rstrip(b",\r\n")
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


@dataclass
class Attempt:
    """One patch attempt on one device, reconstructed from a log's events."""

    source: str
    device: str
    index: int
    start_time: float
    end_time: float
    # ordered (time, state) pairs from state_change events (state entered)
    states: list[tuple[float, str]] = field(default_factory=list)
    # test_pulse events as dicts (each has 'event_time' plus TEST_PULSE_FIELDS)
    test_pulses: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def best_stage(self) -> int:
        """Furthest funnel stage this attempt reached (see STAGE_NAMES)."""
        if not self.states:
            return ATTEMPTED
        return max(STATE_STAGE.get(state, ATTEMPTED) for _, state in self.states)

    @property
    def best_stage_name(self) -> str:
        return STAGE_NAMES[self.best_stage]

    @property
    def attempted_find(self) -> bool:
        return self.best_stage >= APPROACHED

    @property
    def found_cell(self) -> bool:
        return self.best_stage >= FOUND

    @property
    def sealed(self) -> bool:
        return self.best_stage >= SEALED

    @property
    def broke_in(self) -> bool:
        return self.best_stage >= WHOLE_CELL

    @property
    def final_state(self) -> str | None:
        """The last patch state entered during this attempt."""
        return self.states[-1][1] if self.states else None

    @property
    def outcome(self) -> str:
        """'whole cell' on success, else the state the attempt gave up in."""
        if self.broke_in:
            return "whole cell"
        # last failure/reset state entered, else the final state, else 'no states'
        for _, state in reversed(self.states):
            if state in FAILURE_STATES:
                return state
        return self.final_state or "no states"

    def state_intervals(self) -> list[tuple[str, float, float]]:
        """(state, t_enter, t_exit) spans; the last span runs to end_time."""
        spans = []
        for i, (t, state) in enumerate(self.states):
            t_end = self.states[i + 1][0] if i + 1 < len(self.states) else self.end_time
            spans.append((state, t, t_end))
        return spans

    def test_pulses_in_states(self, states: Iterable[str]) -> list[dict[str, Any]]:
        """Test pulses recorded while the pipette was in any of ``states``."""
        wanted = set(states)
        spans = [s for s in self.state_intervals() if s[0] in wanted]
        if not spans:
            return []
        hits = []
        for tp in self.test_pulses:
            t = tp.get("event_time")
            if t is None:
                continue
            # Spans are half-open [t0, t1) so boundary pulses aren't double-counted,
            # except the span ending at end_time includes its final pulse.
            if any(t0 <= t < t1 or (t == t1 == self.end_time) for _, t0, t1 in spans):
                hits.append(tp)
        return hits

    @property
    def max_seal_resistance(self) -> float | None:
        """Peak steady-state resistance reached while sealing (ohms)."""
        tps = self.test_pulses_in_states({"seal", "cell attached"})
        vals = [
            tp["steady_state_resistance"]
            for tp in tps
            if tp.get("steady_state_resistance") is not None
        ]
        return max(vals) if vals else None

    @property
    def gigaseal(self) -> bool:
        """Whether a gigaohm seal was measured (cross-check on the state claim)."""
        r = self.max_seal_resistance
        return r is not None and r >= GIGASEAL_OHMS

    def _whole_cell_stat(self, field_name: str) -> float | None:
        tps = self.test_pulses_in_states({"whole cell"})
        vals = [tp[field_name] for tp in tps if tp.get(field_name) is not None]
        if not vals:
            return None
        vals.sort()
        return vals[len(vals) // 2]  # median

    @property
    def access_resistance(self) -> float | None:
        """Median access resistance during whole-cell (ohms)."""
        return self._whole_cell_stat("access_resistance")

    @property
    def input_resistance(self) -> float | None:
        """Median input resistance during whole-cell (ohms)."""
        return self._whole_cell_stat("input_resistance")

    @property
    def holding_current(self) -> float | None:
        """Median baseline (holding) current during whole-cell (amps)."""
        return self._whole_cell_stat("baseline_current")

    @property
    def capacitance(self) -> float | None:
        """Median membrane capacitance during whole-cell (farads)."""
        return self._whole_cell_stat("capacitance")


def _attempts_from_device_events(
    events: list[dict[str, Any]], source: str, device: str
) -> list[Attempt]:
    """Split one device's event stream into attempts on ``new_patch_attempt``.

    A log with no ``new_patch_attempt`` markers is treated as a single attempt.
    """
    # indices of new_patch_attempt markers
    starts = [
        i for i, ev in enumerate(events) if ev.get("event") == "new_patch_attempt"
    ]
    if not starts:
        chunks = [events]
    else:
        # a preamble before the first marker (if any) is its own attempt
        bounds = ([0] if starts[0] != 0 else []) + starts + [len(events)]
        chunks = [events[a:b] for a, b in zip(bounds, bounds[1:]) if b > a]

    attempts = []
    for index, chunk in enumerate(chunks):
        times = [ev["event_time"] for ev in chunk if "event_time" in ev]
        if not times:
            continue
        att = Attempt(
            source=source,
            device=device,
            index=index,
            start_time=min(times),
            end_time=max(times),
        )
        for ev in chunk:
            etype = ev.get("event")
            if etype == "state_change":
                att.states.append((ev["event_time"], ev["state"]))
            elif etype == "test_pulse":
                att.test_pulses.append(ev)
        attempts.append(att)
    return attempts


def load_log(path: str) -> list[Attempt]:
    """Parse one log file into attempts, split per device and per attempt."""
    events = parse_log_events(path)
    by_device: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        dev = ev.get("device")
        if dev is None:
            continue  # global events (profiles, surface depth) carry no device
        by_device.setdefault(dev, []).append(ev)
    attempts = []
    for device, dev_events in by_device.items():
        attempts.extend(_attempts_from_device_events(dev_events, path, device))
    return attempts


def approached_attempts(attempts: Iterable[Attempt]) -> list[Attempt]:
    """Keep only attempts that actually engaged a cell (reached the approach stage).

    Attempts that never progress past out/bath/clean/fouled (``best_stage ==
    ATTEMPTED``) are pipette setup and cleaning cycles, not real patch attempts
    on a cell. They are excluded so the demo analysis (funnel, throughput,
    active time) reflects only cells the rig actually tried to patch.
    """
    return [a for a in attempts if a.attempted_find]


def find_logs(roots: Iterable[str]) -> list[str]:
    """Recursively find MultiPatch_*.log files under ``roots`` (case-insensitive)."""
    found = []
    for root in roots:
        if os.path.isfile(root):
            found.append(root)
            continue
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                low = name.lower()
                if low.startswith("multipatch_") and low.endswith(".log"):
                    found.append(os.path.join(dirpath, name))
    return sorted(found)


def load_run(roots: Iterable[str]) -> list[Attempt]:
    """Load every attempt from every MultiPatch log found under ``roots``."""
    attempts = []
    for path in find_logs(roots):
        attempts.extend(load_log(path))
    return attempts
