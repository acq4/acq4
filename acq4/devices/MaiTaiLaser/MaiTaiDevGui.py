from PyQt4 import QtGui, QtCore
from acq4.Manager import getManager, logExc, logMsg
from acq4.devices.Laser.devTemplate import Ui_Form
from acq4.devices.Laser.LaserDevGui import LaserDevGui
from maiTaiTemplate import Ui_MaiTaiStatusWidget
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
        self._maitaiui = Ui_MaiTaiStatusWidget()
        self._maitaiwidget = QtGui.QWidget()
        self._maitaiui.setupUi(self._maitaiwidget)
        # insert Mai Tai widget in Laser GUI
        self.ui.verticalLayout_2.insertWidget(0, self._maitaiwidget)
        
        if self.dev.isLaserOn():
            self.onOffToggled(True)
            self._maitaiui.turnOnOffBtn.setChecked(True)
            if self.dev.getInternalShutter():
                self.internalShutterToggled(True)
                self._maitaiui.InternalShutterBtn.setChecked(True)
            self._maitaiui.InternalShutterBtn.setEnabled(True)
        else:
            self._maitaiui.InternalShutterBtn.setEnabled(False)
                
        #self.ui.MaiTaiGroup.hide()
        #self.ui.turnOnOffBtn.hide()
        
        self._maitaiui.pumpCurrentSpin.setOpts(suffix='%', siPrefix=False, dec=False, step=0.1)
        self._maitaiui.greenPowerSpin.setOpts(suffix='W', siPrefix=True, dec=False, step=0.1)
        
        self.pumpPowerModes = {-2:'Current %', -3:'IR Power',-4:'Green Power'}
        pumpMode = self.dev.getPumpMode() # {'PCUR':'Current %', 'PPOW':'Green Power', 'POW':'IR Power'}
        self.setPumpMode(pumpMode)
        
        
        startWL = self.dev.getWavelength()
        self._maitaiui.wavelengthSpin_2.setOpts(suffix='m', siPrefix=True, dec=False, step=5e-9)
        self._maitaiui.wavelengthSpin_2.setValue(startWL)
        self._maitaiui.wavelengthSpin_2.setOpts(bounds=self.dev.getWavelengthRange())
        self._maitaiui.currentWaveLengthLabel.setText(siFormat(startWL, suffix='m'))
        
        
        self._maitaiui.wavelengthSpin_2.valueChanged.connect(self.wavelengthSpinChanged)
        self._maitaiui.powerButtonGroup.buttonClicked.connect(self.powerModeChanged)
        self._maitaiui.pumpCurrentSpin.valueChanged.connect(self.pumpCurrentSpinChanged)
        self._maitaiui.greenPowerSpin.valueChanged.connect(self.greenPowerSpinChanged)
        
        
        self._maitaiui.turnOnOffBtn.toggled.connect(self.onOffToggled)
        self._maitaiui.InternalShutterBtn.toggled.connect(self.internalShutterToggled)
        self._maitaiui.ExternalShutterBtn.toggled.connect(self.externalShutterToggled)
        self._maitaiui.externalSwitchBtn.toggled.connect(self.externalSwitchToggled)
        self._maitaiui.linkLaserExtSwitchCheckBox.toggled.connect(self.linkLaserExtSwitch)
        self._maitaiui.alignmentModeBtn.toggled.connect(self.alignmentModeToggled)


        self.dev.sigOutputPowerChanged.connect(self.outputPowerChanged)
        self.dev.sigSamplePowerChanged.connect(self.samplePowerChanged)
        self.dev.sigPumpPowerChanged.connect(self.pumpPowerChanged)
        self.dev.sigPumpCurrentChanged.connect(self.pumpCurrentChanged)
        self.dev.sigProgrammedPChanged.connect(self.programmedPowerChanged)
        self.dev.sigRelativeHumidityChanged.connect(self.relHumidityChanged)
        self.dev.sigPulsingStateChanged.connect(self.pulsingStateChanged)
        self.dev.sigWavelengthChanged.connect(self.wavelengthChanged)
        self.dev.sigModeChanged.connect(self.modeChanged)
        self.dev.sigP2OptimizationChanged.connect(self.p2OptimizationChanged)
        self.dev.sigHistoryBufferChanged.connect(self.historyBufferChanged)
        self.dev.sigHistoryBufferPumpLaserChanged.connect(self.historyBufferPumpLaserChanged)
        
    def onOffToggled(self, b):
        if b:
            self.dev.switchLaserOn()
            self._maitaiui.turnOnOffBtn.setText('Turn Off Laser')
            self._maitaiui.turnOnOffBtn.setStyleSheet("QLabel {background-color: #C00}") 
            self._maitaiui.EmissionLabel.setText('Emission ON')
            self._maitaiui.EmissionLabel.setStyleSheet("QLabel {color: #C00}")
            self._maitaiui.InternalShutterBtn.setEnabled(True)
        else:
            self.dev.switchLaserOff()
            self.shutterToggled(False)
            self._maitaiui.turnOnOffBtn.setText('Turn On Laser')
            self._maitaiui.turnOnOffBtn.setStyleSheet("QLabel {background-color: None}")
            self._maitaiui.EmissionLabel.setText('Emission Off')
            self._maitaiui.EmissionLabel.setStyleSheet("QLabel {color: None}") 
            self._maitaiui.InternalShutterBtn.setEnabled(False)
            
    def internalShutterToggled(self, b):
        if b:
            if self._maitaiui.linkLaserExtSwitchCheckBox.isChecked():
                self.dev.externalSwitchOFF()
                self._maitaiui.externalSwitchBtn.setChecked(False)
                self._maitaiui.externalSwitchBtn.setText('External Switch OFF')
            self.dev.openInternalShutter()
            self._maitaiui.InternalShutterBtn.setText('Close Laser Shutter')
            self._maitaiui.InternalShutterLabel.setText('Laser Shutter Open')
            self._maitaiui.InternalShutterLabel.setStyleSheet("QLabel {color: #0A0}")
        elif not b:
            self.dev.closeInternalShutter()
            self._maitaiui.InternalShutterBtn.setText('Open Laser Shutter')
            #self._maitaiui.shutterBtn.setStyleSheet("QLabel {background-color: None}")
            self._maitaiui.InternalShutterLabel.setText('Laser Shutter Closed')
            self._maitaiui.InternalShutterLabel.setStyleSheet("QLabel {color: None}")
            if self._maitaiui.linkLaserExtSwitchCheckBox.isChecked():
                self.dev.externalSwitchON()
                self._maitaiui.externalSwitchBtn.setChecked(True)
                self._maitaiui.externalSwitchBtn.setText('External Switch ON')
    
    def externalShutterToggled(self, b):
        if b:
            self.dev.openShutter()
            self._maitaiui.ExternalShutterBtn.setText('Close External Shutter')
            self._maitaiui.ExternalShutterLabel.setText('External Shutter Open')
            self._maitaiui.ExternalShutterLabel.setStyleSheet("QLabel {color: #10F}") 
        elif not b:
            self.dev.closeShutter()
            self._maitaiui.ExternalShutterBtn.setText('Open External Shutter')   
            self._maitaiui.ExternalShutterLabel.setText('External Shutter Closed')
            self._maitaiui.ExternalShutterLabel.setStyleSheet("QLabel {color: None}")
    
    def setPumpMode(self, newPumpMode):
        if newPumpMode == 'Current %':
            self._maitaiui.currentBtn.setChecked(True)
            self._maitaiui.pumpCurrentSpin.setEnabled(True)
            self._maitaiui.greenPowerSpin.setEnabled(False)
            self.currentPumpMode = 'Current %'
        elif newPumpMode == 'Green Power':
            self._maitaiui.greenPowerBtn.setChecked(True)
            self._maitaiui.pumpCurrentSpin.setEnabled(False)
            self._maitaiui.greenPowerSpin.setEnabled(True)
            self.currentPumpMode = 'Green Power'
        elif newPumpMode == 'IR Power':
            self._maitaiui.irPowerBtn.setChecked(True)
            self._maitaiui.pumpCurrentSpin.setEnabled(False)
            self._maitaiui.greenPowerSpin.setEnabled(False)
            self.currentPumpMode = 'IR Power'
    
    def externalSwitchToggled(self,b):
        if b:
            self.dev.externalSwitchON()
            self._maitaiui.externalSwitchBtn.setText('External Switch ON')
        elif not b:
            self.dev.externalSwitchOFF()
            self._maitaiui.externalSwitchBtn.setText('External Switch OFF')
    
    def linkLaserExtSwitch(self,b):
        if b:
            self._maitaiui.externalSwitchBtn.setEnabled(False)
        elif not b:
            self._maitaiui.externalSwitchBtn.setEnabled(True)
    
    def alignmentModeToggled(self,b):
        if b:
            self.dev.acitvateAlignmentMode()
            self._maitaiui.alignmentModeBtn.setText('Alignment Mode ON')
        elif not b:
            self.dev.deactivateAlignmentMode()
            self._maitaiui.alignmentModeBtn.setText('Alignment Mode OFF')
            
    
    def wavelengthChanged(self,wl):
        if wl is None:
            self._maitaiui.currentWaveLengthLabel.setText("?")
        else:
            self._maitaiui.currentWaveLengthLabel.setText(siFormat(wl, suffix='m'))
        
    def wavelengthSpinChanged(self, value):
        self.dev.setWavelength(value)
        #if value not in self.dev.config.get('namedWavelengths', {}).keys():
        #    self._maitaiui.wavelengthCombo.setCurrentIndex(0)
    
    def pumpCurrentSpinChanged(self, value):
        if self.currentPumpMode == 'Current %':
            print('currenSpinChanged',value)
            self.dev.setPumpCurrent(value)
    
    def greenPowerSpinChanged(self, value):
        if self.currentPumpMode == 'Green Power':
            print('powerSpinChanged',value)
            self.dev.setGreenPower(value)
    
    def powerModeChanged(self):
        newPowerMode = self._maitaiui.powerButtonGroup.checkedId()
        self.dev.setPumpMode(self.pumpPowerModes[newPowerMode])
        self.setPumpMode(self.pumpPowerModes[newPowerMode])
        #self.dev.setPosition((newPos+1))
        #self.dev.setWavelength(value)
        #if value not in self.dev.config.get('namedWavelengths', {}).keys():
        #    self._maitaiui.wavelengthCombo.setCurrentIndex(0)

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
            self._maitaiui.P2OptimizationLabel.setText("?")
        elif p2Opt:
            self._maitaiui.P2OptimizationLabel.setText("ON")
        elif not p2Opt:
            self._maitaiui.P2OptimizationLabel.setText("OFF")
    
    def historyBufferChanged(self, hist):
        if hist is None:
            self._maitaiui.systemStatusLabel.setText("?")
        else:
            self._maitaiui.systemStatusLabel.setText(str(hist))
    
    def historyBufferPumpLaserChanged(self, histPL):
        if histPL is None:
            self._maitaiui.pumpLaserSystemStatusLabel.setText("?")
        else:
            self._maitaiui.pumpLaserSystemStatusLabel.setText(str(histPL))
    
    def pumpPowerChanged(self,pumpPower):
        if pumpPower is None:
            self._maitaiui.pumpPowerLabel.setText("?")
        else:
            self._maitaiui.pumpPowerLabel.setText(siFormat(pumpPower, suffix='W'))
            
        if self.currentPumpMode != 'Green Power':
            self._maitaiui.greenPowerSpin.setValue(pumpPower)
        
    def pumpCurrentChanged(self,pumpCurrent):
        if self.currentPumpMode != 'Current %':
            #if pumpCurrent is None:
            #    self._maitaiui.pumpPowerLabel.setText("?")
            #else:
            self._maitaiui.pumpCurrentSpin.setValue(pumpCurrent)
    
    def programmedPowerChanged(self,programmedPower):
        if programmedPower is None:
            self._maitaiui.irPowerLabel.setText("?")
        else:
            self._maitaiui.irPowerLabel.setText(siFormat(programmedPower, suffix='W'))
    
    
    def relHumidityChanged(self, humidity):
        if humidity is None:
            self._maitaiui.relHumidityLabel.setText("?")
        else:
            self._maitaiui.relHumidityLabel.setText(siFormat(humidity, suffix='%'))
    
    def modeChanged(self, mode):
        if mode is None:
            self._maitaiui.pumpModeLabel.setText("?")
        else:
            self._maitaiui.pumpModeLabel.setText(mode)
    
    def pulsingStateChanged(self, pulsing):
        if pulsing:
            self._maitaiui.PulsingLabel.setText('Pulsing')
            self._maitaiui.PulsingLabel.setStyleSheet("QLabel {color: #EA0}")
        else:
            self._maitaiui.PulsingLabel.setText('Not Pulsing')
            self._maitaiui.PulsingLabel.setStyleSheet("QLabel {color: None}")
    
      

            
        
       
        