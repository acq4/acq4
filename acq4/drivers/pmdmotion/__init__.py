"""Driver for PMD Magellan motion control ICs (Dover SmartStage) over RS-485."""
from .backend import MagellanBackend
from .driver import MagellanPMD
from .protocol import (
    ChecksumError,
    CommunicationError,
    CommutationError,
    LimitError,
    MagellanError,
    NotCommutatedError,
    PMDError,
)
