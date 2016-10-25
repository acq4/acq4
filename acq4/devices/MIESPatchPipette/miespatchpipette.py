from ..PatchPipette import PatchPipette
from acq4.util.mies import MIES
import numpy as np


class MIESPatchPipette(PatchPipette):
    """A single patch pipette channel that uses a running MIES instance to handle
    electrophysiology and pressure control.
    """
    def __init__(self, deviceManager, config, name):
        self.mies = MIES.getBridge(True)
        self.mies.sigDataReady.connect(self.updateState)
        self._headstage = config.pop('headstage')
        self.TPData = {"time": [],
                       "Rss": [],
                       "Rpeak": []}
        PatchPipette.__init__(self, deviceManager, config, name)

    def updateState(self, TPArray):
        """Got the signal from MIES that data is available, update"""
        TPDict = self.parseTPData(TPArray)
        if TPDict:
            for key, timeseries in self.TPData.iteritems():
                timeseries.append(TPDict[key])
            self.sigStateChanged.emit()

    def parseTPData(self, TPArray):
        """Take the incoming array and make a dictionary of it"""
        try:
            lastTime = self.TPData["time"][-1]
        except IndexError:
            lastTime = 0
        if TPArray[0, self._headstage] > lastTime:
            TPData = {
                "time": TPArray[0, self._headstage],
                "Rss": TPArray[1, self._headstage],
                "Rpeak": TPArray[2, self._headstage]
                }
        else:
            TPData = {}
        return TPData

    def getPatchStatus(self):
        """Return a dict describing the status of the patched cell.

        Includes keys:
        * state ('bath', 'sealing', 'on-cell', 'whole-cell', etc..)
        * resting potential
        * resting current
        * input resistance
        * access resistance
        * capacitance
        * clamp mode ('ic' or 'vc')
        * timestamp of last measurement

        """
        # maybe 'state' should be available via a different method?

    def getPressure(self):
        pass

    def setPressure(self):
        # accepts waveforms as well?
        pass

    def setState(self, state):
        if state == 'seal':
            self.mies.selectHeadstage(self._headstage)
            self.mies.setSeal()
        elif state == 'bath':
            self.mies.selectHeadstage(self._headstage)
            self.mies.setApproach()

    def setActive(self, active):
        self.mies.setHeadstageActive(self._headstage, active)

    def setSelected(self):
        self.mies.selectHeadstage(self._headstage)

    def autoPipetteOffset(self):
        self.mies.selectHeadstage(self._headstage)
        self.mies.autoPipetteOffset()

    def quit(self):
        self.mies.quit()
        super(MIESPatchPipette, self).quit()
