"""Driver for PMD Magellan motion control ICs (Dover SmartStage) over RS-485."""
from .magellan import MagellanPMD
from .protocol import (
    ChecksumError,
    CommunicationError,
    CommutationError,
    LimitError,
    MagellanError,
    NotCommutatedError,
    PMDError,
)
