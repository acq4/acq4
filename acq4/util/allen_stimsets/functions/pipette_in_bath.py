"""PSQ_PipetteInBath (PB): pipette resistance in the bath, voltage clamp."""

from __future__ import annotations

from typing import Optional

from .. import qc
from ..core import (
    AbortSet,
    AmplifierSettings,
    EpochTable,
    MidSweepAction,
    SetConfig,
    SweepConfig,
    SweepData,
)
from ..core import SweepDecision
from . import _vc_common as vc
from .base import register

PIPETTE_RESISTANCE = 'PipetteResistance'  # MOhm, sweep and set
PIPETTE_RESISTANCE_QC = 'PipetteResistanceQC'  # bool
# bool; the leak test failed, after which MIES re-runs auto pipette offset
AUTO_PIPETTE_OFFSET = 'AutoPipetteOffset'


@register
class PipetteInBath(vc.VCQCFunction):
    """Pipette resistance from the 3 embedded TPs; 500 ms pre-pulse baseline with RMS and leak tests.

    Notebook values (besides those in ``_vc_common``): ``PipetteResistance`` (MOhm, steady state of the
    averaged embedded TPs, computed even when baseline QC failed), ``PipetteResistanceQC``
    (``Min <= R <= Max``), ``AutoPipetteOffset``.
    """

    miesName = 'PSQ_PipetteInBath'
    analysisType = 'PB'
    setValueKeys = (PIPETTE_RESISTANCE, PIPETTE_RESISTANCE_QC, vc.chunkKey(0, 'LeakCurrent'))

    def preSet(self) -> SetConfig:
        """Validate parameters; request VC holding off (restored at set end) and auto pipette offset."""
        self.checkParams(('MaxLeakCurrent', 'NumberOfTestpulses'))
        for name in ('MinPipetteResistance', 'MaxPipetteResistance'):
            v = self.param(name, None)
            if v is None:
                raise AbortSet(f"{self.miesName}: required parameter {name!r} missing")
            if not (0 < v <= 20):
                raise AbortSet(f"{self.miesName}: invalid {name} {v}")
        self._leakFailed = False
        # one request: holding is disabled before the offset is measured
        return self.setConfig(AmplifierSettings(holdingEnabled=False, pipetteOffset='auto'))

    def preSweep(self, setSweepIndex: int, layout: EpochTable) -> SweepConfig:
        """Return DAScale 1 and the ``U_TP*`` epochs; raises AbortSet for an unsuitable stimset."""
        e0 = layout.stimsetEpoch(0)
        self._chunks = qc.prePulseChunks(e0.start, e0.duration)
        userEpochs = qc.testpulseEpochs(layout, vc.DASCALE, int(self.param('NumberOfTestpulses')))
        self._tpNames = [ep.name for ep in userEpochs if 'SubType' not in ep.tags]
        self._bl = self.baselineQC()
        self._blStatus: Optional[qc.BaselineStatus] = None
        return SweepConfig(dascale=vc.DASCALE, userEpochs=userEpochs)

    def midSweep(self, data: SweepData) -> MidSweepAction:
        """Evaluate the baseline chunk once acquired; EarlyStop when it fails (RMS or leak)."""
        if self._blStatus is not None:
            return None
        status = self._bl.evaluate(data, self._chunks)
        if not status.decided:
            return None
        self._blStatus = status
        if status.passed:
            return None
        return qc.toMidSweepAction(status.code, self.analysisType, data)

    def postSweep(self, data: SweepData) -> SweepDecision:
        """Write baseline, pipette resistance and sampling QC; return the bookkeeping decision."""
        values = self.notebook.sweep(data.sweep).values
        if self._blStatus is None:
            self.midSweep(data)
        blPassed = self._blStatus is not None and self._blStatus.passed
        self.recordBaseline(values, self._bl, blPassed)
        leakFailed = self._bl.results.get(0) is not None and (
            self._bl.results[0].leakCurrentPassed == qc.QC_FAILED
        )
        values[AUTO_PIPETTE_OFFSET] = leakFailed
        self._leakFailed |= leakFailed

        res = vc.tpResistance(data, self._tpNames)
        r = res.steadyStateResistance if res is not None else float('nan')
        rPassed = self.param('MinPipetteResistance') <= r <= self.param('MaxPipetteResistance')
        values[PIPETTE_RESISTANCE] = r
        values[PIPETTE_RESISTANCE_QC] = rPassed
        return self.finishSweep(data, values, blPassed, rPassed)

    def postSetAmplifier(self) -> AmplifierSettings:
        """Request auto pipette offset after a set in which a leak test failed."""
        return AmplifierSettings(pipetteOffset='auto') if self._leakFailed else AmplifierSettings()
