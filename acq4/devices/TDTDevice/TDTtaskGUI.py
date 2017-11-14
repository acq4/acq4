from PyQt4 import QtCore, QtGui
from acq4.devices.Device import TaskGui

class TDTTaskGui(TaskGui):
    
    def __init__(self, dev, taskRunner):
        TaskGui.__init__(self, dev, taskRunner)
        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)
        self.attenSpin = QtGui.QSpinBox()
        self.attenSpin.setMaximum(120)
        self.attenSpin.setMinimum(0)
        self.attenSpin.setValue(30)
        self.layout.addWidget(self.attenSpin)

    def generateTask(self, params=None):
        return {'PA5.1': {'attenuation': self.attenSpin.value()}}

    def saveState(self):
        """Return a dictionary representing the current state of the widget."""
        return {'attenuation':self.attenSpin.value()}

    def restoreState(self, state):
        """Restore the state of the widget from a dictionary previously generated using saveState"""
        attenuation = state.get('attenuation', 30)
        self.attenSpin.setValue(attenuation)