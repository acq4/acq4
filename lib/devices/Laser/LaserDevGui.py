from PyQt4 import QtGui, QtCore
from lib.Manager import getManager, logExc, logMsg
from devTemplate import Ui_Form
import numpy as np
from scipy import stats
from pyqtgraph.functions import siFormat
import time


class LaserDevGui(QtGui.QWidget):
    
    def __init__(self, dev):
        QtGui.QWidget.__init__(self)
        self.dev = dev
        #self.dev.devGui = self  ## make this gui accessible from LaserDevice, so device can change power values. NO, BAD FORM (device is not allowed to talk to guis, it can only send signals)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.calibrateWarning = self.dev.config.get('calibrationWarning', None)
        self.calibrateBtnState = 0
        
        ### configure gui
        self.ui.energyCalcGroup.hide()  ## not using this for now
        
        self.ui.wavelengthSpin.setOpts(suffix='m', siPrefix=True)
        if not self.dev.hasTunableWavelength:
            self.ui.wavelengthGroup.setDisabled(True)
            self.ui.wavelengthSpin.setValue(self.dev.config.get('wavelength', None))
        else:
            self.ui.wavelengthSpin.setValue(self.dev.getWavelength())
            for x in self.dev.config.get('namedWavelengths', {}).keys():
                self.ui.wavelengthCombo.addItem(x)
                
        if not self.dev.hasPCell:
            self.ui.pCellGroup.hide()
        else:
            self.ui.minVSpin.setOpts(step=0.1, minStep=0.01, siPrefix=True, dec=True)
            self.ui.maxVSpin.setOpts(step=0.1, minStep=0.01, siPrefix=True, dec=True)
            self.ui.stepsSpin.setOpts(step=1, dec=True)
            
        self.ui.measurementSpin.setOpts(suffix='s', siPrefix=True, bounds=[0.0, 5.0], dec=True, step=1, minStep=0.01)
        self.ui.settlingSpin.setOpts(suffix='s', siPrefix=True, value=0.1, dec=True, step=1, minStep=0.01)
        self.ui.expectedPowerSpin.setOpts(suffix='W', siPrefix=True, bounds=[0.0, None], value=self.dev.getParam('expectedPower'), dec=True, step=0.1, minStep=0.01)
        self.ui.toleranceSpin.setOpts(step=1, suffix='%', bounds=[0.1, 100.0], value=self.dev.getParam('tolerance'))
        
        
        if not self.dev.hasShutter:
            self.ui.shutterBtn.setEnabled(False)
        if not self.dev.hasQSwitch:
            self.ui.qSwitchBtn.setEnabled(False)
        
        
        
        
        
        ### Populate device lists
        defMicroscope = self.dev.config.get('scope', None)     
        defPowerMeter = self.dev.config.get('defaultPowerMeter', None)
        devs = self.dev.dm.listDevices()
        for d in devs:
            self.ui.microscopeCombo.addItem(d)
            self.ui.meterCombo.addItem(d)
            if d == defMicroscope:
                self.ui.microscopeCombo.setCurrentIndex(self.ui.microscopeCombo.count()-1)
            if d == defPowerMeter:
                self.ui.meterCombo.setCurrentIndex(self.ui.meterCombo.count()-1)
         
        ## get scope device to connect objective changed signal
        self.scope = getManager().getDevice(self.dev.config['scope'])
        self.scope.sigObjectiveChanged.connect(self.objectiveChanged)
        
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
        self.ui.wavelengthSpin.valueChanged.connect(self.wavelengthSpinChanged)
        self.ui.wavelengthCombo.currentIndexChanged.connect(self.wavelengthComboChanged)
        #self.ui.microscopeCombo.currentIndexChanged.connect(self.microscopeChanged)
        self.ui.meterCombo.currentIndexChanged.connect(self.powerMeterChanged)
        self.ui.channelCombo.currentIndexChanged.connect(self.channelChanged)
        #self.ui.measurementSpin.valueChanged.connect(self.measurmentSpinChanged)
        #self.ui.settlingSpin.valueChanged.connect(self.settlingSpinChanged)
        self.ui.shutterBtn.toggled.connect(self.shutterToggled)
        self.ui.qSwitchBtn.toggled.connect(self.qSwitchToggled)
        self.ui.checkPowerBtn.clicked.connect(self.dev.outputPower)
        self.ui.powerAlertCheck.toggled.connect(self.powerAlertToggled)
        
        self.dev.sigPowerChanged.connect(self.updatePowerLabels)
        
        self.dev.outputPower()  ## check laser power
        
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
            
    def shutterToggled(self, b):
        if b:
            self.dev.openShutter()
            self.ui.shutterBtn.setText('Close Shutter')
        elif not b:
            self.dev.closeShutter()
            self.ui.shutterBtn.setText('Open Shutter')
            
    def qSwitchToggled(self, b):
        if b:
            self.dev.openQSwitch()
            self.ui.qSwitchBtn.setText('Turn Off QSwitch')
        elif not b:
            self.dev.closeQSwitch()
            self.ui.qSwitchBtn.setText('Turn On QSwitch')
            
    
    def expectedPowerSpinChanged(self, value):
        self.dev.setParam(expectedPower=value)
        #self.dev.expectedPower = value
        self.dev.appendPowerHistory(value)
    
    def toleranceSpinChanged(self, value):
        self.dev.setParam(tolerance=value)
    
    def wavelengthSpinChanged(self, value):
        self.dev.setWavelength(value)
        if value not in self.dev.config.get('namedWavelengths', {}).keys():
            self.ui.wavelengthCombo.setCurrentIndex(0)
    
    def wavelengthComboChanged(self):
        if self.ui.wavelengthCombo.currentIndex() == 0:
            return
        text = str(self.ui.wavelengthCombo.currentText())
        wl = self.dev.config.get('namedWavelengths', {}).get(text, None)
        if wl is not None:
            self.ui.wavelengthSpin.setValue(wl)
    
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
            
    
    #def measurementSpinChanged(self, value):
        #pass
    
    #def settlingSpinChanged(self, value):
        #pass
        
    def objectiveChanged(self):
        ## look up transmission value for this objective in calibration list
        index = self.dev.getCalibrationIndex()
        obj = self.scope.getObjective()['name'] 
        vals = index[self.scope.name].get(obj, None)
        if vals is None:
            raise Exception("No laser calibration for %s objective on %s." %(obj, self.scope.name))
        wl = str(siFormat(self.dev.getWavelength()))
        vals = vals.get(wl, None)
        if vals is None:
            raise Exception("No laser calibration for %s wavelenth with %s objective on %s." %(wl, obj, self.scope.name))
        
        ## set that transmisson value in dev.params
        self.dev.setParam(scopeTransmission=vals['transmission'])
        
        ## update labels
        with self.dev.variableLock:
            power = self.dev.getParam('currentPower')
        self.updatePowerLabels(power, self.dev.checkPowerValidity(power))
    
    def updatePowerLabels(self, power, valid):
        #if power is None:
            #self.ui.outputPowerLabel.setText("")
            #self.ui.samplePowerLabel.setText("")
        #else:
        #print 'power:', power*self.dev.getParam('scopeTransmission'), str(siFormat(power*self.dev.getParam('scopeTransmission'), suffix='W'))
        self.ui.outputPowerLabel.setText(siFormat(power, suffix='W'))
        self.ui.samplePowerLabel.setText(siFormat(power*self.dev.getParam('scopeTransmission'), suffix='W'))
        if not valid:
            print "power invalid"
            self.ui.outputPowerLabel.setStyleSheet("QLabel {color: #B00}")
        else:
            self.ui.outputPowerLabel.setStyleSheet("QLabel {color: #000}")


    def updateCalibrationList(self):
        self.ui.calibrationList.clear()
        ## Populate calibration lists
        index = self.dev.getCalibrationIndex()
        if index.has_key('pCellCalibration'):
            index.pop('pCellCalibration')
        for scope in index:
            #self.microscopes.append(scope)
            for obj in index[scope]:
                for wavelength in index[scope][obj]:
                    cal = index[scope][obj][wavelength]
                    power = cal['power']
                    trans = cal['transmission']
                    date = cal['date']
                    item = QtGui.QTreeWidgetItem([scope, obj, wavelength, '%.2f' %(trans*100) + '%', siFormat(power, suffix='W'), date])
                    self.ui.calibrationList.addTopLevelItem(item)
        ## set current scopeTransmission
        trans = index.get(self.scope.name, {}).get(self.scope.getObjective()['name'], {}).get(str(siFormat(self.dev.getWavelength())), {}).get('transmission', None)
        if trans is not None:
            self.dev.setParam(scopeTransmission=trans)
            
    def calibrateClicked(self):
        ## Delete button must be clicked twice.
        if self.calibrateBtnState == 0 and self.calibrateWarning is not None:
            self.ui.calibrateBtn.setText(self.calibrateWarning)
            self.calibrateBtnState = 1
        elif self.calibrateBtnState == 1 or self.calibrateWarning is None:
            self.ui.calibrateBtn.setEnabled(False)
            try:
                self.ui.calibrateBtn.setText('Calibrating...')
                self.calibrate()
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
    
    def calibrate(self):
        scope = str(self.ui.microscopeCombo.currentText())
        #meter = str(self.ui.meterCombo.currentText())
        obj = getManager().getDevice(scope).getObjective()['name']
        wavelength = str(siFormat(self.dev.getWavelength()))
        date = time.strftime('%Y.%m.%d %H:%M', time.localtime())
        index = self.dev.getCalibrationIndex()
        powerMeter = str(self.ui.meterCombo.currentText())
        mTime = self.ui.measurementSpin.value()
        sTime = self.ui.settlingSpin.value()
        
        ## Run calibration
        if not self.dev.hasPCell:
            power, transmission = self.dev.runCalibration(powerMeter=powerMeter, measureTime=mTime, settleTime=sTime)
            self.dev.setParam(currentPower=power, scopeTransmission=transmission)
        else:
            raise Exception("Pockel Cell calibration is not yet implented.")
            #if index.has_key('pCellCalibration') and not self.ui.recalibratePCellCheck.isChecked():
                #power, transmission = self.runCalibration() ## need to tell it to run with open pCell
            #else:
                #minVal = self.ui.minVSpin.value()
                #maxVal = self.ui.maxVSpin.value()
                #steps = self.ui.stepsSpin.value()
                #power = []
                #arr = np.zeros(steps, dtype=[('voltage', float), ('trans', float)])
                #for i,v in enumerate(np.linspace(minVal, maxVal, steps)):
                    #p, t = self.runCalibration(pCellVoltage=v) ### returns power at sample(or where powermeter was), and transmission through whole system
                    #power.append(p)
                    #arr[i]['trans']= t
                    #arr[i]['voltage']= v
                #power = (min(power), max(power))
                #transmission = (arr['trans'].min(), arr['trans'].min())
                #arr['trans'] = arr['trans']/arr['trans'].max()
                #minV = arr['voltage'][arr['trans']==arr['trans'].min()]
                #maxV = arr['voltage'][arr['trans']==arr['trans'].max()]
                #if minV < maxV:
                    #self.dev.pCellCurve = arr[arr['voltage']>minV * arr['voltage']<maxV]
                #else:
                    #self.dev.pCellCurve = arr[arr['voltage']<minV * arr['voltage']>maxV]
                    
                #index['pCellCalibration'] = {'voltage': list(self.dev.pCellCurve['voltage']), 
                                             #'trans': list(self.dev.pCellCurve['trans'])}
                
            
              
        if scope not in index:
            index[scope] = {}
        if obj not in index[scope]:
            index[scope][obj] = {}
        index[scope][obj][wavelength] = {'power': power, 'transmission':transmission, 'date': date}

        self.dev.writeCalibrationIndex(index)
        self.updateCalibrationList()
    
    def deleteClicked(self):
        #self.dev.outputPower()
        cur = self.ui.calibrationList.currentItem()
        if cur is None:
            return
        scope = str(cur.text(0))
        obj = str(cur.text(1))
        
        index = self.dev.getCalibrationIndex()
        
        del index[scope][obj]

        self.dev.writeCalibrationIndex(index)
        self.updateCalibrationList()
    

            
        
       
        