"""PSQ_SealEvaluation (SE): seal resistance from two groups of 3 embedded TPs, voltage clamp."""

from __future__ import annotations

import math

import numpy as np

from .. import qc
from ..core import AbortSet, EpochTable, SetConfig, SweepConfig, SweepData, SweepDecision
from . import _vc_common as vc
from .base import register

TEST_PULSE_GROUP = 'TestPulseGroup'  # 'Both' | 'First' | 'Second'
SEAL_RESISTANCE_A = 'SealResistanceA'  # MOhm, NaN when group A is not selected
SEAL_RESISTANCE_B = 'SealResistanceB'  # MOhm
SEAL_RESISTANCE_MAX = 'SealResistanceMax'  # MOhm
SEAL_RESISTANCE_QC = 'SealResistanceQC'  # bool

REQUIRED_EPOCHS = 22  # PSQ_SE_REQUIRED_EPOCHS
GROUPS = {'Both': ('A', 'B'), 'First': ('A',), 'Second': ('B',)}
# stimset epoch of each group's baseline chunk and first epochs of its three TPs
_GROUP_EPOCHS = {'A': (0, (1, 4, 7)), 'B': (11, (12, 15, 18))}


@register
class SealEvaluation(vc.VCQCFunction):
    """Seal resistance of the selected TP groups; baseline RMS on each group's ``U_BLS`` chunk.

    Baseline QC runs after the sweep only (no early stop) and needs every selected group's chunk.
    Notebook values (besides those in ``_vc_common``): ``TestPulseGroup``, ``SealResistanceA``/``B``
    (MOhm, steady state of the group's averaged TPs), ``SealResistanceMax``, ``SealResistanceQC``
    (some selected group ``>= SealThreshold``).
    """

    miesName = 'PSQ_SealEvaluation'
    analysisType = 'SE'
    rmsThresholdMax = 100.0
    setValueKeys = (SEAL_RESISTANCE_A, SEAL_RESISTANCE_B, SEAL_RESISTANCE_MAX, SEAL_RESISTANCE_QC)

    def preSet(self) -> SetConfig:
        """Validate parameters; no amplifier changes."""
        self.checkParams(('BaselineChunkLength',))
        thr = self.param('SealThreshold', None)
        if thr is None:
            raise AbortSet(f"{self.miesName}: required parameter 'SealThreshold' missing")
        if not thr > 0:
            raise AbortSet(f"{self.miesName}: invalid SealThreshold {thr}")
        self._group = self.param('TestPulseGroupSelector', 'Both')
        if self._group not in GROUPS:
            raise AbortSet(f"{self.miesName}: invalid TestPulseGroupSelector {self._group!r}")
        return self.setConfig()

    def preSweep(self, setSweepIndex: int, layout: EpochTable) -> SweepConfig:
        """Return DAScale 1, the selected groups' ``U_BLS*`` and ``U_TP*`` epochs.

        Raises AbortSet unless the stimset has 22 epochs with 0/nonzero/0 TP amplitudes and baseline
        epochs of at least BaselineChunkLength.
        """
        eps = qc.stimsetEpochs(layout)
        if len(eps) != REQUIRED_EPOCHS:
            raise AbortSet(
                f"{self.miesName}: stimset has {len(eps)} epochs, needs {REQUIRED_EPOCHS}"
            )
        groups = GROUPS[self._group]
        bls = qc.baselineSelectionEpochs(
            layout,
            [_GROUP_EPOCHS[g][0] for g in groups],
            self.param('BaselineChunkLength', qc.BL_CHUNK_LENGTH),
        )
        tps = []
        self._tpNames = {}
        for g in groups:
            names = []
            for i in _GROUP_EPOCHS[g][1]:
                tp = qc.testpulseLikeEpochs(
                    eps[i], eps[i + 1], eps[i + 2], vc.DASCALE, len(tps) // 4
                )
                tps.extend(tp)
                names.append(tp[0].name)
            self._tpNames[g] = names
        self._chunks = [
            qc.ChunkSpec(k, ep.start, ep.duration, 'generic') for k, ep in enumerate(bls)
        ]
        return SweepConfig(dascale=vc.DASCALE, userEpochs=bls + tps)

    def postSweep(self, data: SweepData) -> SweepDecision:
        """Write baseline, seal resistances and sampling QC; return the bookkeeping decision."""
        values = self.notebook.sweep(data.sweep).values
        values[TEST_PULSE_GROUP] = self._group
        bl = self.baselineQC()
        # an unacquired chunk (user stop) fails
        codes = [bl.evaluateChunk(data, c) for c in self._chunks]
        blPassed = all(code == qc.BL_PASS for code in codes)
        self.recordBaseline(values, bl, blPassed)

        r = {}
        for g in ('A', 'B'):
            res = vc.tpResistance(data, self._tpNames[g]) if g in self._tpNames else None
            r[g] = res.steadyStateResistance if res is not None else float('nan')
        selected = [r[g] for g in GROUPS[self._group]]
        rMax = float(np.nanmax(selected)) if not all(math.isnan(v) for v in selected) else math.nan
        thr = self.param('SealThreshold') * 1000  # GOhm -> MOhm
        sealPassed = any(v >= thr for v in selected)
        values[SEAL_RESISTANCE_A] = r['A']
        values[SEAL_RESISTANCE_B] = r['B']
        values[SEAL_RESISTANCE_MAX] = rMax
        values[SEAL_RESISTANCE_QC] = sealPassed
        return self.finishSweep(data, values, blPassed, sealPassed)
