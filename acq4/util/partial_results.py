"""Types for results that a task delivers, partially settled, while it is still running."""

from __future__ import annotations

import math
from dataclasses import dataclass

from MetaArray import MetaArray


@dataclass(frozen=True)
class SettleSpec:
    """Declared settling delay of one result component.

    delay: seconds behind the acquisition edge at which values become final; math.inf means
        the component does not settle until the task ends.
    reason: short human-readable cause, e.g. "bidirectional Bessel, 100 Hz cutoff".
    """

    delay: float
    reason: str = ''

    def __post_init__(self):
        if not self.delay >= 0:
            raise ValueError(f"SettleSpec delay must be >= 0 (got {self.delay!r})")

    @property
    def updates(self) -> bool:
        """True if the component settles during the run (finite delay)."""
        return math.isfinite(self.delay)


class SettlementMixin:
    """Per-component count of settled (final) values on a result object.

    Components are channel names for DAQ devices, 'frames' for cameras. Producers call
    _initSettlement() before use, then _setSettled() and _setComplete() from any one thread;
    settlement() and isComplete() may be read from any thread.
    """

    def _initSettlement(self, components=()) -> None:
        """Reset settlement: every component in *components* starts at 0, not complete."""
        self._settled = {c: 0 for c in components}
        self._complete = False

    def settlement(self) -> dict[str, int]:
        """Return a copy of {component: number of settled values}."""
        return dict(self._settled)

    def isComplete(self) -> bool:
        """True once the producer has marked every component final (_setComplete)."""
        return self._complete

    def _setSettled(self, component: str, n: int) -> None:
        """Set the settled count of *component* (added if new).

        Raises ValueError if *n* is negative or less than the current count.
        """
        n = int(n)
        prev = self._settled.get(component, 0)
        if n < prev:
            raise ValueError(f"Settled count of {component!r} cannot decrease ({prev} -> {n})")
        self._settled[component] = n

    def _setComplete(self) -> None:
        """Mark every component final."""
        self._complete = True


class TaskResultArray(SettlementMixin, MetaArray):
    """MetaArray returned by DAQ-backed device tasks; same object during and after the run.

    Constructed exactly like MetaArray, with no settlement components. Slicing, copy() and
    arithmetic return plain MetaArray.
    """

    def __init__(self, *args, **kwargs):
        MetaArray.__init__(self, *args, **kwargs)
        self._initSettlement()
