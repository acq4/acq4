# -*- coding: utf-8 -*-
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.drivers.ThorlabsFW102C import FilterWheelDriver
from acq4.devices.FilterWheel.FilterWheelDevGui import FilterWheelDevGui
from acq4.devices.FilterWheel.FilterWheelTaskTemplate import Ui_Form
from acq4.devices.Microscope import Microscope
from acq4.util.SequenceRunner import SequenceRunner
from acq4.devices.Device import *
from acq4.devices.Device import TaskGui
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
import acq4.util.debug as debug
import acq4.pyqtgraph as pg
import time
from collections import OrderedDict

class FilterWheel(Device, OptomechDevice):
    """ Thorlabs motorized filter wheel (FW102C)
    The Filter wheel device class adds control and display for the filter wheel device status.
    
    * Maintains list of the filters in the six filter-wheel positions with their description
    * Support for selecting a filter wheel position
    * Support for filter wheel implementation during task : specific filter wheel position during one task, different positions as task sequence
    * Support to changing filter wheel speed and input/ouput modus 
    
    Configuration examples:
    
    FilterWheel:
        driver: 'FilterWheel'
        port: COM4                         ## serial port connected to filter-wheel
        baud: 115200
        parentDevice: 'Microscope'
        filters: # filters in slots
            0:  # first slot
                name: 'green_and_shortpass'
                description: 'ET535/70m Chroma, FESH0700 ThorL'
            1:  # second slot 
                name: 'red'
                description: 'ET630/75m-2p Chroma'
            2: # third slot
                name: 'shortpass'
                description: 'shortpass'


    """
    
    sigFilterChanged = QtCore.Signal(object)
    sigFilterWheelSpeedChanged = QtCore.Signal(object)
    sigFilterWheelTrigModeChanged = QtCore.Signal(object)
    sigFilterWheelSensorModeChanged = QtCore.Signal(object)
    
    def __init__(self, dm, config, name):
        
        Device.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)
        
        self.scopeDev = None
        self.currentFilter = None
        p = self
        while p is not None:
            p = p.parentDevice()
            if isinstance(p, Microscope):
                self.scopeDev = p
                
        self.port = config['port']  ## windows com ports start at COM1, pyserial ports start at 0
        self.baud = config.get('baud', 115200)
        #self.positionLabels = config.get('postionLabels')
        
        
        self.driver = FilterWheelDriver(self.port, self.baud)
        self.driverLock = Mutex(QtCore.QMutex.Recursive)  ## access to low level driver calls
        self.filterWheelLock = Mutex(QtCore.QMutex.Recursive)  ## access to self.attributes
        
        
        self.filters = OrderedDict()
        ## Format of self.filters is:
        ## { 
        ##    filterWheelPosition1: {filterName: filter},
        ##    filterWheelPosition2: {filterName: filter},
        ## }
        nPos = self.getPositionCount()
        for k in range(nPos):  ## Set value for each filter
            filt = Filter(config['filters'],self,k)
            self.filters[k] = filt
        
        #print self.filters.values()
        #print self.filters[1].name(), self.filters[1].description()
        #if len(self.positionLabels) != self.getPositionCount():
        #    raise Exception("Number of FilterWheel positions %s must correspond to number of labels!" % self.getPositionCount())
        
        with self.driverLock:
            self.currentFWPosition = self.driver.getPos()
            self.currentFilter = self.getFilter()
            
        self.fwThread = FilterWheelThread(self, self.driver, self.driverLock)
        self.fwThread.fwPosChanged.connect(self.positionChanged)
        self.fwThread.start()
        
    def setTriggerMode(self, trigMode):
        with self.driverLock:
            self.driver.setTriggerMode(trigMode)
            self.sigFilterWheelTrigModeChanged.emit(trigMode)
    
    def getTriggerMode(self):
        with self.driverLock:
            return self.driver.getTriggerMode()
       
    def setSpeed(self, speed):
        with self.driverLock:
            self.driver.setSpeed(speed)
            self.sigFilterWheelSpeedChanged.emit(speed)
    
    def getSpeed(self):
        with self.driverLock:
            return self.driver.getSpeed()
        
    def setPosition(self, pos):
        with self.driverLock:
            self.driver.setPos(pos)
    
    def getSensorMode(self):
        with self.driverLock:
            return self.driver.getSensorMode()
        
    def setSensorMode(self, sensorMode):
        with self.driverLock:
            self.driver.setSensorMode(sensorMode)
            self.sigFilterWheelSensorModeChanged.emit(sensorMode)
    
    def getPosition(self):
        with self.driverLock:
            return self.driver.getPos()
        
    def getPositionCount(self):
        with self.driverLock:
            return self.driver.getPosCount()
    
    def positionChanged(self,newPos):
        with self.filterWheelLock:
            self.currentFWPosition = newPos
            self.currentFilter = self.getFilter()
            self.sigFilterChanged.emit(newPos)
        
    def createTask(self, cmd, parentTask):
        with self.filterWheelLock:
            return FilterWheelTask(self, cmd, parentTask)
    
    def taskInterface(self, taskRunner):
        with self.filterWheelLock:
            return FilterWheelTaskGui(self, taskRunner)
        
    def getFilter(self):
        """Return the currently active Filter."""
        with self.filterWheelLock:
            if (self.currentFWPosition-1) not in self.filters:
                return None
            return self.filters[(self.currentFWPosition-1)]
            #return self.objectives[self.currentSwitchPosition][selected]
    
    def listFilters(self):
        """
        Return a list of available filters.
        """
        with self.filterWheelLock:
            return self.filters.values()
    
    def _allFilters(self):
        ## used by (preferrably only) GUI interface
        return self.filters
    
    
    def deviceInterface(self, win):
        return FilterWheelDevGui(self)


