from PyQt4 import QtGui, QtCore
from acq4.Manager import getManager, logExc, logMsg
#from acq4.devices.Laser.devTemplate import Ui_Form
#from acq4.devices.Laser.LaserDevGui import LaserDevGui
#from maiTaiTemplate import Ui_MaiTaiStatusWidget
from FilterWheelTemplate import Ui_FilterWheelWidget
import numpy as np
from scipy import stats
from acq4.pyqtgraph.functions import siFormat
import time


class FilterWheelDevGui(QtGui.QWidget):
    
    def __init__(self, dev):
        QtGui.QWidget.__init__(self)
        self.dev = dev 
        
        self.ui = Ui_FilterWheelWidget()
        self.ui.setupUi(self)
        
        self.positionGroup = QtGui.QButtonGroup()
        self.positionButtons = []
        for i in range(self.dev.getPositionCount()):
            self.positionButtons.append(QtGui.QRadioButton(str(i+1) + ' : ' + str(self.dev.positionLabels[i])))
            self.positionGroup.addButton(self.positionButtons[-1],i)
            self.ui.PositionGridLayout.addWidget(self.positionButtons[-1],i+1,1)
            self.connect(self.positionButtons[-1], QtCore.SIGNAL("clicked()"), self.positionButtonClicked)
        self.positionGroup.setExclusive(True)
        
        self.updatePosition()
        
        if self.dev.getTriggerMode()==0:
            self.ui.inputTrigButton.setChecked(True)
        elif self.dev.getTriggerMode()==1:
            self.ui.outputTrigButton.setChecked(True)
        
        if self.dev.getSpeed()==0:
            self.ui.SlowButton.setChecked(True)
        elif self.dev.getSpeed()==1:
            self.ui.FastButton.setChecked(True)
        
        self.ui.SlowButton.toggled.connect(self.slowSpeedToggled)
        self.ui.inputTrigButton.toggled.connect(self.inputTrigToggled)


        self.dev.sigFilterWheelPositionChanged.connect(self.positionChanged)
        self.dev.sigFilterWheelSpeedChanged.connect(self.speedChanged)
        self.dev.sigFilterWheelTrigModeChanged.connect(self.trigModeChanged)
        
    def slowSpeedToggled(self, b):
        if b:
            self.dev.setSpeed(0)
            self.ui.SlowButton.setChecked(True)
        else:
            self.dev.setSpeed(1)
            self.ui.FastButton.setChecked(True)
            
    def speedChanged(self, newSpeed):
        if newSpeed==0:
            self.ui.SlowButton.setChecked(True)
        else:
            self.ui.FastButton.setChecked(True)
    
    def inputTrigToggled(self, b):
        if b:
            self.dev.setTriggerMode(0)
            self.ui.inputTrigButton.setChecked(True)
        elif not b:
            self.dev.setTriggerMode(1)
            self.ui.outputTrigButton.setChecked(True)
        
    def trigModeChanged(self, newTrigMode):
        if newTrigMode==0:
            self.ui.inputTrigButton.setChecked(True)
        else:
            self.ui.outputTrigButton.setChecked(True)
    def updatePosition(self):
        currentPos = self.dev.getPosition()
        self.positionButtons[currentPos-1].setChecked(True)
        
    def positionButtonClicked(self):
        newPos = self.positionGroup.checkedId()
        self.dev.setPosition((newPos+1))
    
    def positionChanged(self, newPos):
        self.positionButtons[newPos-1].setChecked(True)

            
        
       
        