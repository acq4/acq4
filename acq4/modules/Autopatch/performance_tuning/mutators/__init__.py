"""The explicit registry of tuning mutators, keyed by name."""

from .seal import SealTimeout
from .survey import MinHealth


def build_registry(classes):
    registry = {}
    for cls in classes:
        if cls.name in registry:
            raise ValueError(f"duplicate mutator name {cls.name!r}")
        registry[cls.name] = cls
    return registry


MUTATORS = build_registry((SealTimeout, MinHealth))
