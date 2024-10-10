import collections

import numpy as np

import pyqtgraph as pg
from acq4.Manager import getManager
from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.devices.Stage import Stage
from acq4.modules.Camera import CameraModuleInterface
from acq4.util import Qt
from acq4.util.Mutex import Mutex
from acq4.util.debug import printExc
from acq4.util.future import Future, MultiFuture, future_wrap
from acq4.util.imaging import Frame
from acq4.util.surface import find_surface
from acq4.util.typing import Number
from pyqtgraph.units import µm

Ui_Form = Qt.importTemplate('.deviceTemplate')


class Microscope(Device, OptomechDevice):
    """
    The Microscope device class has several purposes:

    * Acts as a parent for imaging and photostimulation devices
    * Account for differences in magnification, focal plane, and xy offset between objectives
        * Maintains list of objective slots (most scopes have 2-5 slots)
        * For each slot, maintains a list of possible objectives that may be found there
          (this allows the experimenter to change the objective at a certain slot
          during the experiment)
        * Support for automatically selecting the correct objective position based on a Switch device
        * Each objective has an offset and scale factor associated with it. This transformation is communicated
          automatically to all rigidly-connected child devices.
    * Manage multiple parent stage devices (such as independent focus / xy stages)
    * Manage attached light + filter devices
    * Track the focus depth of sample surface
    """

    sigObjectiveChanged = Qt.Signal(object)  ## (objective, lastObjective)
    sigLightChanged = Qt.Signal(object, object)  # self, lightName
    sigObjectiveListChanged = Qt.Signal()
    sigSurfaceDepthChanged = Qt.Signal(object)

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)

        self.config = config
        self.presets = config.get('presets', {})
        self.lock = Mutex(Qt.QMutex.Recursive)
        self.switchDevice = None
        self.currentSwitchPosition = None
        self.currentObjective = None
        self._focusDevice = None
        self._positionDevice = None
        self._surfaceDepth = None

        self.objectives = collections.OrderedDict()
        ## Format of self.objectives is:
        ## { 
        ##    switchPosition1: {objName1: objective1, objName2: objective, ...},
        ##    switchPosition2: {objName1: objective1, objName2: objective, ...},
        ## }

        for slot_name, objs in config['objectives'].items():  ## Set default values for each objective
            self.objectives[slot_name] = collections.OrderedDict()
            for obj_name, o in objs.items():
                obj = Objective(o, self, (slot_name, obj_name))
                self.objectives[slot_name][obj_name] = obj
                # obj.sigTransformChanged.connect(self.objectiveTransformChanged)

        ## Keep track of the objective currently in use for each position
        ## Format is: { switchPosition1: objective1,  ... }
        self.selectedObjectives = collections.OrderedDict(
            [(i, list(self.objectives[i].values())[0]) for i in self.objectives]
        )
        for obj in self.selectedObjectives.values():
            self.addSubdevice(obj)

        ## if there is a light source, configure it here
        if 'lightSource' in config:
            self.lightSource = dm.getDevice(config['lightSource'])
            self.lightSource.sigLightChanged.connect(self._lightChanged)
        else:
            self.lightSource = None

        ## If there is a switch device, configure it here
        if 'objectiveSwitch' in config:
            self.switchDevice = dm.getDevice(config['objectiveSwitch'][0])  ## Switch device
            self.objSwitchId = config['objectiveSwitch'][1]  ## Switch ID
            self.switchDevice.sigSwitchChanged.connect(self.objectiveSwitchChanged)
            try:
                self.objectiveSwitchChanged()
            except:
                printExc("Could not set initial objective state:")
        else:
            self.switchDevice = None
            firstObj = next(iter(self.objectives))
            self.objectiveIndexChanged(firstObj)

        cal = self.readConfigFile('calibration')
        if 'surfaceDepth' in cal:
            self.setSurfaceDepth(cal['surfaceDepth'])

        dm.declareInterface(name, ['microscope'], self)

    def quit(self):
        pass

    def objectiveSwitchChanged(self, sw=None, change=None):
        ## Called when the switch device has changed, NOT when the user has selected a different objective.
        ## *change* looks like { switchId1: newValue, switchId2: newValue, ... }
        if sw is None:
            change = {self.objSwitchId: self.switchDevice.getSwitch(self.objSwitchId)}

        if self.objSwitchId not in change:  ## the switch(es) that changed are not relevant to this device
            return
        state = str(change[self.objSwitchId])
        self.objectiveIndexChanged(state)

    def setObjectiveIndex(self, index):
        """Selects the objective currently in position *index*
        
        This method is called when the user selects an objective index from the manager UI."""
        if self.switchDevice is not None and hasattr(self.switchDevice, 'setSwitch'):
            self.switchDevice.setSwitch(self.objSwitchId, int(index))
        else:
            self.objectiveIndexChanged(index)

    def objectiveIndexChanged(self, index):
        # called when the objective index has changed.
        index = str(index)
        if index not in self.selectedObjectives:
            raise ValueError(
                f"Requested invalid objective switch position: {index} (options are {', '.join(list(self.objectives.keys()))})"
            )

        ## determine new objective, return early if there is no change
        ## NOTE: it is possible in some cases for the objective to have changed even if the index has not.
        with self.lock:
            lastObj = self.currentObjective
            self.currentSwitchPosition = index
            self.currentObjective = self.getObjective()
            if self.currentObjective == lastObj:
                return

        self.setCurrentSubdevice(self.currentObjective)
        self.sigObjectiveChanged.emit((self.currentObjective, lastObj))
        self.sigGeometryChanged.emit(self)

    def getObjective(self) -> "Objective":
        """Return the currently active Objective."""
        with self.lock:
            if self.currentSwitchPosition not in self.selectedObjectives:
                return None
            return self.selectedObjectives[self.currentSwitchPosition]

    def listObjectives(self):
        """
        Return a list of available objectives. (one objective returned per switch position)
        """
        with self.lock:
            return list(self.selectedObjectives.values())

    def loadPreset(self, name):
        conf = self.presets[name]
        for dev_name, state in conf.items():
            if dev_name == "objective":
                self.setObjectiveIndex(state)
            elif dev_name != "hotkey":
                dev = self.dm.getDevice(dev_name)
                if hasattr(dev, "loadPreset"):
                    dev.loadPreset(state)

    def handlePresetHotkey(self, kb_dev, changes, name):
        key, pressed = changes.get('keys', [])[0]
        if pressed:
            self.loadPreset(name)

    def deviceInterface(self, win):
        iface = ScopeGUI(self, win)
        iface.objectiveChanged((self.currentObjective, None))
        return iface

    def physicalTransform(self, subdev=None):
        return self.parentDevice().deviceTransform(subdev)

    def getGeometries(self):
        if (obj := self.getObjective()) is None:
            return []
        return obj.getRealGeometries()

    def selectObjective(self, obj):
        ##Set the currently-active objective for a particular switch position
        ##This is _not_ the same as objectiveIndexChanged.
        index = obj.key()[0]
        with self.lock:
            self.removeSubdevice(self.selectedObjectives[index])
            self.selectedObjectives[index] = obj
            self.addSubdevice(obj)
        self.objectiveIndexChanged(self.currentSwitchPosition)  # update self.currentObjective, send signals (if needed)
        self.sigObjectiveListChanged.emit()

    def _allObjectives(self):
        ## used by (preferrably only) GUI interface
        return self.objectives

    def _lightChanged(self, light, name):
        self.sigLightChanged.emit(self, name)

    def cameraModuleInterface(self, mod):
        """Return an object to interact with camera module.
        """
        return ScopeCameraModInterface(self, mod)

    def getFocusDepth(self):
        """Return the z-position of the focal plane.

        This method requires a device that provides focus position feedback.
        """
        return self.mapToGlobal(Qt.QVector3D(0, 0, 0)).z()

    def setFocusDepth(self, z, speed='fast'):
        """Set the z-position of the focal plane.

        This method requires motorized focus control.
        """
        # this is how much the focal plane needs to move (in the global frame)
        dif = z - self.getFocusDepth()

        # this is the current global location of the focus device 
        fd = self.focusDevice()
        fdpos = fd.globalPosition()

        # and this is where it needs to go
        fdpos[2] += dif
        return fd.moveToGlobal(fdpos, speed)

    def getDefaultImager(self):
        name = self.config.get('defaultImager', None)
        if name is None:
            cameras = self.dm.listInterfaces("camera")
            if len(cameras) == 0:
                raise RuntimeError("No camera devices available.")
            name = cameras[0]
        return self.dm.getDevice(name)

    def getZStack(self, imager: "Device", z_range, block=False) -> Future[list[Frame]]:
        """Acquire a z-stack of images using the given imager.

        The z-stack is returned as frames.
        """
        from acq4.util.imaging.sequencer import acquire_z_stack

        return acquire_z_stack(imager, *z_range, block=block)

    @future_wrap
    def findSurfaceDepth(self, imager: "Device", searchDistance=200*µm, searchStep=5*µm, _future: Future = None) -> float:
        """Set the surface of the sample based on how focused the images are."""
        z_range = (self.getSurfaceDepth() + searchDistance, self.getSurfaceDepth() - searchDistance, searchStep)
        z_stack: list[Frame] = self.getZStack(imager, z_range, block=True).getResult()
        threshold = self.config.get('surfaceDetectionPercentileThreshold', 96)
        if (idx := find_surface(z_stack, threshold)) is not None:
            depth = z_stack[idx].mapFromFrameToGlobal([0, 0, 0])[2]
            self.setSurfaceDepth(depth)
            _future.waitFor(self.setFocusDepth(depth))
            return depth
        else:
            raise ValueError("Could not find surface")

    def getSurfaceDepth(self) -> Number:
        """Return the z-position of the sample surface as marked by the user.
        """
        return self._surfaceDepth

    def setSurfaceDepth(self, depth):
        self._surfaceDepth = depth
        self.sigSurfaceDepthChanged.emit(depth)
        self.writeCalibration()

    def globalPosition(self):
        """Return the global position of the scope's center axis at the focal plane.
        """
        return self.mapToGlobal(pg.Vector(0, 0, 0))

    def setGlobalPosition(self, pos, speed='fast'):
        """Move the microscope such that its center axis is at a specified global position.

        If *pos* is a 3-element vector, then this method will also attempt to set the focus depth
        accordingly.

        Return a MoveFuture instance.
        """
        pos = np.asarray(pos)
        positionDevice = self.positionDevice()
        focusDevice = self.focusDevice()

        if len(pos) == 3 and focusDevice is not positionDevice:
            z = pos[2]
            zFuture = self.setFocusDepth(z)
            pos = pos[:2]
        else:
            zFuture = None

        if len(pos) == 2:
            pos = list(pos) + [self.getFocusDepth()]

        # Determine how to move the xy(z) stage to react the new center position
        gpos = self.globalPosition()
        sgpos = positionDevice.globalPosition()
        sgpos2 = pg.Vector(sgpos) + (pg.Vector(pos) - gpos)
        sgpos2 = [sgpos2.x(), sgpos2.y(), sgpos2.z()]
        xyFuture = positionDevice.moveToGlobal(sgpos2, speed)
        if zFuture is None:
            return xyFuture
        else:
            return MultiFuture([zFuture, xyFuture])

    def writeCalibration(self):
        cal = {'surfaceDepth': self.getSurfaceDepth()}
        self.writeConfigFile(cal, 'calibration')

    def focusDevice(self):
        if self._focusDevice is None:
            if 'focusDevice' in self.config:
                # check config first
                self._focusDevice = getManager().getDevice(self.config['focusDevice'])
            else:
                # if nothing was specified, then use the first parent stage with z positioning
                p = self
                while True:
                    if p is None or isinstance(p, Stage) and p.capabilities()['setPos'][2]:
                        self._focusDevice = p
                        break
                    p = p.parentDevice()
        return self._focusDevice

    def positionDevice(self):
        if self._positionDevice is None:
            p = self
            while True:
                if p is None or isinstance(p, Stage) and p.capabilities()['setPos'][0] and p.capabilities()['setPos'][1]:
                    self._positionDevice = p
                    break
                p = p.parentDevice()
        return self._positionDevice


