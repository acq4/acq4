from PyQt4 import QtGui, QtCore



class LaserDevGui(QtGui.QWidget):
    
    def __init__(self, dev):
        QtGui.QWidget.__init__(self)
        self.dev = dev
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        
        defMicroscope = self.dev.config.get('defaultMicroscope', None)
        defPowerMeter = self.dev.config.get('defaultPowerMeter', None)
        
        ## Populate device lists
        devs = self.dev.dm.listDevices()
        for d in devs:
            self.ui.microscopeCombo.addItem(d)
            self.ui.meterCombo.addItem(d)
            if d == defMicroscope:
                self.ui.microscopeCombo.setCurrentIndex(self.ui.microscopeCombo.count()-1)
            if d == defLaser:
                self.ui.meterCombo.setCurrentIndex(self.ui.meterCombo.count()-1)
         
        ## Populate list of calibrations
        self.updateCalibrationList()

        self.ui.calibrateBtn.clicked.connect(self.calibrateClicked)
        self.ui.deleteBtn.clicked.connect(self.deleteClicked)

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
        obj = getManager().getDevice(scope).getObjective()[0]
        
        ## Run calibration
        power, scale = self.runCalibration()
        
        date = time.strftime('%Y.%m.%d %H:%M', time.localtime())
        
        index = self.dev.getCalibrationIndex()
        
        if scope not in index:
            index[scope] = {}
        index[scope][obj] = {'power': power, 'scale':scale 'date': date}

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
        power = None
        scale = None
        ## disable QSwitch for whole process
        gotOffset = False
        ## compare laser's power indicator to the powermeter being used for calibration (if laser has powerIndicator)
        if self.hasPowerIndicator:
            pass
            ## ask user to put power meter at output of laser
            ## record some duration of signal on the laser's powerIndicator and the powerMeter 
            ## determine relationship between meter measurements of the same signal
            
            gotOffset=True
            
        if gotOffset or not self.hasPowerIndicator:
            
            ## ask user to put power meter under objective
            ## record signal on powerIndicator (if laser has one) and powerMeter
            ## determine power under objective
            ## determine linear relationship between power measured by laser's power indicator and power under objective
            pass
        
        if power == None or scale == None:
            raise Exception("Was not able to calibrate laser power.")
        else:
            return (power, scale)
        