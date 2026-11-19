"""Append-only JSONL assignment ledger for tuning runs, mirrored into each slice directory."""

import json
import os
import random

from acq4.util.tuning_points import INELIGIBLE

MIRROR_NAME = "performance_tuning_ledger.jsonl"


def ledger_path(manager, run_id):
    return manager.configFileName(
        os.path.join("modules", "AutopatchTuning", "runs", f"{run_id}.jsonl")
    )


def read_lines(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(text) for text in f if text.strip()]


def _key(condition):
    return json.dumps(condition, sort_keys=True)


class JsonlLedger:
    """Implements the tuning_points Ledger protocol over a JSONL file.

    Conditions round-trip through JSON and are compared by their sorted-key
    `json.dumps`, so they must be JSON-stable: `30` and `30.0` are different conditions.
    """

    def __init__(self, path, rng=None):
        self.path = path
        self._rng = rng or random.Random()
        self._lines = read_lines(path)

    def record(self, line):
        line = json.loads(json.dumps(line, default=str))
        if "condition" not in line and line.get("event") == "decision":
            line["eligible"] = False
        text = json.dumps(line) + "\n"
        self._append(self.path, text, init=True)
        if line.get("slice_dir"):
            self._append(os.path.join(line["slice_dir"], MIRROR_NAME), text)
        self._lines.append(line)

    def _append(self, path, text, init=False):
        if init and not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            gitignore = os.path.join(
                os.path.dirname(os.path.dirname(path)), ".gitignore"
            )
            if not os.path.exists(gitignore):
                with open(gitignore, "w") as f:
                    f.write("*\n")
        with open(path, "a") as f:
            f.write(text)
            f.flush()

    def lines(self):
        return list(self._lines)

    def slice_dirs(self):
        seen = {}
        for line in self._lines:
            if line.get("slice_dir"):
                seen.setdefault(line["slice_dir"])
        return list(seen)

    def _decision_lines(self, mutator):
        return [
            line
            for line in self._lines
            if line.get("event") == "decision" and line["mutator"] == mutator
        ]

    def decisions(self, mutator, unit_kind, unit_id):
        found = None
        for line in self._decision_lines(mutator):
            if line["unit"] == unit_kind and line["unit_id"] == unit_id:
                found = line["condition"] if "condition" in line else INELIGIBLE
        return found

    def choose(self, mutator, unit_kind, conditions, slice_id):
        keys = [_key(c) for c in conditions]
        counts = [0] * len(conditions)
        for line in self._decision_lines(mutator):
            if line["unit"] != unit_kind or "condition" not in line:
                continue
            if unit_kind == "cell" and line["slice_id"] != slice_id:
                continue
            for i, key in enumerate(keys):
                if key == _key(line["condition"]):
                    counts[i] += 1
        least = min(counts)
        return self._rng.choice([c for c, n in zip(conditions, counts) if n == least])
