from PyQt4 import QtGui, QtCore
from acq4.Manager import getManager, logExc, logMsg
from devTemplate import Ui_Form
from LaserDevGui import LaserDevGui
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
        #self.ui.powerGroup.hide()
        self.ui.subPowerGroup.hide()
        self.ui.controlButtonGroup.hide()
        self.ui.wavelengthGroup.hide()
        
        if self.dev.isLaserOn():
            self.onOffToggled(True)
            self.ui.turnOnOffBtn.setChecked(True)
            if self.dev.getInternalShutter():
                self.internalShutterToggled(True)
                self.ui.shutterBtn_2.setChecked(True)
        
        #self.ui.MaiTaiGroup.hide()
        #self.ui.turnOnOffBtn.hide()
        
        startWL = self.dev.getWavelength()
        self.ui.wavelengthSpin_2.setOpts(suffix='m', siPrefix=True, dec=False, step=5e-9)
        self.ui.wavelengthSpin_2.setValue(startWL)
        self.ui.wavelengthSpin_2.setOpts(bounds=self.dev.getWavelengthRange())
        self.ui.currentWaveLengthLabel.setText(siFormat(startWL, suffix='m'))
        #if not self.dev.hasTunableWavelength:
        #    self.ui.wavelengthGroup.setVisible(False)
        #else:
        #    for x in self.dev.config.get('namedWavelengths', {}).keys():
        #        self.ui.wavelengthCombo.addItem(x)
        #    self.ui.wavelengthSpin.setOpts(bounds=self.dev.getWavelengthRange())

        #self.ui.wavelengthSpin.setOpts(suffix='m', siPrefix=True, dec=False, step=5e-9)
        #self.ui.wavelengthSpin.setValue(self.dev.getWavelength())
        #if not self.dev.hasTunableWavelength:
        #    self.ui.wavelengthGroup.setVisible(False)
        #else:
        #    for x in self.dev.config.get('namedWavelengths', {}).keys():
        #        self.ui.wavelengthCombo.addItem(x)
        #    self.ui.wavelengthSpin.setOpts(bounds=self.dev.getWavelengthRange())
                
        if not self.dev.hasPCell:
            self.ui.pCellGroup.hide()
        else:
            self.ui.minVSpin.setOpts(step=0.1, minStep=0.01, siPrefix=True, dec=True)
            self.ui.maxVSpin.setOpts(step=0.1, minStep=0.01, siPrefix=True, dec=True)
            self.ui.stepsSpin.setOpts(step=1, dec=True)
            
        self.ui.measurementSpin.setOpts(suffix='s', siPrefix=True, bounds=[0.0, 5.0], dec=True, step=1, minStep=0.01)
        self.ui.settlingSpin.setOpts(suffix='s', siPrefix=True, value=0.1, dec=True, step=1, minStep=0.01)
        self.ui.expectedPowerSpin.setOpts(suffix='W', siPrefix=True, bounds=[0.0, None], value=self.dev.getParam('expectedPower'), dec=True, step=0.1, minStep=0.01)
        self.ui.toleranceSpin.setOpts(step=1, suffix='%', bounds=[0.1, None], value=self.dev.getParam('tolerance'))
        
        
        if not self.dev.hasShutter:
            self.ui.shutterBtn.setEnabled(False)
        if not self.dev.hasQSwitch:
            self.ui.qSwitchBtn.hide()
            #self.ui.qSwitchBtn.setEnabled(False)
        
        
        
        
        
        ### Populate device lists
        #self.ui.microscopeCombo.setTypes('microscope')
        self.ui.meterCombo.setTypes('daqChannelGroup')
        #defMicroscope = self.dev.config.get('scope', None)     
        defPowerMeter = self.dev.config.get('defaultPowerMeter', None)
        #self.ui.microscopeCombo.setCurrentText(defMicroscope)
        self.ui.meterCombo.setCurrentText(defPowerMeter)
        #devs = self.dev.dm.listDevices()
        #for d in devs:
            #self.ui.microscopeCombo.addItem(d)
            #self.ui.meterCombo.addItem(d)
            #if d == defMicroscope:
                #self.ui.microscopeCombo.setCurrentIndex(self.ui.microscopeCombo.count()-1)
            #if d == defPowerMeter:
                #self.ui.meterCombo.setCurrentIndex(self.ui.meterCombo.count()-1)
         
        ## get scope device to connect objective changed signal
        #self.scope = getManager().getDevice(self.dev.config['scope'])
        #self.scope.sigObjectiveChanged.connect(self.objectiveChanged)
        
        ## Populate list of calibrations
        #self.microscopes = []
        self.updateCalibrationList()
        
        ## get scope device to connect objective changed signal
        #self.scope = None
        #while self.scope == None:
            #for m in self.microscopes:
                #try:
                    #self.scope = getManager().getDevice(m)
                #except:
                    #pass
        

        ## make connections
        self.ui.calibrateBtn.focusOutEvent = self.calBtnLostFocus
        
        self.ui.calibrateBtn.clicked.connect(self.calibrateClicked)
        self.ui.deleteBtn.clicked.connect(self.deleteClicked)
        self.ui.currentPowerRadio.toggled.connect(self.currentPowerToggled)
        self.ui.expectedPowerRadio.toggled.connect(self.expectedPowerToggled)
        self.ui.expectedPowerSpin.valueChanged.connect(self.expectedPowerSpinChanged)
        self.ui.toleranceSpin.valueChanged.connect(self.toleranceSpinChanged)
        self.ui.wavelengthSpin_2.valueChanged.connect(self.wavelengthSpinChanged)
        self.ui.wavelengthCombo.currentIndexChanged.connect(self.wavelengthComboChanged)
        #self.ui.microscopeCombo.currentIndexChanged.connect(self.microscopeChanged)
        self.ui.meterCombo.currentIndexChanged.connect(self.powerMeterChanged)
        self.ui.channelCombo.currentIndexChanged.connect(self.channelChanged)
        #self.ui.measurementSpin.valueChanged.connect(self.measurmentSpinChanged)
        #self.ui.settlingSpin.valueChanged.connect(self.settlingSpinChanged)
        self.ui.turnOnOffBtn.toggled.connect(self.onOffToggled)
        self.ui.internalShutterBtn.toggled.connect(self.internalShutterToggled)
        self.ui.qSwitchBtn.toggled.connect(self.qSwitchToggled)
        self.ui.checkPowerBtn.clicked.connect(self.dev.outputPower)
        self.ui.powerAlertCheck.toggled.connect(self.powerAlertToggled)
        
        self.ui.GDDEnableCheck.toggled.connect(self.GDDEnableToggled)
        self.ui.GDDSpin.valueChanged.connect(self.GDDSpinChanged)

        self.dev.sigOutputPowerChanged.connect(self.outputPowerChanged)
        self.dev.sigSamplePowerChanged.connect(self.samplePowerChanged)
        self.dev.sigPumpPowerChanged.connect(self.pumpPowerChanged)
        self.dev.sigRelativeHumidityChanged.connect(self.relHumidityChanged)
        self.dev.sigPulsingStateChanged.connect(self.pulsingStateChanged)
        self.dev.sigWavelengthChanged.connect(self.wavelengthChanged)
        
        try:
            self.dev.outputPower()  ## check laser power
        except:
            pass
        
        self.powerMeterChanged() ## populate channel combo for default power meter

    def GDDEnableToggled(self, b):
        if b:
            gddlims = self.dev.getGDDMinMax()
            self.ui.GDDLimits.setText("Min %d, Max %d" % (gddlims[0], gddlims[1]))
            gddValue = self.ui.GDDSpin.value()
          #  print 'gdd Value at enable checked: ', gddValue
            self.dev.setGDD(gddValue)
        elif not b:
            self.dev.clearGDD() # turn it off. 
        
    def GDDSpinChanged(self, value):
        if self.ui.GDDEnableCheck.isChecked():
         #   print 'gdd value from spinchanged: ', value
            self.dev.setGDD(value)
        
    def onOffToggled(self, b):
        if b:
            self.dev.switchLaserOn()
            self.ui.turnOnOffBtn.setText('Turn Off Laser')
            self.ui.turnOnOffBtn.setStyleSheet("QLabel {background-color: #C00}") 
            self.ui.EmissionLabel.setText('Emission ON')
            self.ui.EmissionLabel.setStyleSheet("QLabel {color: #C00}") 
        else:
            self.dev.switchLaserOff()
            self.shutterToggled(False)
            self.ui.turnOnOffBtn.setText('Turn On Laser')
            self.ui.turnOnOffBtn.setStyleSheet("QLabel {background-color: None}")
            self.ui.EmissionLabel.setText('Emission Off')
            self.ui.EmissionLabel.setStyleSheet("QLabel {color: None}") 
            
    def currentPowerToggled(self, b):
        if b:
            self.dev.setParam(useExpectedPower=False)
    
    def expectedPowerToggled(self, b):
        if b:
            self.dev.setParam(useExpectedPower=True)
            
    def powerAlertToggled(self, b):
        if b:
            self.dev.setParam(powerAlert=True)
        else:
            self.dev.setParam(powerAlert=False)
            
    def internalShutterToggled(self, b):
        if b:
            self.dev.openInternalShutter()
            self.ui.InternalShutterBtn.setText('Close Laser Shutter')
            self.ui.InternalShutterLabel.setText('Laser Shut. Open')
            self.ui.InternalShutterLabel.setStyleSheet("QLabel {color: #0A0}") 
        elif not b:
            self.dev.closeInternalShutter()
            self.ui.InternalShutterBtn.setText('Open Laser Shutter')
            #self.ui.shutterBtn.setStyleSheet("QLabel {background-color: None}")
            self.ui.InternalShutterLabel.setText('Laser Shut. Closed')
            self.ui.InternalShutterLabel.setStyleSheet("QLabel {color: None}")
    
    def externalShutterToggled(self, b):
        if b:
            self.dev.openShutter()
            self.ui.ExternalShutterBtn.setText('Close External Shutter')
            self.ui.ExternalShutterLabel.setText('External Shut. Open')
            self.ui.ExternalShutterLabel.setStyleSheet("QLabel {color: #0A0}") 
        elif not b:
            self.dev.closeShutter()
            self.ui.ExternalShutterBtn.setText('Open External Shutter')   
            self.ui.ExternalShutterLabel.setText('External Shut. Closed')
            self.ui.ExternalShutterLabel.setStyleSheet("QLabel {color: None}")
    
    def expectedPowerSpinChanged(self, value):
        self.dev.setParam(expectedPower=value)
        #self.dev.expectedPower = value
        self.dev.appendPowerHistory(value)
    
    def toleranceSpinChanged(self, value):
        self.dev.setParam(tolerance=value)
    
    def wavelengthChanged(self,wl):
        if wl is None:
            self.ui.currentWaveLengthLabel.setText("?")
        else:
            self.ui.currentWaveLengthLabel.setText(siFormat(wl, suffix='m'))
        
    def wavelengthSpinChanged(self, value):
        self.dev.setWavelength(value)
        #if value not in self.dev.config.get('namedWavelengths', {}).keys():
        #    self.ui.wavelengthCombo.setCurrentIndex(0)
    
    def wavelengthComboChanged(self):
        if self.ui.wavelengthCombo.currentIndex() == 0: # "Set wavelength for..."
            return # not selected
        text = unicode(self.ui.wavelengthCombo.currentText())
        wl = self.dev.config.get('namedWavelengths', {}).get(text, None)
        if wl is not None:
            if len(wl) == 1:
                self.ui.wavelengthSpin.setValue(wl)
            elif len(wl) > 1:
                self.ui.wavelengthSpin.setValue(wl[0])
                gddValue = self.ui.GDDSpin.setValue(wl[1])
            else:
                print 'bad entry in devices.cfg for wavelength, GDD value'
    #def microscopeChanged(self):
        #pass
    
    def powerMeterChanged(self):
        powerDev = getManager().getDevice(self.ui.meterCombo.currentText())
        channels = powerDev.listChannels()
        self.ui.channelCombo.clear()
        for k in channels.keys():
            self.ui.channelCombo.addItem(k)
        self.channelChanged()
            
    def channelChanged(self):   
        powerDev = getManager().getDevice(self.ui.meterCombo.currentText())
        channels = powerDev.listChannels()
        text = str(self.ui.channelCombo.currentText())
        if text is not '':
            sTime = channels[text].get('settlingTime', None)
            mTime = channels[text].get('measurementTime', None)
        else:
            return
            
        if sTime is not None:
            self.ui.settlingSpin.setValue(sTime)
        if mTime is not None:
            self.ui.measurementSpin.setValue(mTime)
            
    

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
            
    def pumpPowerChanged(self,pumpPower):
        if pumpPower is None:
            self.ui.pumpPowerLabel.setText("?")
        else:
            self.ui.pumpPowerLabel.setText(siFormat(pumpPower, suffix='W'))
    
    def relHumidityChanged(self, humidity):
        if humidity is None:
            self.ui.relHumidityLabel.setText("?")
        else:
            self.ui.relHumidityLabel.setText(siFormat(humidity, suffix='%'))
    
    def pulsingStateChanged(self, pulsing):
        if pulsing: 
            self.ui.PulsingLabel.setStyleSheet("QLabel {color: #EF0}")
        else:
            self.ui.PulsingLabel.setStyleSheet("QLabel {color: None}")
    
    ## Calibration options below
    def updateCalibrationList(self):
        self.ui.calibrationList.clear()
        for opticState, wavelength, trans, power, date in self.dev.getCalibrationList():
            item = QtGui.QTreeWidgetItem([str(opticState), str(wavelength), '%.2f' %(trans*100) + '%', siFormat(power, suffix='W'), date])
            item.key = opticState
            self.ui.calibrationList.addTopLevelItem(item)
            
    def calibrateClicked(self):
        if self.calibrateBtnState == 0 and self.calibrateWarning is not None:
            self.ui.calibrateBtn.setText(self.calibrateWarning)
            self.calibrateBtnState = 1
        elif self.calibrateBtnState == 1 or self.calibrateWarning is None:
            try:
                self.ui.calibrateBtn.setEnabled(False)
                self.ui.calibrateBtn.setText('Calibrating...')
                #scope = str(self.ui.microscopeCombo.currentText())
                powerMeter = unicode(self.ui.meterCombo.currentText())
                mTime = self.ui.measurementSpin.value()
                sTime = self.ui.settlingSpin.value()
                self.dev.calibrate(powerMeter, mTime, sTime)
                self.updateCalibrationList()
            except:
                raise
            finally:
                self.resetCalibrateBtnState()
                
    def resetCalibrateBtnState(self):
        self.calibrateBtnState = 0
        self.ui.calibrateBtn.setEnabled(True)
        self.ui.calibrateBtn.setText('Calibrate')
        
    def calBtnLostFocus(self, ev):
        self.resetCalibrateBtnState()
    
    
    def deleteClicked(self):
        #self.dev.outputPower()
        cur = self.ui.calibrationList.currentItem()
        if cur is None:
            return
        #scope = str(cur.text(0))
        #opticState = str(cur.text(0))
        opticState = cur.key
        
        index = self.dev.getCalibrationIndex()
        
        del index[opticState]

        self.dev.writeCalibrationIndex(index)
        self.updateCalibrationList()
    

            
        
       
        