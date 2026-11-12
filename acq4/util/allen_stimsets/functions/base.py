"""Base class and registry for ported MIES patch-seq analysis functions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Optional

from ..core import (
    EpochTable,
    MidSweepAction,
    SetConfig,
    SetResult,
    SweepConfig,
    SweepData,
    SweepDecision,
)
from ..notebook import Notebook, SetRecord

if TYPE_CHECKING:
    from ..stimset import StimsetDef


_REQUIRED = object()


@dataclass
class RunContext:
    """Read-only rig state an analysis function may consult.

    Callables are evaluated when called, so they reflect settings applied earlier in the run.
    """

    autobiasTarget: Callable[[], Optional[float]]  # mV, or None when autobias is off
    holding: Callable[[], float]  # pA (IC) or mV (VC), current holding command
    commandLimit: float  # largest |command| the DA channel can output, pA (IC) / mV (VC)
    stimsets: Callable[
        [str], 'StimsetDef'
    ]  # look up another stimset by name (e.g. NextStimSetName)


class AnalysisFunction:
    """One MIES patch-seq analysis function bound to one set (one pass through one stimset).

    The runner calls, in order: ``preSet`` once; for each sweep ``preSweep``, ``midSweep`` zero or more
    times on growing partial data, ``postSweep`` once; then ``postSet`` once (also after an abort). A
    function never touches hardware or the notebook's other sets except through return values and reads.

    Subclasses set ``miesName`` (e.g. 'PSQ_DAScale'), ``analysisType`` (MIES prefix, e.g. 'DA') and
    ``clampMode``, and register with ``@register``.
    """

    miesName: str = ''
    analysisType: str = ''
    clampMode: str = ''

    def __init__(
        self, stimset: 'StimsetDef', params: dict[str, Any], notebook: Notebook, context: RunContext
    ):
        self.stimset = stimset
        self.params = params
        self.notebook = notebook
        self.context = context
        self.setRecord: Optional[SetRecord] = None  # assigned by the runner before preSet

    def param(self, name: str, default: Any = _REQUIRED) -> Any:
        """Return analysis parameter *name*; KeyError when absent and no *default* is given."""
        if name in self.params:
            return self.params[name]
        if default is _REQUIRED:
            raise KeyError(f"{self.miesName}: required parameter {name!r} missing")
        return default

    def preSet(self) -> SetConfig:
        raise NotImplementedError

    def preSweep(self, setSweepIndex: int, layout: EpochTable) -> SweepConfig:
        """Return the next sweep's settings; *layout* holds its stimset and TP epochs (DAScale 1)."""
        raise NotImplementedError

    def midSweep(self, data: SweepData) -> MidSweepAction:
        return None

    def postSweep(self, data: SweepData) -> SweepDecision:
        raise NotImplementedError

    def postSet(self) -> SetResult:
        raise NotImplementedError


_registry: dict[str, type[AnalysisFunction]] = {}


def register(cls: type[AnalysisFunction]) -> type[AnalysisFunction]:
    _registry[cls.miesName] = cls
    return cls


def functionFor(miesName: str) -> type[AnalysisFunction]:
    """Return the class for MIES analysis function *miesName*; KeyError if not ported."""
    from . import _loadAll

    _loadAll()
    return _registry[miesName]
