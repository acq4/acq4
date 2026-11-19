"""The explicit registry of tuning mutators, keyed by name."""

from .seal import SealTimeout

MUTATORS = {cls.name: cls for cls in (SealTimeout,)}
