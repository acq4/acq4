import numpy as np
from acq4.util import Qt
from pyqtgraph import ptime
from acq4.devices.PatchPipette.testpulse import TestPulse


class MockPatch(object):
    def __init__(self, pipette):
        self.pipette = pipette
        self.enabled = False
        self.widget = MockPatchUI(self)

        self.resetState()

        pipette._testPulseThread.setParameters(testPulseClass=self.createTestPulse)
    
    def createTestPulse(self, dev, taskParams, result):
        tp = TestPulse(dev, taskParams, result)
        if self.enabled:
            tp._analysis = self.generateAnalysis()
        return tp

    def resetState(self):
        self.radius = 7e-6
        self.sealResistance = 0
        self.maxSealResistance = 2e9
        self.pipResistance = 5e6
        self.accessResistance = 1e12
        self.capacitance = 2e-12
        self.membranePotential = -70e-3
        self.inputResistance = 150e6
        self.lastUpdate = ptime.time()

    def generateAnalysis(self):
        now = ptime.time()
        dt = now - self.lastUpdate
        self.lastUpdate = now

        pip = self.pipette
        targetDistance = np.linalg.norm(pip.pipetteDevice.targetPosition() - pip.pipetteDevice.globalPosition())
        if pip.pressureDevice.source == 'regulator':
            pressure = pip.pressureDevice.pressure
        else:
            pressure = 0
        mode = pip.clampDevice.getMode()
        holding = pip.clampDevice.getHolding(mode)

        pipResistance = self.pipResistance
        if self.widget.foulBtn.isChecked():
            pipResistance += 3e6

        # print("target: %s um   pressure: %s kPa" % (targetDistance*1e6, pressure*1e-3))
        if pressure > 0:
            self.resetState()
            # seal resistance increases by 2 MOhm as we push in from the cell radius
            approachFactor = 5e5 * np.clip(self.radius - targetDistance, 0, 2e-6)
            self.sealResistance = 2e6 * approachFactor

        else:
            if targetDistance > self.radius:
                self.resetState()
            else:
                # seal speed can double if we add pressure
                if self.sealResistance > 0:
                    sealFactor = 1 + np.clip(-pressure / 20e3, 0, 1)
                    sealSpeed = 1.0 - np.exp(-dt / (1.0/sealFactor))
                    sealCond = 1.0 / self.sealResistance
                    maxSealCond = 1.0 / self.maxSealResistance
                    sealCond = sealCond * (1.0 - sealSpeed) + maxSealCond * sealSpeed
                    self.sealResistance = 1.0 / sealCond
                    # print("sf: %s  ss: %s  sr: %s" % (sealFactor, sealSpeed, self.sealResistance))

            if pressure < -27e3:
                # break in
                self.accessResistance = 5e6
                self.capacitance = 30e-12

        self.sealResistance = max(self.sealResistance, 100)

        ssr = pipResistance + 1.0 / (1.0/self.sealResistance + 1.0/(self.accessResistance + self.inputResistance))
        # print("ssr: %s  pr: %s  sr: %s  ar: %s  ir: %s" % (ssr, pipResistance, self.sealResistance, self.accessResistance, self.inputResistance))
        pr = pipResistance + 1.0 / (1.0/self.sealResistance + 1.0/self.accessResistance)

        cap = self.capacitance
        if self.widget.breakBtn.isChecked():
            ssr = 1e6
            pr = 1e6
            cap = 30e-12

        i = (holding - self.membranePotential) / ssr

        return {'baselinePotential': holding, 'baselineCurrent': i, 'peakResistance': pr, 'steadyStateResistance': ssr, 'capacitance': cap}


class MockPatchUI(Qt.QWidget):
    def __init__(self, mp):
        self.mockpatch = mp

        Qt.QWidget.__init__(self)
        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)
        self.enableBtn = Qt.QPushButton('Mock')
        self.layout.addWidget(self.enableBtn, 0, 0)
        self.enableBtn.setCheckable(True)
        self.enableBtn.clicked.connect(self.enableClicked)

        self.breakBtn = Qt.QPushButton('Break tip')
        self.layout.addWidget(self.breakBtn, 1, 0)
        self.breakBtn.setCheckable(True)

        self.foulBtn = Qt.QPushButton('Foul tip')
        self.layout.addWidget(self.foulBtn, 2, 0)
        self.foulBtn.setCheckable(True)

    def enableClicked(self):
        self.mockpatch.enabled = self.enableBtn.isChecked()
