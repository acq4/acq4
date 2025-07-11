from __future__ import print_function

from acq4.devices.Microscope import Microscope
from acq4.drivers.zeiss import ZeissMtbSdk


class ZeissMicroscope(Microscope):
    """
    Microscope device with Zeiss objective changer control via MTB API.
    
    Extends the base Microscope class with automatic objective switching
    and focus depth correction for Zeiss microscope systems.
    
    Zeiss-specific configuration options:
    
    * **safeFocusDepth** (float, required): Safe Z position for objective changes
      Stage moves to this depth before switching objectives to prevent collisions
    
    * **apiDllLocation** (str, optional): Path to MTBApi.dll file
      Uses standard location if not specified
    
    Standard Microscope configuration options (see Microscope base class):
    
    * **objectives** (dict): Objective lens definitions
    
    * **parentDevice** (str, optional): Name of parent stage device
    
    * **transform** (dict, optional): Spatial transform relative to parent device
    
    Example configuration::
    
        ZeissMicroscope:
            driver: 'ZeissMicroscope'
            parentDevice: 'Stage'
            safeFocusDepth: 5e-3
            objectives:
                0:
                    5x:
                        name: '5x 0.25na'
                        scale: 2.581e-6
                1:
                    63x:
                        name: '63x 0.9na'
                        scale: 0.205e-6
                        offset: [70e-6, 65e-6]
    """

    def __init__(self, dm, config, name):
        # We will ask a stage device to move to a safe Z position before switching
        self.safeFocusDepth = config.pop('safeFocusDepth')
        self._startDepth = None
        Microscope.__init__(self, dm, config, name)

        self.zeiss = ZeissMtbSdk.getSingleton(config.get("apiDllLocation", None))
        self.mtbRoot = self.zeiss.connect()
        self.zeiss.getObjectiveChanger().registerEventHandlers(self.zeissObjectivePosChanged, self.zeissObjectivePosSettled)

        self.objectiveIndexChanged(str(self.zeissCurrentPosition()))

    def objectiveIndexChanged(self, index):
        if str(index) == "-1":
            # When changer is in between positions
            return
        return super(ZeissMicroscope, self).objectiveIndexChanged(index)

    def zeissObjectivePosChanged(self, position):
        self.currentSwitchPosition = None

    def zeissObjectivePosSettled(self, position):
        self.objectiveIndexChanged(str(position - 1))

        # should return to same focal plane, correcting for new objective
        if self._startDepth is not None:
            self.setFocusDepth(self._startDepth).wait()
            self._startDepth = None

    def quit(self):
        print("Disconnecting Zeiss")
        self.zeiss.disconnect()
        Microscope.quit(self)

    def zeissCurrentPosition(self):
        return self.zeiss.getObjectiveChanger().getPosition() - 1

    def setObjectiveIndex(self, index):
        if int(index) == self.zeissCurrentPosition():
            return

        self._startDepth = self.getFocusDepth()
        self.moveToSafeDepth().wait()

        self.zeiss.getObjectiveChanger().setPosition(int(index) + 1)

    def moveToSafeDepth(self, speed='fast'):
        """Move focus to a safe position for switching objectives.
        """
        safeDepth = self.safeFocusDepth
        return self.setFocusDepth(safeDepth, speed=speed)
