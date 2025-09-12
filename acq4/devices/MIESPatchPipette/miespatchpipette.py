from collections import OrderedDict

from acq4.util.mies import MIES
from .patch_clamp import MIESPatchClamp
from .pressure_control import MIESPressureControl
from ..PatchPipette import PatchPipette

from acq4.util import Qt
from acq4.util import ptime


class MIESPatchPipette(PatchPipette):
    """
    A patch pipette device that uses a running MIES instance for electrophysiology 
    and pressure control.
    
    Configuration options:
    
    * **headstage** (int, required): MIES headstage number to use for this pipette
    
    * **pipetteDevice** (str, optional): Name of Pipette device for tip tracking
    
    * **sonicatorDevice** (str, optional): Name of sonicator device for cleaning
    
    * **stateManagerClass** (str, optional): Custom state manager class name
    
    * All other options from PatchPipette base class are supported
    
    This device automatically creates internal MIESPatchClamp and MIESPressureControl 
    devices named "{name}_clamp" and "{name}_pressure" respectively.
    
    Example configuration::
    
        PatchPipette1:
            driver: 'MIESPatchPipette'
            headstage: 0
            pipetteDevice: 'Pipette1'
            sonicatorDevice: 'Sonicator1'
    
    Requires a running MIES instance with configured headstage hardware.
    """

    def __init__(self, deviceManager, config, name):
        self.mies = MIES.getBridge()
        self._headstage = config.pop('headstage')

        # create pressure and clamp devices
        clampName = f"{name}_clamp"
        self._mies_clamp = MIESPatchClamp(
            deviceManager, 
            config={'headstage': self._headstage},
            name=clampName)

        pressureName = f"{name}_pressure"
        self._mies_pressure = MIESPressureControl(
            deviceManager, 
            config={'headstage': self._headstage},
            name=pressureName)

        config.update({
            'pressureDevice': pressureName,
        })
        PatchPipette.__init__(self, deviceManager, config, name)
        self.clampDevice = self._mies_clamp

        self.clampDevice.sigStateChanged.connect(self.clampStateChanged)

    def setActive(self, active):
        self.mies.setHeadstageActive(self._headstage, active)
        PatchPipette.setActive(self, active)

    def setSelected(self):
        self.mies.selectHeadstage(self._headstage)

    def clampStateChanged(self, state):
        self.emitNewEvent('clamp_state_change', state)

    def emitNewEvent(self, eventType, eventData=None):
        newEv = OrderedDict([
            ('device', self.name()),
            ('event_time', ptime.time()),
            ('event', eventType),
        ])
        if eventData is not None:
            newEv.update(eventData)
        self.sigNewEvent.emit(self, newEv)
