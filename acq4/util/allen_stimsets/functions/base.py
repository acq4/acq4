"""Base class and registry for ported MIES patch-seq analysis functions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Optional

from .. import qc
from ..core import (
    MIN_SAMPLE_INTERVAL,
    AbortSet,
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

NO_STIMSET = '- none -'  # MIES NONE: a stimset-name parameter naming no stimset
SAMPLING_MULTIPLIERS = (1, 2, 4, 8, 16, 32, 64)


@dataclass
class RunContext:
    """Read-only rig state an analysis function may consult.

    Callables are evaluated when called, so they reflect settings applied earlier in the run.
    """

    autobiasTarget: Callable[[], Optional[float]]  # mV, also while autobias is off; None if unknown
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
        """Return analysis parameter *name*; AbortSet when absent and no *default* is given."""
        if name in self.params:
            return self.params[name]
        if default is _REQUIRED:
            raise AbortSet(f"{self.miesName}: required parameter {name!r} missing")
        return default

    def stimsetParam(self, name: str) -> Optional[str]:
        """Return stimset-name parameter *name* (e.g. NextStimSetName); None when unset or NONE."""
        v = self.param(name, NO_STIMSET)
        return None if v in ('', NO_STIMSET) else v

    def sampleInterval(self) -> float:
        """Return ms per sample: MIN_SAMPLE_INTERVAL x ``SamplingMultiplier``; AbortSet if invalid."""
        mult = self.param('SamplingMultiplier')
        if mult not in SAMPLING_MULTIPLIERS:
            raise AbortSet(
                f"{self.miesName}: SamplingMultiplier {mult} not in {SAMPLING_MULTIPLIERS}"
            )
        return MIN_SAMPLE_INTERVAL * mult

    def samplingPassed(self, data: SweepData) -> bool:
        """Return sampling QC of *data* against ``SamplingFrequency`` (MIES default per type)."""
        expected = self.param('SamplingFrequency', qc.defaultSamplingFrequency(self.analysisType))
        return qc.samplingQC(data.sampleInterval, expected)

    def checkStimsetLength(self, minLength: float) -> None:
        """Raise AbortSet when the stimset is shorter than *minLength* ms."""
        length = len(self.stimset.gridWave(0)) * MIN_SAMPLE_INTERVAL
        if length < minLength:
            raise AbortSet(f"{self.stimset.name} is {length:g} ms, needs at least {minLength:g} ms")

    def requireAutobiasTarget(self) -> float:
        """Return the autobias target (mV); raises AbortSet when it is unknown, non-finite or 0."""
        target = self.context.autobiasTarget()
        if target is None or not math.isfinite(target) or abs(target) < 1e-8:
            raise AbortSet(f"{self.miesName}: autobias target is {target}")
        return target

    def dascaleOutOfRange(self, dascale: float, setSweepIndex: int) -> bool:
        """Return whether *dascale* fails the DAC limit check for stimset sweep *setSweepIndex*."""
        lo, hi = self.stimset.extremes(setSweepIndex)
        return qc.dascaleOutOfRange(
            dascale, lo, hi, self.context.commandLimit, self.context.holding()
        )

    def baselineQC(self, **thresholds) -> qc.BaselineQC:
        """Return a BaselineQC with the ``BaselineRMS*Threshold`` parameters and *thresholds*."""
        return qc.BaselineQC(
            self.analysisType,
            rmsShortThreshold=self.param('BaselineRMSShortThreshold', qc.RMS_SHORT_THRESHOLD),
            rmsLongThreshold=self.param('BaselineRMSLongThreshold', qc.RMS_LONG_THRESHOLD),
            **thresholds,
        )

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
