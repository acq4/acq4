"""Plain recording for stimsets that have no MIES analysis function (e.g. EXTPEXPEND)."""

from __future__ import annotations

from ..core import MIN_SAMPLE_INTERVAL, ClampMode, SetConfig, SetResult, SweepConfig, SweepDecision
from .base import AnalysisFunction

DEFAULT_SAMPLE_INTERVAL = MIN_SAMPLE_INTERVAL * 4  # ms, 50 kHz


def plainRecording(
    clampMode: ClampMode, sampleInterval: float = DEFAULT_SAMPLE_INTERVAL
) -> type[AnalysisFunction]:
    """Return an AnalysisFunction class that plays every sweep at DAScale 1 in *clampMode* and passes."""

    class PlainRecording(AnalysisFunction):
        miesName = ''
        analysisType = 'PLAIN'

        def preSet(self) -> SetConfig:
            return SetConfig(clampMode, sampleInterval)

        def preSweep(self, setSweepIndex, layout) -> SweepConfig:
            return SweepConfig(1.0)

        def postSweep(self, data) -> SweepDecision:
            return SweepDecision(True, 'continue')

        def postSet(self) -> SetResult:
            return SetResult(True)

    PlainRecording.clampMode = clampMode
    return PlainRecording
