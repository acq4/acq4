# -*- coding: utf-8 -*-
from PyQt4 import QtTest
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
    """Optical filter wheel device for swapping FilterSet devices.

    The Filter wheel device class adds control and display for a filter wheel that selects between
    many filters or filter sets. Filters must be defined in the configuration prior to the 
    FilterWheel; see FilterSet for more information.
    
    * Maintains list of the filters in the wheel positions with their description
    * Support for selecting a filter wheel position
    * Support for filter wheel implementation during task : specific filter wheel position during one task, different positions as task sequence
    
    Configuration examples:
    
        FilterWheel:
            driver: 'FilterWheel'
            parentDevice: 'Microscope'
            slots:
                # These are the names of FilterSet devices that have been defined elsewhere
                0: "DIC_FilterCube"
                1: "EGFP_FilterCube"
                2: "EYFP_FilterCube"
    """
    
    sigFilterChanged = QtCore.Signal(object, object)  # self, Filter
    sigFilterWheelSpeedChanged = QtCore.Signal(object, object)  # self, speed
    
    def __init__(self, dm, config, name):
        
        Device.__init__(self, dm, config, name)
        
        self.lock = Mutex(QtCore.QMutex.Recursive)
        
        self._filters = OrderedDict()
        self._slotNames = OrderedDict()
        self._slotIndicators = OrderedDict()

        nPos = self.getPositionCount()
        ports = config.get('ports', None)
        for k in range(nPos):  ## Set value for each filter
            slot = config['slots'].get(str(k))
            if slot is None:
                self._filters[k] = None
                self._slotNames[k] = "empty"
                continue

            if isinstance(slot, str):
                # We are only naming this slot; no actual filter device is defined here
                self._filters[k] = None
                self._slotNames[k] = slot
            elif isinstance(slot, dict):
                filtname = slot['device']
                filt = dm.getDevice(filtname)
                self._filters[k] = filt
                self._slotNames[k] = slot.get('name', filt.name())
                devports = filt.ports()
                if ports is None:
                    ports = devports
                elif set(ports) != set(devports):
                    raise Exception("FilterSet %r does not have the expected ports (%r vs %r)" % (filt, devports, ports))
            else:
                raise TypeError("Slot definition must be str or dict; got: %r" % slot)

            if 'hotkey' in slot:
                dev = dm.getDevice(slot['hotkey']['device'])
                key = slot['hotkey']['key']
                dev.addKeyCallback(key, self._hotkeyPressed, (k,))
                self._slotIndicators[k] = (dev, key)
                # todo: connect to key

        config['ports'] = ports

        OptomechDevice.__init__(self, dm, config, name)

        self._lastFuture = None
        self._lastPosition = None

        # polling thread just checks position regularly; this causes sigFilterChanged to be emitted
        # whenever a change is detected
        pollInterval = config.get('pollInterval', 0.1)
        if pollInterval is not None:
            self.fwThread = FilterWheelPollThread(self, interval=pollInterval)
            self.fwThread.start()

        dm.sigAbortAll.connect(self.stop)

        if 'initialSlot' in config:
            self.setPosition(config['initialSlot'])

    def listFilters(self):
        """Return a dict of available filters.
        """
        with self.filterWheelLock:
            return self._filters.copy()
    
    def slotNames(self):
        """Return a dict of names for each slot in the wheel.
        """
        return self._slotNames.copy()

    def getFilter(self, position=None):
        """Return the Filter at *position*. 
        
        If *position* is None, then return the currently active Filter."""
        if position is None:
            position = self.getPosition()
        return self._filters[position]

    def getPositionCount(self):
        """Return the number of filter positions.

        The number returned indicates all available positions, regardless of
        the presence or absence of a filter in each position.
        """
        raise NotImplementedError("Method must be implemented in subclass")
    
    def setPosition(self, pos):
        """Set the filter wheel position and return a FilterWheelFuture instance
        that can be used to wait for the move to complete.
        """
        with self.lock:
            fut = self._lastFuture
            if fut is not None and not fut.isDone():
                fut.cancel()
            self._lastFuture = self._setPosition(pos)
            return self._lastFuture

    def _setPosition(self, pos):
        """Must be implemented in subclass to request device movement and
        return a FilterWheelFuture.

        Example::

            def _setPosition(self, pos):
                self.device.setPosition(pos)  # actually ask device to move
                return FilterWheelFuture(self, pos)
        """
        raise NotImplementedError("Method must be implemented in subclass")

    def _hotkeyPressed(self, dev, changes, pos):
        self.setPosition(pos)

    def getPosition(self):
        """Return the current position of the filter wheel.
        """
        pos = self._getPosition()
        if pos != self._lastPosition:
            self._lastPosition = pos
            self._positionChanged(pos)
        return pos

    def _getPosition(self):
        raise NotImplementedError("Method must be implemented in subclass")

    def _positionChanged(self, pos):
        filt = self.getFilter(pos)
        self.setCurrentSubdevice(filt)
        self.sigFilterChanged.emit(self, filt)
        for k,indicator in self._slotIndicators.items():
            dev, key = indicator
            if k == pos:
                dev.setBacklight(key, blue=1, red=1)
            else:
                dev.setBacklight(key, blue=0, red=0)

    def isMoving(self):
        """Return the current position of the filter wheel.
        """
        raise NotImplementedError("Method must be implemented in subclass")
        
    def stop(self):
        """Immediately stop the filter wheel.
        """
        self._stop()
        with self.lock:
            fut = self._lastFuture
            if fut is not None:
                fut.cancel()

    def _stop(self):
        raise NotImplementedError("Method must be implemented in subclass")

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


