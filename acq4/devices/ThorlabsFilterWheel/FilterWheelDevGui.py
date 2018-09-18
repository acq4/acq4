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
            self.positionButtons.append(QtGui.QRadioButton())
            self.positionGroup.addButton(self.positionButtons[-1],i)
            self.ui.PositionGridLayout.addWidget(self.positionButtons[-1],2*i+1,1)
            self.ui.PositionGridLayout.addWidget(QtGui.QLabel(str(self.dev.filters[i].name())),2*i+1,2)
            self.ui.PositionGridLayout.addWidget(QtGui.QLabel(str(self.dev.filters[i].description())),2*i+2,2)
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
        
        if self.dev.getSensorMode()==0:
            self.ui.sensorOffButton.setChecked(True)
        elif self.dev.getSensorMode()==1:
            self.ui.sensorOnButton.setChecked(True)
        
        self.ui.SlowButton.toggled.connect(self.slowSpeedToggled)
        self.ui.inputTrigButton.toggled.connect(self.inputTrigToggled)
        self.ui.sensorOffButton.toggled.connect(self.sensorModeToggled)

        self.dev.sigFilterChanged.connect(self.positionChanged)
        self.dev.sigFilterWheelSpeedChanged.connect(self.speedChanged)
        self.dev.sigFilterWheelTrigModeChanged.connect(self.trigModeChanged)
        self.dev.sigFilterWheelSensorModeChanged.connect(self.sensorModeChanged)
        
    def slowSpeedToggled(self, b):
        if b:
            self.dev.setSpeed(0)
            #self.ui.SlowButton.setChecked(True)
        else:
            self.dev.setSpeed(1)
            #self.ui.FastButton.setChecked(True)
            
    def speedChanged(self, newSpeed):
        if newSpeed==0:
            self.ui.SlowButton.setChecked(True)
        else:
            self.ui.FastButton.setChecked(True)
    
    def inputTrigToggled(self, b):
        if b:
            self.dev.setTriggerMode(0)
            #self.ui.inputTrigButton.setChecked(True)
        elif not b:
            self.dev.setTriggerMode(1)
            #self.ui.outputTrigButton.setChecked(True)
            
    def sensorModeToggled(self, b):
        if b:
            self.dev.setSensorMode(0)
            #self.ui.sensorOffButton.setChecked(True)
        elif not b:
            self.dev.setSensorMode(1)
            #self.ui.sensorOnButton.setChecked(True)
            
    def trigModeChanged(self, newTrigMode):
        if newTrigMode==0:
            self.ui.inputTrigButton.setChecked(True)
        else:
            self.ui.outputTrigButton.setChecked(True)
    
    def sensorModeChanged(self, newSensorMode):
        if newSensorMode==0:
            self.ui.sensorOffButton.setChecked(True)
        else:
            self.ui.sensorOnButton.setChecked(True)
            
    def updatePosition(self):
        currentPos = self.dev.getPosition()
        self.positionButtons[currentPos-1].setChecked(True)
        
    def positionButtonClicked(self):
        newPos = self.positionGroup.checkedId()
        self.dev.setPosition((newPos+1))
    
    def positionChanged(self, newPos):
        self.positionButtons[newPos-1].setChecked(True)

            
        
       
        