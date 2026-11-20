"""In-memory tuning-point ledger for runtime tests: real balancing behaviour over a list of lines."""

import random

from acq4.util.tuning_points import INELIGIBLE


class MemoryLedger:
    def __init__(self, rng=None):
        self.lines = []
        self._rng = rng or random.Random()

    def record(self, line):
        self.lines.append(dict(line))

    def decision_lines(self, mutator=None):
        return [
            line
            for line in self.lines
            if line.get("event") == "decision"
            and (mutator is None or line["mutator"] == mutator)
        ]

    def decisions(self, mutator, unit_kind, unit_id):
        found = None
        for line in self.decision_lines(mutator):
            if line["unit"] == unit_kind and line["unit_id"] == unit_id:
                found = line["condition"] if "condition" in line else INELIGIBLE
        return found

    def choose(self, mutator, unit_kind, conditions, slice_id):
        counts = [0] * len(conditions)
        for line in self.decision_lines(mutator):
            if line["unit"] != unit_kind or "condition" not in line:
                continue
            if unit_kind == "cell" and line["slice_id"] != slice_id:
                continue
            for i, condition in enumerate(conditions):
                if condition == line["condition"]:
                    counts[i] += 1
        least = min(counts)
        return self._rng.choice([c for c, n in zip(conditions, counts) if n == least])
