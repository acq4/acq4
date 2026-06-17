import time
from collections import OrderedDict

import pyqtgraph as pg
from acq4.devices.Device import TaskGui, Device, DeviceTask
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.util import Qt
from acq4.util.gentle import ManualGuiTask, Stopped
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread

Ui_Form = Qt.importTemplate('.FilterWheelTaskTemplate')


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
    
    sigFilterChanged = Qt.Signal(object, object)  # self, Filter
    sigFilterWheelSpeedChanged = Qt.Signal(object, object)  # self, speed
    
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        
        self.lock = Mutex(Qt.QMutex.Recursive)
        
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
                filtname = slot.get('device')
                filt = None if filtname is None else dm.getDevice(filtname)
                self._filters[k] = filt
                self._slotNames[k] = slot.get('name', filtname)
                if filt is not None:
                    devports = filt.ports()
                    if ports is None:
                        ports = devports
                    elif set(ports) != set(devports):
                        raise Exception(f"{filt!r} does not have the expected ports ({devports!r} vs {ports!r})")
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
        """Return a dict of available {slot_n: filter} pairs.
        """
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
            if position is None:
                return None
        return self._filters[position]

    def getPositionCount(self):
        """Return the number of filter positions.

        The number returned indicates all available positions, regardless of
        the presence or absence of a filter in each position.

        By default this returns the largest configured slot number, but 
        subclasses may override this method.
        """
        return max(map(int, self.config['slots'].keys())) + 1
    
    def setPosition(self, pos):
        """Set the filter wheel position and return a FilterWheelFuture instance
        that can be used to wait for the move to complete.
        """
        with self.lock:
            fut = self._lastFuture
            if fut is not None and not fut.is_done:
                fut.stop("Filter change was cancelled")
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

    def loadPreset(self, name):
        """Load a preset filter wheel position by name."""
        idx = next((i for i, n in self._slotNames.items() if n == name), None)
        return self.setPosition(idx)

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

    def _checkMoveFuture(self):
        if self._lastFuture is None:
            return
        self._lastFuture._poll()

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
                fut.stop("Filter wheel stopped")

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


class FilterWheelFuture(ManualGuiTask):
    """Track the progress of a requested filter wheel position change.

    This is an externally-completed ManualGuiTask: it has no body and spawns no
    thread. The device's filter-wheel position monitor (FilterWheelPollThread)
    is the producer; each poll it calls ``_poll()``, which once the wheel stops
    moving resolves the promise if the target was reached or fails it otherwise.
    ``stop()`` aborts an in-progress move; the producer sees ``is_stopped``.
    Subclasses override ``_atTarget()`` to decide when the move has arrived.
    """

    def __init__(self, dev, position):
        ManualGuiTask.__init__(self, name=f"{dev.name()} filter change to {position}")
        self.dev = dev
        self.position = position

    def _atTarget(self):
        return self.dev.getPosition() == self.position

    def _poll(self):
        """Evaluate move progress and complete the promise if it has settled.

        Called by the device's position monitor thread (the producer). While the
        wheel is still moving, or once the promise is already complete, this is a
        no-op. When the wheel stops, the promise is resolved at the target or
        failed if it stopped short.
        """
        if self.is_done or self.is_stopped:
            return
        if self.dev.isMoving():
            return
        if self._atTarget():
            self.resolve(self.position)
        else:
            self.fail(RuntimeError(
                f"Filter wheel did not reach target while moving to {self.position} "
                f"(got to {self.dev.getPosition()})"
            ))


class FilterWheelTask(DeviceTask):
    """Set a filter wheel position before beginning the task.

    Command structure::

        {'filterWheelPosition': N}
    """
    def __init__(self, dev, cmd, parentTask):
        DeviceTask.__init__(self, dev, cmd, parentTask)
        self.dev = dev
        self.cmd = cmd
        self.parentTask = parentTask
        
    def configure(self):
        requiredPos = self.cmd['filterWheelPosition']
        self.future = self.dev.setPosition(requiredPos)
            
    def start(self):
        self.future.wait()
        
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
        
        self.filters = self.dev.slotNames()
        for slotn, name in self.filters.items():
            name = "%d: %s" % (slotn, name)
            self.ui.filterCombo.addItem(name, slotn)
        
        self.ui.sequenceCombo.addItem('off')
        self.ui.sequenceCombo.addItem('list')
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
        if params is None or 'filterWheelPosition' not in params:
            ind = self.ui.filterCombo.currentIndex()
            slotn = self.ui.filterCombo.itemData(ind)
        else:
            slotn = params['filterWheelPosition']
        
        return {'filterWheelPosition': slotn}
    
    def saveState(self, saveItems=False):
        state = self.stateGroup.state()
        return state
    
    def restoreState(self, state):
        self.stateGroup.setState(state)
        self.ui.sequenceListEdit.setVisible(state['sequenceCombo'] != 'off')
        self.sequenceChanged()
        
    def listSequence(self):
        if self.ui.sequenceCombo.currentIndex() == 0:
            return {}

        pos = str(self.ui.sequenceListEdit.text())
        if pos == '':
            return {}
        
        try:
            pos = list(map(int, pos.split(',')))
        except Exception:
            raise ValueError("Filter list must be a comma-separated list of integer positions (got %r)" % pos)

        return {'filterWheelPosition': pos}
        
    def sequenceChanged(self):
        self.sigSequenceChanged.emit(self.dev.name())
        if self.ui.sequenceCombo.currentIndex() == 1:
            self.ui.sequenceListEdit.show()
        else:
            self.ui.sequenceListEdit.hide()
            

class FilterWheelDevGui(Qt.QWidget):
    def __init__(self, dev):
        Qt.QWidget.__init__(self)
        self.dev = dev

        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)

        self.positionBtnLayout = Qt.QGridLayout()
        self.layout.addLayout(self.positionBtnLayout, 0, 0)
        self.positionBtnLayout.setContentsMargins(0, 0, 0, 0)

        self.positionGroup = Qt.QButtonGroup()
        self.positionButtons = []
        cols = 3
        slotNames = self.dev.slotNames()
        for i in range(self.dev.getPositionCount()):
            name = slotNames[i]
            btn = Qt.QPushButton("%d: %s" % (i, name))
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
        Thread.__init__(self, name=f"FilterWheelPollThread_{dev.name()}")
        self.dev = dev
        self.interval = interval
        
    def run(self):
        self.stopThread = False
        while self.stopThread is False:
            try:
                pos = self.dev.getPosition()
                self.dev._checkMoveFuture()
                time.sleep(self.interval)
            except:
                self.dev.logger.exception("Error in Filter Wheel poll thread:")
                time.sleep(1.0)
    
    def stop(self):
        self.stopThread = True
