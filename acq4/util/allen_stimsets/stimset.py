"""MIES stimset definitions (WaveBuilder WP/WPT/SegWvType) and sweep construction."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .core import ClampMode, EpochTable, TestPulseSettings


@dataclass
class EpochDef:
    """One WaveBuilder epoch. Times in ms; amplitudes in stimset units (scaled later by DAScale)."""

    type: str  # 'square' | 'ramp' | 'noise' | 'sin' | 'saw' | 'pulseTrain' | 'psc' | 'custom' | 'combine'
    duration: float
    amplitude: float = 0.0
    offset: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)  # type-specific WP/WPT values, decoded


@dataclass
class StimsetDef:
    """A MIES stimset: epochs, sweep count, ITI, and its analysis function with decoded parameters.

    ``params`` maps analysis parameter names to Python values: float for 'variable', str for 'string',
    list[float] for 'wave', list[str] for 'textwave'.
    """

    name: str  # MIES name including channel suffix, e.g. 'X1PS_SubThresh_DA_0'
    epochs: list[EpochDef]
    numSweeps: int
    iti: float  # s
    analysisFunction: Optional[str] = None
    params: dict[str, Any] = field(default_factory=dict)
    flipped: bool = False

    def wave(self, setSweepIndex: int, sampleInterval: float) -> np.ndarray:
        """Return the stimset wave for one sweep at *sampleInterval* (ms), DAScale 1, as MIES samples it."""
        raise NotImplementedError

    def epochTable(self, setSweepIndex: int, offset: float) -> EpochTable:
        """Return ``E<i>`` epochs for one sweep, shifted to start at *offset* ms, DAScale 1."""
        raise NotImplementedError


def loadStimsets(path: Path | str) -> dict[str, StimsetDef]:
    """Read every stimset from a MIES NWB (stimset file or recorded experiment), keyed by name."""
    raise NotImplementedError


@dataclass
class SweepCommand:
    """A built sweep: DA command (stimset x DAScale plus inserted TP, no holding) and its epochs."""

    command: np.ndarray  # mV (VC) or pA (IC)
    sampleInterval: float  # ms
    epochs: EpochTable
    stimsetStart: float  # ms, sweep time at which epoch E0 begins


def buildSweep(
    stimset: StimsetDef,
    setSweepIndex: int,
    dascale: float,
    sampleInterval: float,
    clampMode: ClampMode,
    testPulse: Optional[TestPulseSettings],
    userOnsetDelay: float = 0.0,
    terminationDelay: float = 0.0,
) -> SweepCommand:
    """Assemble one sweep as MIES does: inserted TP (if *testPulse*), onset delays, stimset, termination."""
    raise NotImplementedError
