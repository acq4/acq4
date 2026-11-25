"""Survey-stage mutators."""

from .base import ValueMutator


class MinHealth(ValueMutator):
    name = "min_health"
    unit = "survey"
    answers = {"min_health"}
    conditions = [0.5, 0.7]

    def value(self, point, default, condition, facts):
        return condition
