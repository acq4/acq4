# -*- coding: utf-8 -*-
from __future__ import print_function

from acq4.devices.Device import Device
from acq4.util import Qt


class PatchClamp(Device):
    """Base class for all patch clamp amplifier devices.
    
    Signals
    -------
    sigStateChanged(state)
        Emitted when any state parameters have changed
    sigHoldingChanged(self, clamp_mode)
        Emitted when the holding value for any clamp mode has changed
    """

    sigStateChanged = Qt.Signal(object)  # state
    sigHoldingChanged = Qt.Signal(object, object)  # self, mode

    def __init__(self, deviceManager, config, name):
        Device.__init__(self, deviceManager, config, name)

    def getState(self):
        """Return a dictionary of active state parameters
        """
        raise NotImplementedError()

    def getParam(self, param):
        """Return the value of a single state parameter
        """
        raise NotImplementedError()

    def setParam(self, param, value):
        """Set the value of a single state parameter
        """
        raise NotImplementedError()

    def getHolding(self, mode=None):
        """Return the holding value for a specific clamp mode.
        
        If no clamp mode is given, then return the holding value for the currently active clamp mode.
        """
        raise NotImplementedError()

    def setHolding(self, mode=None, value=None):
        """Set the holding value for a specific clamp mode.
        """
        raise NotImplementedError()

    def autoPipetteOffset(self):
        """Automatically set the pipette offset.
        """
        raise NotImplementedError()

    def autoBridgeBalance(self):
        """Automatically set the bridge balance.
        """
        raise NotImplementedError()

    def autoCapComp(self):
        """Automatically configure capacitance compensation.
        """
        raise NotImplementedError()

    def getMode(self):
        """Get the currently active clamp mode ('IC', 'VC', etc.)
        """
        raise NotImplementedError()

    def setMode(self, mode):
        """Set the currently active clamp mode ('IC', 'VC', etc.)
        """
        raise NotImplementedError()

    def getDAQName(self, channel):
        """Return the name of the DAQ device that performs digitization for this amplifier channel.
        """
        raise NotImplementedError()
