from PyQt4 import QtGui, QtCore
from acq4.Manager import getManager, logExc, logMsg
from acq4.devices.Laser.devTemplate import Ui_Form
from acq4.devices.Laser.LaserDevGui import LaserDevGui
from maiTaiTemplate import Ui_MaiTai
import numpy as np
from scipy import stats
from acq4.pyqtgraph.functions import siFormat
import time


class MaiTaiDevGui(LaserDevGui):
    
    def __init__(self, dev):
        LaserDevGui.__init__(self,dev)
        self.dev = dev
        #self.dev.devGui = self  ## make this gui accessible from LaserDevice, so device can change power values. NO, BAD FORM (device is not allowed to talk to guis, it can only send signals)
        #self.ui = Ui_Form()
        #self.ui.setupUi(self)
        
        self.calibrateWarning = self.dev.config.get('calibrationWarning', None)
        self.calibrateBtnState = 0
        
        ### configure gui
        ### hide group boxes which are not related to Mai Tai function 
        self.ui.buttonGroup.hide()
        self.ui.wavelengthGroup.hide()
        
        # setup Mai Tai widget
        self.maiTai_widget = QtGui.QWidget()
        self.maiTai_widget.ui = Ui_MaiTai()
        self.maiTai_widget.ui.setupUi(self.maiTai_widget)
        
        # insert Mai Tai widget in Laser GUI
        self.layout.insertWidget(1,self.maiTai_widget)
        
        if self.dev.isLaserOn():
            self.onOffToggled(True)
            self.maiTai_widget.ui.turnOnOffBtn.setChecked(True)
            if self.dev.getInternalShutter():
                self.internalShutterToggled(True)
                self.maiTai_widget.ui.InternalShutterBtn.setChecked(True)
            self.maiTai_widget.ui.InternalShutterBtn.setEnabled(True)
        else:
            self.maiTai_widget.ui.InternalShutterBtn.setEnabled(False)
                
        #self.ui.MaiTaiGroup.hide()
        #self.ui.turnOnOffBtn.hide()
        
        startWL = self.dev.getWavelength()
        self.maiTai_widget.ui.wavelengthSpin_2.setOpts(suffix='m', siPrefix=True, dec=False, step=5e-9)
        self.maiTai_widget.ui.wavelengthSpin_2.setValue(startWL)
        self.maiTai_widget.ui.wavelengthSpin_2.setOpts(bounds=self.dev.getWavelengthRange())
        self.maiTai_widget.ui.currentWaveLengthLabel.setText(siFormat(startWL, suffix='m'))
        
        
        self.maiTai_widget.ui.wavelengthSpin_2.valueChanged.connect(self.wavelengthSpinChanged)
        
        self.maiTai_widget.ui.turnOnOffBtn.toggled.connect(self.onOffToggled)
        self.maiTai_widget.ui.InternalShutterBtn.toggled.connect(self.internalShutterToggled)
        self.maiTai_widget.ui.ExternalShutterBtn.toggled.connect(self.externalShutterToggled)
        self.maiTai_widget.ui.externalSwitchBtn.toggled.connect(self.externalSwitchToggled)
        self.maiTai_widget.ui.linkLaserExtSwitchCheckBox.toggled.connect(self.linkLaserExtSwitch)
        self.maiTai_widget.ui.alignmentModeBtn.toggled.connect(self.alignmentModeToggled)


        self.dev.sigOutputPowerChanged.connect(self.outputPowerChanged)
        self.dev.sigSamplePowerChanged.connect(self.samplePowerChanged)
        self.dev.sigPumpPowerChanged.connect(self.pumpPowerChanged)
        self.dev.sigRelativeHumidityChanged.connect(self.relHumidityChanged)
        self.dev.sigPulsingStateChanged.connect(self.pulsingStateChanged)
        self.dev.sigWavelengthChanged.connect(self.wavelengthChanged)
        self.dev.sigModeChanged.connect(self.modeChanged)
        self.dev.sigP2OptimizationChanged.connect(self.p2OptimizationChanged)
        self.dev.sigHistoryBufferChanged.connect(self.historyBufferChanged)
        
    def onOffToggled(self, b):
        if b:
            self.dev.switchLaserOn()
            self.maiTai_widget.ui.turnOnOffBtn.setText('Turn Off Laser')
            self.maiTai_widget.ui.turnOnOffBtn.setStyleSheet("QLabel {background-color: #C00}") 
            self.maiTai_widget.ui.EmissionLabel.setText('Emission ON')
            self.maiTai_widget.ui.EmissionLabel.setStyleSheet("QLabel {color: #C00}")
            self.maiTai_widget.ui.InternalShutterBtn.setEnabled(True)
        else:
            self.dev.switchLaserOff()
            self.shutterToggled(False)
            self.maiTai_widget.ui.turnOnOffBtn.setText('Turn On Laser')
            self.maiTai_widget.ui.turnOnOffBtn.setStyleSheet("QLabel {background-color: None}")
            self.maiTai_widget.ui.EmissionLabel.setText('Emission Off')
            self.maiTai_widget.ui.EmissionLabel.setStyleSheet("QLabel {color: None}") 
            self.maiTai_widget.ui.InternalShutterBtn.setEnabled(False)
            
    def internalShutterToggled(self, b):
        if b:
            if self.maiTai_widget.ui.linkLaserExtSwitchCheckBox.isChecked():
                self.dev.externalSwitchOFF()
                self.maiTai_widget.ui.externalSwitchBtn.setChecked(False)
                self.maiTai_widget.ui.externalSwitchBtn.setText('External Switch OFF')
            self.dev.openInternalShutter()
            self.maiTai_widget.ui.InternalShutterBtn.setText('Close Laser Shutter')
            self.maiTai_widget.ui.InternalShutterLabel.setText('Laser Shutter Open')
            self.maiTai_widget.ui.InternalShutterLabel.setStyleSheet("QLabel {color: #0A0}")
        elif not b:
            self.dev.closeInternalShutter()
            self.maiTai_widget.ui.InternalShutterBtn.setText('Open Laser Shutter')
            #self.maiTai_widget.ui.shutterBtn.setStyleSheet("QLabel {background-color: None}")
            self.maiTai_widget.ui.InternalShutterLabel.setText('Laser Shutter Closed')
            self.maiTai_widget.ui.InternalShutterLabel.setStyleSheet("QLabel {color: None}")
            if self.maiTai_widget.ui.linkLaserExtSwitchCheckBox.isChecked():
                self.dev.externalSwitchON()
                self.maiTai_widget.ui.externalSwitchBtn.setChecked(True)
                self.maiTai_widget.ui.externalSwitchBtn.setText('External Switch ON')
    
    def externalShutterToggled(self, b):
        if b:
            self.dev.openShutter()
            self.maiTai_widget.ui.ExternalShutterBtn.setText('Close External Shutter')
            self.maiTai_widget.ui.ExternalShutterLabel.setText('External Shutter Open')
            self.maiTai_widget.ui.ExternalShutterLabel.setStyleSheet("QLabel {color: #10F}") 
        elif not b:
            self.dev.closeShutter()
            self.maiTai_widget.ui.ExternalShutterBtn.setText('Open External Shutter')   
            self.maiTai_widget.ui.ExternalShutterLabel.setText('External Shutter Closed')
            self.maiTai_widget.ui.ExternalShutterLabel.setStyleSheet("QLabel {color: None}")
    
    def externalSwitchToggled(self,b):
        if b:
            self.dev.externalSwitchON()
            self.maiTai_widget.ui.externalSwitchBtn.setText('External Switch ON')
        elif not b:
            self.dev.externalSwitchOFF()
            self.maiTai_widget.ui.externalSwitchBtn.setText('External Switch OFF')
    
    def linkLaserExtSwitch(self,b):
        if b:
            self.maiTai_widget.ui.externalSwitchBtn.setEnabled(False)
        elif not b:
            self.maiTai_widget.ui.externalSwitchBtn.setEnabled(True)
    
    def alignmentModeToggled(self,b):
        if b:
            self.dev.acitvateAlignmentMode()
            self.maiTai_widget.ui.alignmentModeBtn.setText('Alignment Mode ON')
        elif not b:
            self.dev.deactivateAlignmentMode()
            self.maiTai_widget.ui.alignmentModeBtn.setText('Alignment Mode OFF')
            
    
    def wavelengthChanged(self,wl):
        if wl is None:
            self.maiTai_widget.ui.currentWaveLengthLabel.setText("?")
        else:
            self.maiTai_widget.ui.currentWaveLengthLabel.setText(siFormat(wl, suffix='m'))
        
    def wavelengthSpinChanged(self, value):
        self.dev.setWavelength(value)
        #if value not in self.dev.config.get('namedWavelengths', {}).keys():
        #    self.maiTai_widget.ui.wavelengthCombo.setCurrentIndex(0)
    

    def samplePowerChanged(self, power):
        if power is None:
            self.ui.samplePowerLabel.setText("?")
        else:
            self.ui.samplePowerLabel.setText(siFormat(power, suffix='W'))

    def outputPowerChanged(self, power, valid):
        if power is None:
            self.ui.outputPowerLabel.setText("?")
        else:
            self.ui.outputPowerLabel.setText(siFormat(power, suffix='W'))
        
        self.ui.outputPowerLabel.setStyleSheet("QLabel {color: #C00}")
        #if not valid:
        #    self.ui.outputPowerLabel.setStyleSheet("QLabel {color: #C00}")
        #else:
        #    self.ui.outputPowerLabel.setStyleSheet("QLabel {color: #000}")
    
    def p2OptimizationChanged(self,p2Opt):
        if p2Opt is None:
            self.maiTai_widget.ui.P2OptimizationLabel.setText("?")
        elif p2Opt:
            self.maiTai_widget.ui.P2OptimizationLabel.setText("ON")
        elif not p2Opt:
            self.maiTai_widget.ui.P2OptimizationLabel.setText("OFF")
    
    def historyBufferChanged(self, hist):
        if hist is None:
            self.maiTai_widget.ui.systemStatusLabel.setText("?")
        else:
            self.maiTai_widget.ui.systemStatusLabel.setText(str(hist))
    
    def pumpPowerChanged(self,pumpPower):
        if pumpPower is None:
            self.maiTai_widget.ui.pumpPowerLabel.setText("?")
        else:
            self.maiTai_widget.ui.pumpPowerLabel.setText(siFormat(pumpPower, suffix='W'))
    
    def relHumidityChanged(self, humidity):
        if humidity is None:
            self.maiTai_widget.ui.relHumidityLabel.setText("?")
        else:
            self.maiTai_widget.ui.relHumidityLabel.setText(siFormat(humidity, suffix='%'))
    
    def modeChanged(self, mode):
        if mode is None:
            self.maiTai_widget.ui.pumpModeLabel.setText("?")
        else:
            self.maiTai_widget.ui.pumpModeLabel.setText(mode)
    
    def pulsingStateChanged(self, pulsing):
        if pulsing:
            self.maiTai_widget.ui.PulsingLabel.setText('Pulsing')
            self.maiTai_widget.ui.PulsingLabel.setStyleSheet("QLabel {color: #EA0}")
        else:
            self.maiTai_widget.ui.PulsingLabel.setText('Not Pulsing')
            self.maiTai_widget.ui.PulsingLabel.setStyleSheet("QLabel {color: None}")
    
      

            
        
       
        