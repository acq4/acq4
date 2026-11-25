"""Base classes for tuning mutators: value answerers, scope wrappers and profile-param pinners."""

from acq4.experiment.actions import change_patch_profile_params


class Mutator:
    name: str
    unit: str
    conditions: list
    # A condition every run must include; None for no baseline.
    baseline = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        conditions = getattr(cls, "conditions", None)
        if cls.baseline is not None and conditions is not None:
            if cls.baseline not in conditions:
                cls.conditions = [cls.baseline, *conditions]

    def eligible(self, facts) -> bool:
        return True


class ValueMutator(Mutator):
    answers: set

    def value(self, point, default, condition, facts):
        raise NotImplementedError


class ScopeMutator(Mutator):
    wraps: set

    def around(self, point, condition, facts):
        raise NotImplementedError


class ProfileParamMutator(ScopeMutator):
    wraps = {"patching"}
    params: tuple  # ((state, param), ...)

    def around(self, point, condition, facts):
        if len(self.params) == 1:
            ((state, param),) = self.params
            condition = {param: condition}
        values = {}
        for state, param in self.params:
            values.setdefault(state, {})[param] = condition[param]
        return change_patch_profile_params(facts["ctx"], values)
