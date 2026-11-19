"""Base classes for tuning mutators: value answerers, scope wrappers and profile-param pinners."""

from acq4.experiment.actions import change_patch_profile_params


class Mutator:
    name: str
    unit: str
    conditions: list

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
    params: dict

    def around(self, point, condition, facts):
        if isinstance(condition, dict):
            values = {}
            for state, param in self.params.items():
                values.setdefault(state, {})[param] = condition[param]
        else:
            state, param = next(iter(self.params.items()))
            values = {state: {param: condition}}
        return change_patch_profile_params(facts["ctx"], values)
