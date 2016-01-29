import re
import numpy as np
from PyQt4 import QtGui, QtCore

from acq4.modules.Module import Module
from acq4 import getManager
import acq4.pyqtgraph as pg


class MultiPatch(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config) 
        
        self.win = MultiPatchWindow(self)
        self.win.show()


class MultiPatchWindow(QtGui.QWidget):
    def __init__(self, module):
        QtGui.QWidget.__init__(self)
        self.module = module

        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)

        self.matrix = QtGui.QWidget()
        self.matrixLayout = QtGui.QGridLayout()
        self.matrix.setLayout(self.matrixLayout)
        self.layout.addWidget(self.matrix, 0, 0, 1, 2)

        man = getManager()
        pipNames = man.listInterfaces('pipette')
        self.pips = [man.getDevice(name) for name in pipNames]
        self.columns = []
        self.pips.sort(key=lambda p: int(re.sub(r'[^\d]+', '', p.name())))

        for i, pip in enumerate(self.pips):
            nbtn = QtGui.QPushButton(re.sub(r'[^\d]+', '', pip.name()))
            nbtn.setCheckable(True)
            focusTipBtn = QtGui.QPushButton('Tip')
            focusTargetBtn = QtGui.QPushButton('Target')

            self.matrixLayout.addWidget(nbtn, 0, i)
            self.matrixLayout.addWidget(focusTipBtn, 1, i)
            self.matrixLayout.addWidget(focusTargetBtn, 2, i)

            btns = [nbtn, focusTipBtn, focusTargetBtn]
            self.columns.append(btns)
            for b in btns:
                b.pipette = pip

        self.moveInBtn = QtGui.QPushButton("Move in")
        self.moveOutBtn = QtGui.QPushButton("Move out")
        self.layout.addWidget(self.moveInBtn, 1, 0)
        self.layout.addWidget(self.moveOutBtn, 1, 1)

        self.moveInBtn.clicked.connect(self.moveIn)
        self.moveOutBtn.clicked.connect(self.moveOut)

    def moveIn(self):
        for pip in self.selectedPipettes():
            pip.advanceTowardTarget(10e-6)

    def moveOut(self):
        for pip in self.selectedPipettes():
            pip.retract(10e-6)

    def selectedPipettes(self):
        return [col[0].pipette for col in self.columns if col[0].isChecked()]