class Filter(OptomechDevice):
    
    def __init__(self, config, fw, key):
        self._config = config
        self._fw = fw
        self._key = key
        #print config, key
        key = str(key)
        if key in config:
            name = '%s-%s' %((int(key)+1), config[key]['name'])
            self._description = config[key]['description']
        else:
            name = '%s-%s' %((int(key)+1), 'empty')
            self._description = '-'
        
        OptomechDevice.__init__(self, fw.dm, {}, name)
        
    def key(self):
        return self._key

    def description(self):
        return self._description
    
    def filterwheel(self):
        return self._fw
    
    def __repr__(self):
        return "<Filter %s.%s>" % (self._fw.name(), self.name())


    
class FilterWheelTask(DeviceTask):

    def __init__(self, dev, cmd, parentTask):
        DeviceTask.__init__(self, dev, cmd, parentTask)
        self.dev = dev
        self.cmd = cmd
        self.parentTask = parentTask
        #print parentTask
        
    def configure(self):

        with self.dev.filterWheelLock:
            #self.state = self.dev.getLastState()
            requiredPos = int(self.cmd['filterWheelPosition'][0]) # take the first character of string and convert it to int
            if self.dev.currentFWPosition != requiredPos:
                self.dev.setPosition(requiredPos)
            
    def start(self):
        pass
        
    def stop(self, abort):
        pass

    def isDone(self):
        return True
    
class FilterWheelTaskGui(TaskGui):
    
    def __init__(self, dev, taskRunner):
        
        TaskGui.__init__(self, dev, taskRunner)

        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.dev = dev
        
        filters = self.dev.listFilters()
        filterList = self.generatFilterList(filters)
        for i in range(len(filterList)):
            item = self.ui.filterCombo.addItem('%s' % filterList[i][1]) 
        
        item = self.ui.sequenceCombo.addItem('off')
        item = self.ui.sequenceCombo.addItem('list')
        self.ui.sequenceListEdit.hide()
        
        self.ui.sequenceCombo.currentIndexChanged.connect(self.sequenceChanged)
        self.ui.sequenceListEdit.editingFinished.connect(self.sequenceChanged)
            
        ## Create state group for saving/restoring state
        self.stateGroup = pg.WidgetGroup([
            (self.ui.filterCombo,),
            (self.ui.sequenceCombo,),
            (self.ui.sequenceListEdit,),
        ])
        
    def generateTask(self, params=None):
        state = self.stateGroup.state()
        
        if params is None or 'filterWheelPosition' not in params:
            target = state['filterCombo']
        else:
            target = self.filterTaskList[params['filterWheelPosition']]
        
        task = {}
        task['recordState'] = True
        task['filterWheelPosition'] = target #state['filterCombo']
        return task    
    
    def saveState(self, saveItems=False):
        state = self.stateGroup.state()
        return state
    
    def restoreState(self, state):
        self.stateGroup.setState(state)
        self.ui.sequenceListEdit.setVisible(state['sequenceCombo'] != 'off')
        self.sequenceChanged()
        
    def storeConfiguration(self):
        state = self.saveState(saveItems=True)
        self.dev.writeConfigFile(state, 'lastConfig')

    def loadConfiguration(self):
        state = self.dev.readConfigFile('lastConfig')
        self.restoreState(state)    
        
    def listSequence(self):
        if self.ui.sequenceCombo.currentIndex() == 1:
            filt = self.getFilterList()
            return OrderedDict([('filterWheelPosition', filt)])
        else:
            return []
        
    def sequenceChanged(self):
        self.filterTaskList = None
        self.sigSequenceChanged.emit(self.dev.name())
        if self.ui.sequenceCombo.currentIndex() == 1:
            self.ui.sequenceListEdit.show()
        else:
            self.ui.sequenceListEdit.hide()
        
    def getFilterList(self):
        self.filterTaskList = []
        pos = self.ui.sequenceListEdit.text()
        if pos == '':
            return self.filterTaskList
        else:
            pos = map( int, pos.split(',') )
            for i in range(len(pos)):
                self.filterTaskList.append(self.filterList[pos[i]-1])
            #print 'filterTaskList :', self.filterTaskList
            return self.filterTaskList
    
    def generatFilterList(self, filt):
        self.filterList = []
        for i in range(len(filt)):
            self.filterList.append([(i+1), filt[i].name()])
        #print 'filterList : ', self.filterList
        return self.filterList
            
    
class FilterWheelThread(Thread):

    fwPosChanged = QtCore.Signal(object)

    def __init__(self, dev, driver, lock):
        Thread.__init__(self)
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.dev = dev
        self.driver = driver
        self.driverLock = lock
        self.cmds = {}

        
    def run(self):
        self.stopThread = False
        with self.driverLock:
            self.fwPosChanged.emit(self.driver.getPos())
        while True:
            try:
                with self.driverLock:
                    pos = self.driver.getPos()
                self.fwPosChanged.emit(pos)
                time.sleep(0.5)
            except:
                debug.printExc("Error in Filter Wheel communication thread:")
                
            self.lock.lock()
            if self.stopThread:
                self.lock.unlock()
                break
            self.lock.unlock()
            time.sleep(0.02)

        self.driver.close()
    
    def stop(self, block=False):
        with self.lock:
            self.stopThread = True
        if block:
            if not self.wait(10000):
                raise Exception("Timed out while waiting for Filter Wheel thread exit!")
