from __future__ import print_function

from acq4.devices.Microscope import Microscope
from acq4.drivers.zeiss import ZeissMtbSdk


class ZeissMicroscope(Microscope):
    """Microscope subclass implementing control of a Zeiss objective changer
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