class Objective(Device, OptomechDevice):

    def __init__(self, config, scope, key):
        self._config = config
        self._scope = scope
        self._key = key
        name = config['name']

        Device.__init__(self, scope.dm, config, name)
        OptomechDevice.__init__(self, scope.dm, config, name)

        if 'offset' in config:
            self.setOffset(config['offset'])
        if 'scale' in config:
            self.setScale(config['scale'])

    def deviceTransform(self, subdev=None):
        return pg.SRTTransform3D(super().deviceTransform(subdev))

    def defaultGeometryArgs(self):
        return {'color': (0, 0.7, 0.9, 0.4)}

    def getGeometries(self):
        return []  # Microscopes are in charge of deciding which objective to display

    def getRealGeometries(self):
        return Device.getGeometries(self)

    def setOffset(self, pos):
        tr = self.deviceTransform()
        tr.setTranslate(pos)
        self.setDeviceTransform(tr)

    def setScale(self, scale):
        if not hasattr(scale, '__len__'):
            scale = (scale, scale, 1)

        tr = self.deviceTransform()
        tr.setScale(scale)
        self.setDeviceTransform(tr)

    def offset(self):
        return self.deviceTransform().getTranslation()

    def scale(self):
        return self.deviceTransform().getScale()

    def key(self):
        return self._key

    def scope(self):
        return self._scope

    @property
    def radius(self):
        return self._config.get('radius')

    @property
    def topRadius(self):
        return self._config.get('topRadius')

    @property
    def bottomRadius(self):
        return self._config.get('bottomRadius')

    @property
    def focalDistance(self):
        return self._config.get('focalDistance')

    def __repr__(self):
        return (f"<Objective {self._scope.name()}.{self.name()} "
                f"offset={self.offset().x():0.2g},{self.offset().y():0.2g} "
                f"scale={self.scale().x():0.2g}>")


