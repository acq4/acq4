# MoveSpec: the input type for the global motion planner.
# Callers resolve named positions to coordinates before constructing a MoveSpec.
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import numpy as np

if TYPE_CHECKING:
    from acq4.devices.Device import Device


@dataclass
class MoveSpec:
    """Describes where one device should end up.

    position is expressed in relative_to's local coordinate frame when relative_to is set,
    otherwise in global coordinates.  speed is a hint; the planner may tighten it for safety.
    """

    device: "Device"
    position: np.ndarray
    relative_to: Optional["Device"] = None
    speed: Optional[str] = None

    def __post_init__(self):
        self.position = np.asarray(self.position, dtype=float)
