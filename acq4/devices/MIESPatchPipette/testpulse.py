from acq4.devices.PatchPipette.testpulse import TestPulseThread
from acq4.util import Qt


class MIESTestPulseThread(TestPulseThread):
    """Run periodic test pulses over MIES bridge.

    Note: we do not actually start a thread here since the TP is run in the MIES process instead
    """
    sigTestPulseFinished = Qt.Signal(object, object)  # device, result
    started = Qt.Signal()
    finished = Qt.Signal()

    def __init__(self, dev, params):
        TestPulseThread.__init__(self, dev, params)
        self.dev = dev
        self._headstage = dev._headstage
        dev.mies.sigDataReady.connect(self.newTestPulse)

    def newTestPulse(self, data):
        """Got the signal from MIES that data is available, update"""
        tp = TestPulse(self.dev, data[:, self._headstage])
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

    def start(self):
        pass

    def stop(self, block=False):
        pass

    def run(self):
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
        self.analysis_l = {
            'steady_state_resistance': data[1],
            'peak_resistance': data[2],
            'capacitance': 0,
        }

    @property
    def data(self):
        return None

    def startTime(self):
        return self.result['startTime']

    def clampMode(self):
        return self.taskParams['clampMode']

    def analysis(self):
        return self.analysis_l.copy()

    def getFitData(self):
        return None
