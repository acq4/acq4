from .base import AnalysisFunction, RunContext, functionFor, register

_MODULES = [
    'pipette_in_bath',
    'seal_evaluation',
    'access_resistance_smoke',
    'true_resting_vm',
    'dascale',
    'square_pulse',
    'rheobase',
    'ramp',
    'chirp',
]


def _loadAll():
    import importlib

    for name in _MODULES:
        try:
            importlib.import_module(f'{__name__}.{name}')
        except ModuleNotFoundError as exc:
            # not yet ported; anything else missing is a real error
            if exc.name != f'{__name__}.{name}':
                raise