class ScopeGUI(Qt.QWidget):
    """Microscope GUI displayed in Manager window.
    Shows selection of objectives and allows scale/offset to be changed for each."""

    def __init__(self, dev, win):
        Qt.QWidget.__init__(self)
        self.win = win
        self.dev = dev
        self.dev.sigObjectiveChanged.connect(self.objectiveChanged)

        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.objList = self.dev._allObjectives()
        self.switchN = len(self.objList)
        self.objWidgets = {}
        self.blockSpinChange = False
        for row, obj in enumerate(self.objList, start=1):
            ## For each objective, create a set of widgets for selecting and updating.
            c = Qt.QComboBox()
            r = Qt.QRadioButton(obj)

            xs = pg.SpinBox(step=1e-6, suffix='m', siPrefix=True)
            ys = pg.SpinBox(step=1e-6, suffix='m', siPrefix=True)
            zs = pg.SpinBox(step=1e-6, suffix='m', siPrefix=True)
            xyss = pg.SpinBox(step=1e-7, bounds=(1e-10, None))
            zss = pg.SpinBox(step=1e-7, bounds=(1e-10, None))

            xs.index = ys.index = zs.index = xyss.index = zss.index = obj  ## used to determine which row has changed
            widgets = (r, c, xs, ys, zs, xyss, zss)
            for col, w in enumerate(widgets):
                self.ui.objectiveLayout.addWidget(w, row, col)
            self.objWidgets[obj] = widgets

            for o in self.objList[obj].values():
                c.addItem(o.name(), o)
                o.sigTransformChanged.connect(self.updateSpins)

            ## objectives are accessed like:
            ##   index = changedWidget.index
            ##   combo = self.objWidgets[index][1]
            ##   obj = combo.currentData()

            r.clicked.connect(self.objRadioClicked)
            c.currentIndexChanged.connect(self.objComboChanged)
            xs.sigValueChanged.connect(self.offsetSpinChanged)
            ys.sigValueChanged.connect(self.offsetSpinChanged)
            zs.sigValueChanged.connect(self.offsetSpinChanged)
            xyss.sigValueChanged.connect(self.scaleSpinChanged)
            zss.sigValueChanged.connect(self.scaleSpinChanged)

        for preset, preset_conf in dev.presets.items():
            btn = Qt.QPushButton(preset)
            btn.setObjectName(preset)
            self.ui.presetLayout.addWidget(btn)
            btn.clicked.connect(self.loadPreset)
            # hotkeys
            if 'hotkey' in preset_conf:
                hotkey = preset_conf['hotkey']
                hotkey_dev = dev.dm.getDevice(hotkey["device"])
                key = hotkey["key"]
                hotkey_dev.addKeyCallback(key, dev.handlePresetHotkey, (preset,))
        self.updateSpins()

    def loadPreset(self):
        btn = self.sender()
        name = btn.objectName()
        self.dev.loadPreset(name)

    def objectiveChanged(self, obj):
        ## Microscope says new objective has been selected; update selection radio
        (obj, old) = obj
        index = obj.key()[0]
        self.objWidgets[index][0].setChecked(True)

    def objRadioClicked(self):
        for obj in self.objList:
            if self.objWidgets[obj][0].isChecked():
                self.dev.setObjectiveIndex(obj)
                break

    def objComboChanged(self):
        combo = self.sender()
        self.dev.selectObjective(combo.itemData(combo.currentIndex()))
        self.blockSpinChange = True
        try:
            self.updateSpins()
        finally:
            self.blockSpinChange = False

    def offsetSpinChanged(self, spin):
        if self.blockSpinChange:
            return
        index = spin.index
        (r, combo, xs, ys, zs, xyss, zss) = self.objWidgets[index]
        obj = combo.itemData(combo.currentIndex())
        if callable(getattr(obj, "toPyObject", None)):
            obj = obj.toPyObject()
        obj.sigTransformChanged.disconnect(self.updateSpins)
        try:
            obj.setOffset((xs.value(), ys.value(), zs.value()))
        finally:
            obj.sigTransformChanged.connect(self.updateSpins)

    def scaleSpinChanged(self, spin):
        if self.blockSpinChange:
            return
        index = spin.index
        (r, combo, xs, ys, zs, xyss, zss) = self.objWidgets[index]
        obj = combo.itemData(combo.currentIndex())
        if callable(getattr(obj, "toPyObject", None)):
            obj = obj.toPyObject()
        obj.sigTransformChanged.disconnect(self.updateSpins)
        try:
            obj.setScale((xyss.value(), xyss.value(), zss.value()))
        finally:
            obj.sigTransformChanged.connect(self.updateSpins)

    def updateSpins(self):
        for k, w in self.objWidgets.items():
            (r, combo, xs, ys, zs, xyss, zss) = w
            obj = combo.itemData(combo.currentIndex())
            if callable(getattr(obj, "toPyObject", None)):
                obj = obj.toPyObject()

            offset = obj.offset()
            xs.setValue(offset.x())
            ys.setValue(offset.y())
            zs.setValue(offset.z())

            scale = obj.scale()
            xyss.setValue(scale.x())
            zss.setValue(scale.z())


