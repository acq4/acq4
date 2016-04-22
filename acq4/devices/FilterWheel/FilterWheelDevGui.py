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
        
        #self.calibrateWarning = self.dev.config.get('calibrationWarning', None)
        #self.calibrateBtnState = 0
        
        ### configure gui
        ### hide group boxes which are not related to Mai Tai function 
        #self.ui.buttonGroup.hide()
        #self.ui.wavelengthGroup.hide()
        
        # setup Mai Tai widget
        #self._maitaiui = Ui_MaiTaiStatusWidget()
        #self._maitaiwidget = QtGui.QWidget()
        #self._maitaiui.setupUi(self._maitaiwidget)
        # insert Mai Tai widget in Laser GUI
        #self.ui.verticalLayout_2.insertWidget(0, self._maitaiwidget)
        
        buttonVBox = QtGui.QVBoxLayout()
        for i in range(self.dev.getPositionCount()):
            radio = QtGui.QRadioButton(str(self.dev.positionLabels[i]))
            buttonVBox.addWidget(radio)
        buttonVBox.addStretch(1)
        self.ui.PositionGroup.setLayout(buttonVBox)
        
        
        if self.dev.getTriggerMode()==0:
            self.ui.inputTrigButton.setEnabled(True)
        elif self.dev.getTriggerMode()==1:
            self.ui.outputTrigButton.setEnabled(True)
        
        if self.dev.getSpeed()==0:
            self.ui.SlowButton.setEnabled(True)
        elif self.dev.getSpeed()==1:
            self.ui.FastButton.setEnabled(True)
        
        
        startWL = self.dev.getWavelength()
        self._maitaiui.wavelengthSpin_2.setOpts(suffix='m', siPrefix=True, dec=False, step=5e-9)
        self._maitaiui.wavelengthSpin_2.setValue(startWL)
        self._maitaiui.wavelengthSpin_2.setOpts(bounds=self.dev.getWavelengthRange())
        self._maitaiui.currentWaveLengthLabel.setText(siFormat(startWL, suffix='m'))
        
        
        #self.ui.wavelengthSpin_2.valueChanged.connect(self.wavelengthSpinChanged)
        
        
        self.ui.SlowButton.toggled.connect(self.slowSpeedToggled)
        self.ui.inputTrigButton.toggled.connect(self.inputTrigToggled)
        #self._maitaiui.InternalShutterBtn.toggled.connect(self.internalShutterToggled)
        #self._maitaiui.ExternalShutterBtn.toggled.connect(self.externalShutterToggled)
        #self._maitaiui.externalSwitchBtn.toggled.connect(self.externalSwitchToggled)
        #self._maitaiui.linkLaserExtSwitchCheckBox.toggled.connect(self.linkLaserExtSwitch)
        #self._maitaiui.alignmentModeBtn.toggled.connect(self.alignmentModeToggled)


        self.dev.sigFilterWheelPositionChanged.connect(self.positionChanged)
        self.dev.sigFilterWheelSpeedChanged.connect(self.speedChanged)
        self.dev.sigFilterWheelTrigModeChanged.connect(self.trigModeChanged)
        
    def slowSpeedToggled(self, b):
        if b:
            self.dev.setSpeed(0)
            self.ui.SlowButton.setEnabled(True)
        else:
            self.dev.setSpeed(1)
            self.ui.FastButton.setEnabled(True)
            
    def speedChanged(self, newSpeed):
        if newSpeed==0:
            self.ui.SlowButton.setEnabled(True)
        else:
            self.ui.FastButton.setEnabled(True)
    
    def inputTrigToggled(self, b):
        if b:
            self.dev.setTriggerMode(0)
            self.ui.inputTrigButton.setEnabled(True)
        elif not b:
            self.dev.setTriggerMode(1)
            self.ui.outputTrigButton.setEnabled(True)
            
    def trigModeChanged(self, newTrigMode):
        if newTrigMode==0:
            self.ui.inputTrigButton.setEnabled(True)
        else:
            self.ui.outputTrigButton.setEnabled(True)
            
    def positionChanged(self, newPos):
        print newPos
      

            
        
       
        