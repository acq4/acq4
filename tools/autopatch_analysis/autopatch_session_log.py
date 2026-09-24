"""Parse ACQ4 session logs (``log.json``) for the costs a MultiPatch log misses.

The MultiPatch recorder only runs while a cell directory is open, so everything
*between* patch attempts is invisible to ``MultiPatch_*.log``: the clean cycle
that follows every attempt, the tile survey that finds the next cells, and the
idle spent parked while those happen. On an extended demo run that gap is about
half the clock -- the per-log spans ``autopatch_metrics.throughput`` calls
"active time" cover only the patch work itself.

ACQ4's own session log does cover it. ``log.json`` is written for the whole
storage-directory run, and two things in it reconstruct the missing time:

* **Patch states.** ``PatchPipetteStateManager.configureState`` wraps each
  transition in a gentletask throughline frame named ``"<device> -> state
  '<state>'"``, so every record logged inside the transition names the device
  and the state it is entering -- including states (``clean``, ``fouled``,
  ``out``) the MultiPatch recorder was not running for.
* **Cell detection.** ``acq4.experiment.tile_detector.detect`` brackets each
  survey -- move the scope, acquire a z-stack, run the detection model over it
  -- between a "Surveying tile" and a "yielded N candidates" record.

Aggregation into a time budget lives in ``autopatch_metrics`` (see
``session_time_budget``).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Iterable, Iterator

SESSION_LOG_NAME = "log.json"

# Throughline frame pushed by PatchPipetteStateManager.configureState. Non-greedy
# device so a device name containing " -> state '" still splits at the last one.
STATE_FRAME_RE = re.compile(r"^(?P<device>.+) -> state '(?P<state>.*)'$")

# The single record per transition that means "the next state is taking over":
# _configureState logs it once the next state's job has been built, right before
# stopping the previous one. The "Configuring next state" line above it is not a
# safe anchor -- building the job can raise, and then that state never ran.
TRANSITION_FUNC = "_configureState"
TRANSITION_PREFIX = "Stopping previous state"

# tile_detector.detect() start/end records.
SURVEY_FUNC = "detect"
SURVEY_MODULE = "tile_detector"
SURVEY_START_PREFIX = "Surveying tile at"
SURVEY_END_RE = re.compile(r"^Tile at .* yielded (\d+) candidates")

# Cheap line prefilter: a 40 MB session log is mostly records we do not want, and
# json.loads on every one of them dominates the parse. Any line we do want
# contains one of these.
_LINE_MARKERS = (b"-> state '", b"Surveying tile at", b"candidates")


@dataclass(frozen=True)
class StateSpan:
    """One uninterrupted stay of ``device`` in ``state``, from a session log."""

    source: str
    device: str
    state: str
    t_start: float
    t_end: float

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start


@dataclass(frozen=True)
class SurveySpan:
    """One tile survey: scope move, z-stack, and detection model, end to end."""

    source: str
    t_start: float
    t_end: float
    n_candidates: int

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start


def find_session_logs(roots: Iterable[str]) -> list[str]:
    """Find the ``log.json`` covering each root.

    Searched downwards first (a root pointing at the run directory, which is
    where ACQ4 writes it), then upwards from the root itself, so pointing at a
    slice or cell subdirectory still finds the session log of the run it belongs
    to. Only the nearest ancestor is taken: the one whose run the root is part of.
    """
    found: set[str] = set()
    for root in roots:
        root = os.path.abspath(root)
        below = set()
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if name.lower() == SESSION_LOG_NAME:
                    below.add(os.path.join(dirpath, name))
        if below:
            found |= below
            continue
        path = root if os.path.isdir(root) else os.path.dirname(root)
        while True:
            candidate = os.path.join(path, SESSION_LOG_NAME)
            if os.path.isfile(candidate):
                found.add(candidate)
                break
            parent = os.path.dirname(path)
            if parent == path:
                break
            path = parent
    return sorted(found)


def _iter_records(path: str) -> Iterator[dict]:
    """Yield the session-log records that could be a transition or a survey."""
    with open(path, "rb") as fh:
        for raw in fh:
            if not any(marker in raw for marker in _LINE_MARKERS):
                continue
            text = raw.decode("utf-8", "replace").strip().rstrip(",")
            if not text:
                continue
            try:
                record = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record


def _transition(record: dict) -> tuple[float, str, str] | None:
    """(time, device, state entered) if ``record`` marks a state transition."""
    if record.get("funcName") != TRANSITION_FUNC:
        return None
    if not str(record.get("message", "")).startswith(TRANSITION_PREFIX):
        return None
    t = record.get("created")
    if t is None:
        return None
    # The state frame is not necessarily the outermost one: configureState may be
    # called from inside a named operation (a GUI action, the autopatch queue).
    for frame in record.get("throughline") or ():
        m = STATE_FRAME_RE.match(str(frame))
        if m:
            return float(t), m.group("device"), m.group("state")
    return None


def _spans_from_transitions(
    transitions: list[tuple[float, str, str]], source: str
) -> list[StateSpan]:
    """Pair each device's transitions into spans.

    Consecutive transitions into the same state are one stay, not two: the state
    machine reconfigures a state in place (a profile change, a reset) without the
    pipette having gone anywhere. A device's last transition is dropped -- the log
    records the state being entered but never left, so its "duration" would be
    time-until-the-session-ended, not a dwell time.
    """
    spans: list[StateSpan] = []
    by_device: dict[str, list[tuple[float, str]]] = {}
    for t, device, state in transitions:
        by_device.setdefault(device, []).append((t, state))
    for device, entries in by_device.items():
        entries.sort(key=lambda e: e[0])
        merged = [e for i, e in enumerate(entries) if i == 0 or e[1] != entries[i - 1][1]]
        for (t0, state), (t1, _next_state) in zip(merged, merged[1:]):
            spans.append(StateSpan(source, device, state, t0, t1))
    spans.sort(key=lambda s: (s.device, s.t_start))
    return spans


def parse_session_log(path: str) -> tuple[list[StateSpan], list[SurveySpan]]:
    """Parse one ``log.json`` into (patch-state spans, tile-survey spans)."""
    transitions: list[tuple[float, str, str]] = []
    surveys: list[SurveySpan] = []
    survey_start: float | None = None
    for record in _iter_records(path):
        parsed = _transition(record)
        if parsed is not None:
            transitions.append(parsed)
            continue
        if record.get("module") != SURVEY_MODULE or record.get("funcName") != SURVEY_FUNC:
            continue
        message = str(record.get("message", ""))
        t = record.get("created")
        if t is None:
            continue
        if message.startswith(SURVEY_START_PREFIX):
            # A survey with no "yielded" record was aborted (or the log ends
            # mid-survey); it is superseded rather than closed at a guessed time.
            survey_start = float(t)
            continue
        m = SURVEY_END_RE.match(message)
        if m is not None and survey_start is not None:
            surveys.append(SurveySpan(path, survey_start, float(t), int(m.group(1))))
            survey_start = None
    return _spans_from_transitions(transitions, path), surveys


def load_session_logs(
    roots: Iterable[str],
) -> tuple[list[StateSpan], list[SurveySpan]]:
    """Parse every session log covering ``roots`` into spans and surveys."""
    spans: list[StateSpan] = []
    surveys: list[SurveySpan] = []
    for path in find_session_logs(roots):
        s, d = parse_session_log(path)
        spans.extend(s)
        surveys.extend(d)
    return spans, surveys


__all__ = [
    "SESSION_LOG_NAME",
    "StateSpan",
    "SurveySpan",
    "find_session_logs",
    "parse_session_log",
    "load_session_logs",
]
