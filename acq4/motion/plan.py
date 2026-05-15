# Pure-data plan tree produced by MotionPlanner.plan().
# No side effects; fully inspectable for unit tests.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Union

import numpy as np

if TYPE_CHECKING:
    from acq4.devices.Device import Device


@dataclass
class AtomicMove:
    """Move one device to a position in global coordinates."""

    device: "Device"
    position: np.ndarray
    speed: str
    explanation: str = ""

    def __post_init__(self):
        self.position = np.asarray(self.position, dtype=float)


@dataclass
class SequentialGroup:
    """Execute child steps one after another."""

    steps: list = field(default_factory=list)
    explanation: str = ""


@dataclass
class ParallelGroup:
    """Start all child steps simultaneously, then wait for all to finish."""

    steps: list = field(default_factory=list)
    explanation: str = ""


MovePlanStep = Union[AtomicMove, SequentialGroup, ParallelGroup]
