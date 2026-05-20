# MoveSpec: the input type for the global motion planner.
# Callers resolve named positions to coordinates before constructing a MoveSpec.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import numpy as np


if TYPE_CHECKING:
    from acq4.devices.Device import Device


@dataclass
class MoveSpec:
    """Describes where one device should end up.

    position is expressed in relative_to's local coordinate frame when relative_to is set,
    otherwise in global coordinates.  speed is a hint; the planner may tighten it for safety.

    Arguments
    ---------
    device
        The device to move.
    position
        The target position for the device, either in global coordinates or relative to another
        device.
    relative_to
        If set, the position is interpreted as relative to this device's position. That
    speed
        Optional speed hint for the move, e.g. "fast", "slow", or a numeric speed in m/s.  The
        planner may ignore or modify this for safety.
    """

    device: "Device"
    position: np.ndarray
    relative_to: Optional["Device"] = None
    speed: str | float = None
    kwargs: dict = field(default_factory=dict)

    def __post_init__(self):
        self.position = np.asarray(self.position, dtype=float)
        if not hasattr(self.device, "moveToGlobalNoPlanning") and not hasattr(
            self.device, "setGlobalPosition"
        ):
            raise ValueError(
                f"Device {self.device!r} has no movement capability "
                f"(no moveToGlobalNoPlanning or setGlobalPosition)."
            )
