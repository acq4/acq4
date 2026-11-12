"""PSQ_AccessResistanceSmoke (AR): access and steady-state resistance after break-in, voltage clamp.

With infinite limits it is the rig smoke test (EXTPSMOKET): baseline noise and leak only.
"""

from __future__ import annotations

import math
from typing import Optional

from .. import qc
from ..core import AbortSet, EpochTable, MidSweepAction, SetConfig, SweepConfig, SweepData
from ..core import SweepDecision
from . import _vc_common as vc
from .base import register

ACCESS_RESISTANCE = 'AccessResistance'  # MOhm, instantaneous of the averaged embedded TPs
STEADY_STATE_RESISTANCE = 'SteadyStateResistance'  # MOhm
RESISTANCE_RATIO = 'AccessToSteadyStateRatio'  # Ra / Rss, unitless
ACCESS_RESISTANCE_QC = 'AccessResistanceQC'  # bool
RESISTANCE_RATIO_QC = 'ResistanceRatioQC'  # bool


@register
class AccessResistanceSmoke(vc.VCQCFunction):
    """Ra and Rss from the 3 embedded TPs; baseline ``U_BLS0`` on stimset epoch 0 (RMS and leak).

    Notebook values (besides those in ``_vc_common``): ``AccessResistance``, ``SteadyStateResistance``
    (MOhm, NaN unless baseline QC passed), ``AccessToSteadyStateRatio``, ``AccessResistanceQC``
    (``0 < Ra < MaxAccessResistance``) and ``ResistanceRatioQC``
    (``0 < ratio < MaxAccessToSteadyStateResistanceRatio / 100``); with an infinite limit the
    lower bound is not applied.
    """

    miesName = 'PSQ_AccessResistanceSmoke'
    analysisType = 'AR'
    setValueKeys = (
        ACCESS_RESISTANCE,
        STEADY_STATE_RESISTANCE,
        RESISTANCE_RATIO,
        ACCESS_RESISTANCE_QC,
        RESISTANCE_RATIO_QC,
    )

    def preSet(self) -> SetConfig:
        """Validate parameters; no amplifier changes."""
        self.checkParams(('BaselineChunkLength', 'MaxLeakCurrent', 'NumberOfTestpulses'))
        for name in ('MaxAccessResistance', 'MaxAccessToSteadyStateResistanceRatio'):
            v = self.param(name, None)
            if v is None:
                raise AbortSet(f"{self.miesName}: required parameter {name!r} missing")
        if not self.param('MaxAccessResistance') > 0:
            raise AbortSet(f"{self.miesName}: invalid MaxAccessResistance")
        if not self.param('MaxAccessToSteadyStateResistanceRatio') >= 0:
            raise AbortSet(f"{self.miesName}: invalid MaxAccessToSteadyStateResistanceRatio")
        return self.setConfig()

    def preSweep(self, setSweepIndex: int, layout: EpochTable) -> SweepConfig:
        """Return DAScale 1, the ``U_TP*`` epochs and ``U_BLS0``; AbortSet for an unsuitable stimset."""
        tps = qc.testpulseEpochs(layout, vc.DASCALE, int(self.param('NumberOfTestpulses')))
        bls = qc.baselineSelectionEpochs(
            layout, [0], self.param('BaselineChunkLength', qc.BL_CHUNK_LENGTH)
        )
        self._tpNames = [ep.name for ep in tps if 'SubType' not in ep.tags]
        self._chunks = [qc.ChunkSpec(0, bls[0].start, bls[0].duration, 'generic')]
        self._bl = self.baselineQC()
        self._blStatus: Optional[qc.BaselineStatus] = None
        return SweepConfig(dascale=vc.DASCALE, userEpochs=tps + bls)

    def midSweep(self, data: SweepData) -> MidSweepAction:
        """Evaluate ``U_BLS0`` once acquired; EarlyStop when it fails."""
        if self._blStatus is not None and self._blStatus.passed:
            return None
        self._blStatus = self._bl.evaluate(data, self._chunks)
        if self._blStatus.passed:
            return None
        return qc.toMidSweepAction(self._blStatus.code, self.analysisType, data)

    def postSweep(self, data: SweepData) -> SweepDecision:
        """Write baseline, resistances and sampling QC; return the bookkeeping decision."""
        values = self.notebook.sweep(data.sweep).values
        if self._blStatus is None or not self._blStatus.decided:
            self.midSweep(data)
        blPassed = self._blStatus.passed
        self.recordBaseline(values, self._bl, blPassed)

        ra = rss = float('nan')
        if blPassed:
            res = vc.tpResistance(data, self._tpNames)
            if res is not None:
                ra, rss = res.instantaneousResistance, res.steadyStateResistance
        ratio = ra / rss if rss != 0 else math.copysign(math.inf, ra)
        raPassed = vc.belowLimit(ra, self.param('MaxAccessResistance'))
        ratioPassed = vc.belowLimit(
            ratio, self.param('MaxAccessToSteadyStateResistanceRatio') / 100
        )
        values[ACCESS_RESISTANCE] = ra
        values[STEADY_STATE_RESISTANCE] = rss
        values[RESISTANCE_RATIO] = ratio
        values[ACCESS_RESISTANCE_QC] = raPassed
        values[RESISTANCE_RATIO_QC] = ratioPassed
        return self.finishSweep(data, values, blPassed, raPassed, ratioPassed)
