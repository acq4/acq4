# -*- coding: utf-8 -*-
from acq4.devices.OptomechDevice import OptomechDevice
from .FilterWheelTaskTemplate import Ui_Form
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


# Changes:
#  signal signatures changed
# Filter is just object, not OptoMech

class FilterWheel(Device, OptomechDevice):
    """Optical filter wheel device

    The Filter wheel device class adds control and display for a filter wheel that selects between
    many filters or filter sets.
    
    * Maintains list of the filters in the wheel positions with their description
    * Support for selecting a filter wheel position
    * Support for filter wheel implementation during task : specific filter wheel position during one task, different positions as task sequence
    * Support to changing filter wheel speed and input/ouput modus 
    
    Configuration examples:
    
    FilterWheel:
        driver: 'FilterWheel'
        parentDevice: 'Microscope'
        ports: ['excitation', 'emission']
        filters: # filters in slots
            0:  # first slot
                name: 'green_and_shortpass'
                description: 'ET535/70m Chroma, FESH0700 ThorL'
                # Wavelength passed by this filter from parent to child
                emissionWavelength: 535*nm
            1:  # second slot 
                name: 'red'
                description: 'ET630/75m-2p Chroma'
                # Wavelength passed by this filter from parent to child
                emissionWavelength: 630*nm
            2: # third slot
                name: 'shortpass'
                description: 'shortpass'

    """
    
    sigFilterChanged = QtCore.Signal(object, object)  # self, Filter
    sigFilterWheelSpeedChanged = QtCore.Signal(object, object)  # self, speed
    
    def __init__(self, dm, config, name):
        
        Device.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)
        
        self.filterWheelLock = Mutex(QtCore.QMutex.Recursive)  ## access to self.attributes
        
        self.filters = OrderedDict()
        ## Format of self.filters is:
        ## { 
        ##    filterWheelPosition1: {filterName: filter},
        ##    filterWheelPosition2: {filterName: filter},
        ## }
        nPos = self.getPositionCount()
        emptyFilter = {'name': 'empty', 'description': 'empty'}
        for k in range(nPos):  ## Set value for each filter
            filt = Filter(config['filters'].get(k, emptyFilter), self, k)
            self.filters[k] = filt
        
        self.currentFilter = self.getFilter()
            
        self.fwThread = FilterWheelThread(self, self.driver, self.driverLock)
        self.fwThread.fwPosChanged.connect(self.positionChanged)
        self.fwThread.start()
        
    def listFilters(self):
        """Return a dict of available filters.
        """
        with self.filterWheelLock:
            return self.filters.copy()
    
    def getFilter(self):
        """Return the currently active Filter."""
        return self.currentFilter
    
    def getPositionCount(self):
        """Return the number of filter positions.

        The number returned indicates all available positions, regardless of
        the presence or absence of a filter in each position.
        """
        raise NotImplementedError("Method must be implemented in subclass")
    
    def setPosition(self, pos):
        raise NotImplementedError("Method must be implemented in subclass")
    
    def getPosition(self):
        """Return the current position of the filter wheel.
        """
        raise NotImplementedError("Method must be implemented in subclass")
        
    def positionChanged(self, newPos):
        """Sublclasses should call this method when the filterwheel position has changed.
        """
        self.currentFilter = self.filters.get(newPos)
        self.sigFilterChanged.emit(self, newPos)
        
    def setSpeed(self, speed):
        raise NotImplementedError("Method must be implemented in subclass")
    
    def getSpeed(self):
        raise NotImplementedError("Method must be implemented in subclass")
        
    def speedChanged(self, speed):
        """Sublclasses should call this method when the filterwheel speed has changed.
        """
        self.sigSpeedChanged.emit(self, speed)
        
    def createTask(self, cmd, parentTask):
        return FilterWheelTask(self, cmd, parentTask)
    
    def taskInterface(self, taskRunner):
        return FilterWheelTaskGui(self, taskRunner)
        
    def deviceInterface(self, win):
        return FilterWheelDevGui(self)


class FilterSet(OptomechDevice):
    """Represents an optical filter or filter set.

    Parameters
    ----------
    fwDevice : 
        Parent device to which this filter belongs
    key :
        Position where this filter can be accessed from its parent
    name : str
        Short name of this filter (eg, for display in a dropdown menu)
    optics : dict
        Description of the optical properties of this filter. Keys
        are the names of ports on the device; typically 'default' for
        single-axis filters, or 'excitation' / 'emission' for dichroic
        or beam split filters.

    Examples:

        # A pair of stacked filters; second filter is closer to the 
        optics = {'default': [
                    {'model': '...', 'passBands': [(530,580)]},  # bandpass
                    {'model': '...', 'passBands': [(None, 560)]},  # shortpass
                 ]}

        # A dichroic filter cube with excitation / emission filters
        optics = {'excitation': [
                    {'model': '...', 'passBands': [(420,480)]},  # bandpass
                    {'model': '... (reflection)', 'passBands': [(None, 500)]},  # dichroic shortpass
                 ],
                 'emission': [
                    {'model': '... (transmission)', 'passBands': [(505, None)]},  # dichroic longpass 
                    {'model': '...', 'passBands': [(530,580)]},  # bandpass
                 ]}

    """
    def __init__(self, fwDevice, key, name, description, **kwds):
        self._fw = fw
        self._key = key
        self._name = name
        self._description = description

    def name(self):
        return self._config.get('name')

    def key(self):
        return self._key

    def description(self):
        return self._config.get('description')
    
    def filterwheel(self):
        return self._fw
    
    def __repr__(self):
        return "<Filter %s.%s %s>" % (self._fw.name(), self.key(), self.name())

    
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
