# -*- coding: utf-8 -*-
from acq4.devices.OptomechDevice import *
from acq4.drivers.ThorlabsFW102C import *
from acq4.devices.FilterWheel.FilterWheelDevGui import FilterWheelDevGui
from acq4.devices.FilterWheel.FilterWheelTaskTemplate import Ui_Form
from acq4.devices.Microscope import Microscope
from acq4.devices.Device import *
from acq4.devices.Device import TaskGui
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
import acq4.util.debug as debug
import time

class FilterWheel(Device, OptomechDevice):

    sigFilterWheelPositionChanged = QtCore.Signal(object)
    sigFilterWheelSpeedChanged = QtCore.Signal(object)
    sigFilterWheelTrigModeChanged = QtCore.Signal(object)
    
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
                
        self.port = config['port']-1  ## windows com ports start at COM1, pyserial ports start at 0
        self.baud = config.get('baud', 115200)
        #self.positionLabels = config.get('postionLabels')
        
        
        self.driver = filterWheelDriver(self.port, self.baud)
        self.driverLock = Mutex(QtCore.QMutex.Recursive)  ## access to low level driver calls
        self.filterWheelLock = Mutex(QtCore.QMutex.Recursive)  ## access to self.attributes
        
        
        self.filters = collections.OrderedDict()
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
            self.currentObjective = self.getFilter()
            
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
            self.sigFilterWheelPositionChanged.emit(pos)
            
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
            self.sigFilterWheelPositionChanged.emit(newPos)
        
    def createTask(self, cmd, parentTask):
        with self.filterWheelLock:
            return FilterWheelTask(self, cmd, parentTask)
    
    def taskInterface(self, taskRunner):
        with self.filterWheelLock:
            return FilterWheelTaskGui(self, taskRunner)
        
    def setObjectiveIndex(self, index):
        """Selects the objective currently in position *index*"""
        index = str(index)
        if index not in self.selectedObjectives:
            raise Exception("Requested invalid objective switch position: %s (options are %s)" % (index, ', '.join(self.objectives.keys())))
            
        ## determine new objective, return early if there is no change
        ## NOTE: it is possible in some cases for the objective to have changed even if the index has not.
        lastObj = self.currentObjective
        self.currentSwitchPosition = index
        self.currentObjective = self.getObjective()
        if self.currentObjective == lastObj:
            return
        
        self.setCurrentSubdevice(self.currentObjective)
        #self.updateDeviceTransform()
        self.sigObjectiveChanged.emit((self.currentObjective, lastObj))

    
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
    
    #class SignalProxyObject(QtCore.QObject):
        #sigTransformChanged = QtCore.Signal(object) ## self
    
    def __init__(self, config, fw, key):
        #self.__sigProxy = Objective.SignalProxyObject()
        #self.sigTransformChanged = self.__sigProxy.sigTransformChanged
        #self._config = config
        self._config = config
        self._fw = fw
        self._key = key
        #print config, key
        key = str(key)
        if key in config:
            name = config[key]['name']
            self._description = config[key]['description']
        else:
            name = 'empty'
            self._description = '-'
        
        OptomechDevice.__init__(self, fw.dm, {}, name)
        
        #if 'offset' in config:
        #    self.setOffset(config['offset'])
        #if 'scale' in config:
        #    self.setScale(config['scale'])
            
    def key(self):
        return self._key

    def description(self):
        return self._description
    
    def filterwheel(self):
        return self._fw
    
    def __repr__(self):
        return "<Filter %s.%s>" % (self._fw.name(), self.name())


    
class FilterWheelTask(DeviceTask):
    #pass
    # This is disabled--internal shutter in coherent laser should NOT be used by ACQ4; use a separate shutter.
    #
    def __init__(self, dev, cmd, parentTask):
        DeviceTask.__init__(self, dev, cmd, parentTask)
        self.dev = dev
        self.cmd = cmd
        self.parentTask = parentTask
        #print parentTask
        
    def configure(self):
        """Sets the state of a remote multiclamp to prepare for a program run."""
        #print "mc configure"
        with self.dev.filterWheelLock:
            #self.state = self.dev.getLastState()
            print 'command :', self.cmd
            requiredPos = int(self.cmd['filterWheelPosition'][0])
            if self.dev.currentFWPosition != requiredPos:
                print 'current pos:', self.dev.currentFWPosition
                print 'requir. pos:', requiredPos
                self.dev.setPosition(requiredPos)
            
    def start(self):
        # self.shutterOpened = self.dev.getShutter()
        # if not self.shutterOpened:
        #     self.dev.openShutter()
        #     time.sleep(2.0)  ## opening the shutter causes momentary power drop; give laser time to recover
        #                      ## Note: It is recommended to keep the laser's shutter open rather than
        #                      ## rely on this to open it for you.
        #print state['filterCombo']
        #print 'start filterwheel task'
        #LaserTask.start(self)
        pass
        
    def stop(self, abort):
        pass
        #print 'end filterwheel task'
        #if not self.shutterOpened:
        #    self.dev.closeShutter()
        #LaserTask.stop(self, abort)

    def isDone(self):
        return True
    
class FilterWheelTaskGui(TaskGui):
    
    #sigSequenceChanged = QtCore.Signal(object)  ## defined upstream
    
    def __init__(self, dev, taskRunner):
        
        TaskGui.__init__(self, dev, taskRunner)

        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.dev = dev
        
        filters = self.dev.listFilters()
        for i in range(len(filters)):
            item = self.ui.filterCombo.addItem(('%s-%s')%((i+1),filters[i].name())) 
            
        ## Create state group for saving/restoring state
        self.stateGroup = pg.WidgetGroup([
            (self.ui.filterCombo,),
        ])
        
    def generateTask(self, params=None):
        state = self.stateGroup.state()
        task = {}
        task['recordState'] = True
        task['filterWheelPosition'] = state['filterCombo']
        return task    
    
    def saveState(self, saveItems=False):
        state = self.stateGroup.state()
        return state
    
    def restoreState(self, state):
        self.stateGroup.setState(state)
        
    def storeConfiguration(self):
        state = self.saveState(saveItems=True)
        self.dev.writeConfigFile(state, 'lastConfig')

    def loadConfiguration(self):
        state = self.dev.readConfigFile('lastConfig')
        self.restoreState(state)    
        
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
