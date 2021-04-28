from __future__ import print_function
import time
from acq4.util import Qt


class MIESTestPulseThread(Qt.QObject):
    """Run periodic test pulses over MIES bridge.

    Note: we do not actually start a thread here since the TP is run in the MIES process instead
    """
    sigTestPulseFinished = Qt.Signal(object, object)  # device, result
    started = Qt.Signal()
    finished = Qt.Signal()

    def __init__(self, dev, params):
        Qt.QObject.__init__(self)
        self.dev = dev
        self._headstage = dev._headstage
        dev.mies.sigDataReady.connect(self.newTestPulse)

    def newTestPulse(self, data):
        """Got the signal from MIES that data is available, update"""
        tp = TestPulse(self.dev, {}, data[:, self._headstage])

        self.sigTestPulseFinished.emit(self.dev, tp)

    def parseTPData(self, data):
        """Take the incoming array and make a dictionary of it"""
        try:
            lastTime = self.TPData["time"][-1]
        except IndexError:
            lastTime = 0
        if data[0, self._headstage] > lastTime:
            TPData = {
                "time": data[0, self._headstage],
                "Rss": data[1, self._headstage],
                "Rpeak": data[2, self._headstage]
            }
        else:
            TPData = {}
        return TPData

    def setParameters(self, **kwds):
        # what to do here? probably we don't support this for now.
        pass

    def getParameter(self, param):
        return None

    def start(self):
        pass

    def stop(self, block=False):
        pass


class TestPulse(object):
    """Represents a single test pulse run, used to analyze and extract features.
    """
    def __init__(self, dev, data):
        self.dev = dev
        self.devName = dev.name()
        self.taskParams = {
            'clampMode': 'ic',
        }
        self.result = {
            'startTime': data[0],
        }
        self.analysis = {
            'steadyStateResistance': data[1],
            'peakResistance': data[2],
        }

    @property
    def data(self):
        return None

    def startTime(self):
        return self.result['startTime']

    def clampMode(self):
        return self.taskParams['clampMode']

    def analysis(self):
        return self.analysis.copy()

    def getFitData(self):
        return None
