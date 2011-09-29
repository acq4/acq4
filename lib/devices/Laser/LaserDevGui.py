from PyQt4 import QtGui, QtCore
from lib.Manager import getManager, logExc, logMsg
from devTemplate import Ui_Form
import numpy as np



class LaserDevGui(QtGui.QWidget):
    
    def __init__(self, dev):
        QtGui.QWidget.__init__(self)
        self.dev = dev
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
        self.ui.durationSpin.setOpts(suffix='s', siPrefix=True, bounds=[0.0, 3.0])
        self.ui.settlingSpin.setOpts(suffix='s', siPrefix=True, value=0.1)
        self.ui.expectedPowerSpin.setOpts(suffix='W', siPrefix=True, bounds=[0.0, None], value=self.dev.expectedPower)
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
        
    def currentPowerToggled(self, b):
        print b
        pass
    
    def expectedPowerToggled(self, b):
        pass
    
    def expectedPowerSpinChanged(self, value):
        self.dev.expectedPower = value
        self.dev.appendPowerHistory(value)
    
    def toleranceSpinChanged(self, value):
        pass
    
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
    
    

    def updateCalibrationList(self):
        self.ui.calibrationList.clear()
        
        ## Populate calibration lists
        index = self.dev.getCalibrationIndex()
        for scope in index:
            for obj in index[scope]:
                cal = index[scope][obj]
                power = cal['power']
                date = cal['date']
                item = QtGui.QTreeWidgetItem([scope, obj, str(power), date])
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
        cur = self.ui.calibrationList.currentItem()
        scope = str(cur.text(0))
        obj = str(cur.text(1))
        
        index = self.dev.getCalibrationIndex()
        
        del index[scope][obj]

        self.dev.writeCalibrationIndex(index)
        self.updateCalibrationList()
    
    def runCalibration(self):
        
        powerMeter = self.dev.manager.getDevice(self.ui.meterCombo.text())
        daqName = self.dev.config[self.dev.config.keys()[0]]['channel'][0]
        
        power = None
        scale = None
        ## disable QSwitch for whole process
       
        duration = self.ui.durationSpin.value()
        rate = 10000
        nPts = int(rate * duration)
        
        shutterCmd = np.zeros(nPts, dtype=np.byte)
        shutterCmd[nPts/10:] = 1 ## have the first 10% of the trace be a baseline so that we can check to make sure laser was detected
        shutterCmd[-1] = 0 ## close shutter when done
   
        if self.hasPowerIndicator:
            powerInd = self.dev.config['powerIndicator']['channel']
            cmd = {
                'protocol': {'duration': duration, 'timeout': duration+5.0},
                powerInd[0]: {powerInd[1]: {'record':True, 'recordInit':False}},
                self.dev.name: {'shutterWaveform': shutterCmd}, ## laser
                powerMeter: {x: {'record':True, 'recordInit':False} for x in getManager().getDevice(powerMeter).config.keys()},
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
            
            scale = (result['NewportMeter'][0]/result['Photodiode'][0])[nPts/10+0.01/rate:-1].mean()
           
            pass
            
            ## determine relationship between powerIndicator measurement and power under objective
            
           
            
        else:
            
            ## record signal on powerMeter with laser on for some duration
            ## determine power under objective
            
            pass
        
        if power == None or scale == None:
            raise Exception("Was not able to calibrate laser power.")
        else:
            return (power, scale)
        