class ScopeCameraModInterface(CameraModuleInterface):
    """Implements focus control user interface for use in the camera module.
    """
    canImage = False

    def __init__(self, dev, mod):
        CameraModuleInterface.__init__(self, dev, mod)

        self.ctrl = Qt.QWidget()
        self.layout = Qt.QGridLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.ctrl.setLayout(self.layout)

        self.plot = mod.window().getDepthView()
        self.focusLine = self.plot.addLine(y=0, pen='y')
        sd = dev.getSurfaceDepth()
        if sd is None:
            sd = 0
        self.surfaceLine = self.plot.addLine(y=sd, pen='g')
        self.movableFocusLine = self.plot.addLine(y=0, pen='y', markers=[('<|>', 0.5, 10)], movable=True)

        # Note: this is placed here because there is currently no better place.
        # Ideally, the sample orientation, height, and anatomical identity would be contained 
        # in a Sample or Slice object elsewhere..
        self.setSurfaceBtn = Qt.QPushButton('Set Surface')
        self.layout.addWidget(self.setSurfaceBtn, 0, 0)
        self.setSurfaceBtn.clicked.connect(self.setSurfaceClicked)

        self.findSurfaceBtn = Qt.QPushButton('Find Surface')
        self.layout.addWidget(self.findSurfaceBtn, 1, 0)
        self.findSurfaceBtn.clicked.connect(self.findSurfaceClicked)

        self.depthLabel = pg.ValueLabel(suffix='m', siPrefix=True)
        self.layout.addWidget(self.depthLabel, 2, 0)

        dev.sigGlobalTransformChanged.connect(self.transformChanged)
        dev.sigSurfaceDepthChanged.connect(self.surfaceDepthChanged)

        # only works with devices that can change their waypoint while in motion
        # self.movableFocusLine.sigDragged.connect(self.focusDragged)
        self.movableFocusLine.sigPositionChangeFinished.connect(self.focusDragged)

        self.transformChanged()

    def setSurfaceClicked(self):
        focus = self.getDevice().getFocusDepth()
        self.getDevice().setSurfaceDepth(focus)
        self.transformChanged()

    def findSurfaceClicked(self):
        self.getDevice().findSurfaceDepth(self.getDevice().getDefaultImager())

    def surfaceDepthChanged(self, depth):
        self.surfaceLine.setValue(depth)

    def transformChanged(self):
        focus = self.getDevice().getFocusDepth()
        self.focusLine.setValue(focus)

        # Compute the target focal plane.
        # This is a little tricky because the objective might have an offset+scale relative
        # to the focus device.
        fd = self.getDevice().focusDevice()
        if fd is None:
            return
        tpos = fd.globalTargetPosition()
        fpos = fd.globalPosition()
        dif = tpos[2] - fpos[2]
        with pg.SignalBlock(self.movableFocusLine.sigPositionChangeFinished, self.focusDragged):
            self.movableFocusLine.setValue(focus + dif)

        sdepth = self.getDevice().getSurfaceDepth()
        if sdepth is not None:
            depth = focus - sdepth
            self.depthLabel.setValue(depth)

    def focusDragged(self):
        self.getDevice().setFocusDepth(self.movableFocusLine.value())

    def controlWidget(self):
        return self.ctrl

    def boundingRect(self):
        return None

    def quit(self):
        pass
