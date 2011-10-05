from PyQt4 import QtGui, QtCore
from lib.Manager import getManager, logExc, logMsg
from devTemplate import Ui_Form
import numpy as np
from scipy import stats
from functions import siFormat
import time


class LaserDevGui(QtGui.QWidget):
    
    def __init__(self, dev):
        QtGui.QWidget.__init__(self)
        self.dev = dev
        #self.dev.devGui = self  ## make this gui accessible from LaserDevice, so device can change power values. NO, BAD FORM
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        
        ### configure gui
        self.ui.wavelengthSpin.setOpts(suffix='m', siPrefix=True)
        if not self.dev.hasTunableWavelength:
            self.ui.wavelengthGroup.setDisabled(True)
            self.ui.wavelengthSpin.setValue(self.dev.config.get('wavelength', None))
        else:
            self.ui.wavelengthSpin.setValue(self.dev.getWavelength())
            for x in self.dev.config.get('namedWavelengths', {}).keys():
                self.ui.wavelengthCombo.addItem(x)
        if 'pCell' not in self.dev.config:
            self.ui.pCellGroup.hide()
        else:
            self.ui.minVSpin.setOpts(siPrefix=True)
            self.ui.maxVSpin.setOpts(siPrefix=True)
            self.ui.stepsSpin.setOpts(step=1)
            
        self.ui.durationSpin.setOpts(suffix='s', siPrefix=True, bounds=[0.0, 5.0])
        self.ui.settlingSpin.setOpts(suffix='s', siPrefix=True, value=0.1)
        with self.dev.variableLock:
            self.ui.expectedPowerSpin.setOpts(suffix='W', siPrefix=True, bounds=[0.0, None], value=self.dev.params['expectedPower'])
        self.ui.toleranceSpin.setOpts(step=0.1, suffix='%', bounds=[0.1, 100.0], value=5.0)
        
        
        
        
        
        ## Populate device lists
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
         
        ## Populate list of calibrations
        self.updateCalibrationList()

        ## make connections
        self.ui.calibrateBtn.clicked.connect(self.calibrateClicked)
        self.ui.deleteBtn.clicked.connect(self.deleteClicked)
        self.ui.currentPowerRadio.toggled.connect(self.currentPowerToggled)
        self.ui.expectedPowerRadio.toggled.connect(self.expectedPowerToggled)
        self.ui.expectedPowerSpin.valueChanged.connect(self.expectedPowerSpinChanged)
        self.ui.toleranceSpin.valueChanged.connect(self.toleranceSpinChanged)
        self.ui.wavelengthSpin.valueChanged.connect(self.wavelengthSpinChanged)
        self.ui.wavelengthCombo.currentIndexChanged.connect(self.wavelengthComboChanged)
        self.ui.microscopeCombo.currentIndexChanged.connect(self.microscopeChanged)
        self.ui.meterCombo.currentIndexChanged.connect(self.powerMeterChanged)
        self.ui.durationSpin.valueChanged.connect(self.durationSpinChanged)
        self.ui.settlingSpin.valueChanged.connect(self.settlingSpinChanged)
        
        self.dev.sigPowerChanged.connect(self.updatePowerLabels)
        
    def currentPowerToggled(self, b):
        if b:
            self.dev.setParam(useExpectedPower=False)
    
    def expectedPowerToggled(self, b):
        if b:
            self.dev.setParam(useExpectedPower=True)
    
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
    
    def microscopeChanged(self):
        pass
    
    def powerMeterChanged(self):
        pass
    
    def durationSpinChanged(self, value):
        pass
    
    def settlingSpinChanged(self, value):
        pass
    
    def updatePowerLabels(self, power):
        self.ui.outputPowerLabel.setText(str(siFormat(power)))
        self.ui.samplePowerLabel.setText(str(siFormat(power*self.dev.params['scopeTransmission'])))

    def updateCalibrationList(self):
        self.ui.calibrationList.clear()
        
        ## Populate calibration lists
        index = self.dev.getCalibrationIndex()
        for scope in index:
            for obj in index[scope]:
                cal = index[scope][obj]
                power = cal['power']
                scale = cal['scale']
                date = cal['date']
                item = QtGui.QTreeWidgetItem([scope, obj, '%.2f' %(scale*100) + '%', siFormat(power, suffix='W'), date])
                self.ui.calibrationList.addTopLevelItem(item)
    
    def calibrateClicked(self):
        scope = str(self.ui.microscopeCombo.currentText())
        #meter = str(self.ui.meterCombo.currentText())
        obj = getManager().getDevice(scope).getObjective()['name']
        
        ## Run calibration
        power, scale = self.runCalibration()
        
        date = time.strftime('%Y.%m.%d %H:%M', time.localtime())
        
        index = self.dev.getCalibrationIndex()
        
        if scope not in index:
            index[scope] = {}
        index[scope][obj] = {'power': power, 'scale':scale, 'date': date}

        self.dev.writeCalibrationIndex(index)
        self.updateCalibrationList()
    
    def deleteClicked(self):
        self.dev.outputPower()
        cur = self.ui.calibrationList.currentItem()
        if cur is None:
            return
        scope = str(cur.text(0))
        obj = str(cur.text(1))
        
        index = self.dev.getCalibrationIndex()
        
        del index[scope][obj]

        self.dev.writeCalibrationIndex(index)
        self.updateCalibrationList()
    
    def runCalibration(self):
        
        powerMeter = str(self.ui.meterCombo.currentText())
        daqName = self.dev.getDAQName('shutter')
        
        power = None
        scale = None
       
        duration = self.ui.durationSpin.value()
        rate = 10000
        nPts = int(rate * duration)
        
        shutterCmd = np.zeros(nPts, dtype=np.byte)
        shutterCmd[nPts/10:] = 1 ## have the first 10% of the trace be a baseline so that we can check to make sure laser was detected
        shutterCmd[-1] = 0 ## close shutter when done
   
        if self.dev.hasPowerIndicator:
            powerInd = self.dev.config['powerIndicator']['channel']
            cmd = {
                'protocol': {'duration': duration, 'timeout': duration+5.0},
                powerInd[0]: {powerInd[1]: {'record':True, 'recordInit':False}},
                self.dev.name: {'shutterWaveform': shutterCmd}, ## laser
                powerMeter: {x: {'record':True, 'recordInit':False} for x in getManager().getDevice(powerMeter).listChannels()},
                #'CameraTrigger': {'Command': {'preset': 0, 'command': cameraTrigger, 'holding': 0}},
                #self.dev.name: {'xCommand': xCommand, 'yCommand': yCommand}, ## scanner
                daqName: {'numPts': nPts, 'rate': rate}}
            
            ##cmd = {
                ##'protocol': {'duration': 1},
                ##'Laser-UV': {'shutter': {'preset': 0, 'holding': 0, 'command': shutterCmd}},
                ##'Photodiode': {'Photodiode (1kOhm)': {'record':True, 'recordInit':False}},
                ##'NewportMeter': {'Power [100mW max]': {'record':True, 'recordInit':False}},
                ##'DAQ': {'numPts': 10000, 'rate': 10000}
            ##}
            ## record some duration of signal on the laser's powerIndicator and the powerMeter under objective
            task = getManager().createTask(cmd)
            task.execute()
            result = task.getResult()
            
            scale = (result[powerMeter][0]/result[powerInd[0]][0])[nPts/10+0.01/rate:-1].mean()
           
            pass
            
            ## determine relationship between powerIndicator measurement and power under objective
            
           
            
        else:
            cmd = {
                'protocol': {'duration': duration, 'timeout': duration+5.0},
                #powerInd[0]: {powerInd[1]: {'record':True, 'recordInit':False}},
                self.dev.name: {'shutterWaveform': shutterCmd}, ## laser
                powerMeter: {x: {'record':True, 'recordInit':False} for x in getManager().getDevice(powerMeter).config.keys()},
                #'CameraTrigger': {'Command': {'preset': 0, 'command': cameraTrigger, 'holding': 0}},
                #self.dev.name: {'xCommand': xCommand, 'yCommand': yCommand}, ## scanner
                daqName: {'numPts': nPts, 'rate': rate}}
            ## record signal on powerMeter with laser on for some duration
            ## determine power under objective
            task = getManager().createTask(cmd)
            task.execute()
            result = task.getResult()
            
            power = self.dev.outputPower()
            scale = (result[powerMeter][0]/power)[nPts/10+0.01/rate:-1].mean()
            
        laserOff = result[powerMeter][0][:nPts/10]
        laserOn = result[powerMeter][0][nPts/10+0.01/rate:-1]
            
        t, prob = stats.ttest_ind(laserOn, laserOff)
        if prob < 0.01:
            raise Exception("Power meter device %s could not detect laser." %powerMeter)
           
        else:
            return (laserOn.mean(), scale)
        