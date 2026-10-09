"""Parse ACQ4 session logs (``log.json``) for time a MultiPatch log misses.

The MultiPatch recorder runs only while a cell directory is open, so the clean
cycle, tile survey, and idle between attempts appear only here. Two things in
``log.json`` reconstruct them: the ``"<device> -> state '<state>'"`` throughline
frame ``PatchPipetteStateManager.configureState`` wraps each transition in, and
the start/end records ``acq4.experiment.tile_detector.detect`` brackets each
survey with.

Aggregation into a time budget lives in ``autopatch_metrics``.
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

# Logged once the next state's job is built; the earlier "Configuring next state"
# line is not a safe anchor, since building the job can raise.
TRANSITION_FUNC = "_configureState"
TRANSITION_PREFIX = "Stopping previous state"

# tile_detector.detect() start/end records.
SURVEY_FUNC = "detect"
SURVEY_MODULE = "tile_detector"
SURVEY_START_PREFIX = "Surveying tile at"
SURVEY_END_RE = re.compile(r"^Tile at .* yielded (\d+) candidates")

# Cheap prefilter: json.loads on every line of a 40 MB session log dominates the parse.
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

    Searched downwards from each root first, then upwards to the nearest
    ancestor, so a slice or cell subdirectory still finds its run's log.
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
    # The state frame is not necessarily the outermost throughline frame.
    for frame in record.get("throughline") or ():
        m = STATE_FRAME_RE.match(str(frame))
        if m:
            return float(t), m.group("device"), m.group("state")
    return None


def _spans_from_transitions(
    transitions: list[tuple[float, str, str]], source: str
) -> list[StateSpan]:
    """Pair each device's transitions into spans.

    Consecutive transitions into the same state merge into one span. Each
    device's last transition is dropped: it was entered but never left.
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
            # A survey with no "yielded" record was aborted; superseded, not closed.
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