class FilterWheelFuture(object):
    def __init__(self, dev, position):
        self.dev = dev
        self.position = position
        self._wasInterrupted = False
        self._done = False
        self._error = None

    def wasInterrupted(self):
        """Return True if the move was interrupted before completing.
        """
        return self._wasInterrupted

    def cancel(self):
        if self.isDone():
            return
        self._wasInterrupted = True
        self._error = "Filter change was cancelled"

    def _atTarget(self):
        return self.dev.getPosition() == self.position
    
    def isDone(self):
        """Return True if the move has completed or was interrupted.
        """
        if self._wasInterrupted or self._done:
            return True
        if self.dev.isMoving():
            return False

        if self._atTarget():
            self._done = True
            return True
        else:
            self._wasInterrupted = True
            self._error = "Filter wheel did not reach target"
            return True

    def errorMessage(self):
        """Return a string description of the reason for a move failure,
        or None if there was no failure (or if the reason is unknown).
        """
        return self._error
        
    def wait(self, timeout=None, updates=False):
        """Block until the move has completed, has been interrupted, or the
        specified timeout has elapsed.

        If *updates* is True, process Qt events while waiting.

        If the move did not complete, raise an exception.
        """
        start = ptime.time()
        while (timeout is None) or (ptime.time() < start + timeout):
            if self.isDone():
                break
            if updates is True:
                QtTest.QTest.qWait(100)
            else:
                time.sleep(0.1)
        
        if not self.isDone():
            err = self.errorMessage()
            if err is None:
                raise RuntimeError("Timeout waiting for filter wheel change")
            else:
                raise RuntimeError("Move did not complete: %s" % err)


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
            

class FilterWheelDevGui(QtGui.QWidget):
    def __init__(self, dev):
        QtGui.QWidget.__init__(self)
        self.dev = dev

        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)

        self.positionBtnLayout = QtGui.QGridLayout()
        self.layout.addLayout(self.positionBtnLayout, 0, 0)
        self.positionBtnLayout.setContentsMargins(0, 0, 0, 0)

        self.positionGroup = QtGui.QButtonGroup()
        self.positionButtons = []
        cols = 3
        slotNames = self.dev.slotNames()
        for i in range(self.dev.getPositionCount()):
            name = slotNames[i]
            btn = QtGui.QPushButton("%d: %s" % (i, name))
            btn.setCheckable(True)
            btn.filterPosition = i
            self.positionButtons.append(btn)
            self.positionGroup.addButton(btn, i)
            self.positionBtnLayout.addWidget(btn, i // cols, i % cols)
            btn.clicked.connect(self.positionButtonClicked)
        self.positionGroup.setExclusive(True)
        
        self.positionChanged()

        self.dev.sigFilterChanged.connect(self.positionChanged)

    def positionChanged(self):
        pos = self.dev.getPosition()
        if pos is None:
            for btn in self.positionButtons:
                btn.setChecked(False)
        else:
            self.positionButtons[pos].setChecked(True)

    def positionButtonClicked(self):
        self.positionChanged()  # reset button until the filter wheel catches up
        btn = self.sender()
        self.dev.setPosition(btn.filterPosition)


class FilterWheelPollThread(Thread):
    def __init__(self, dev, interval=0.1):
        Thread.__init__(self)
        self.dev = dev
        self.interval = interval
        
    def run(self):
        self.stopThread = False
        while self.stopThread is False:
            try:
                pos = self.dev.getPosition()
                time.sleep(self.interval)
            except:
                debug.printExc("Error in Filter Wheel poll thread:")
                time.sleep(1.0)
    
    def stop(self):
        self.stopThread = True
