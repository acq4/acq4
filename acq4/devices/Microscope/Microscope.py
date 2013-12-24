# -*- coding: utf-8 -*-
from acq4.devices.OptomechDevice import *
from deviceTemplate import Ui_Form
from acq4.util.Mutex import Mutex
import acq4.pyqtgraph as pg
import collections


class Microscope(Device, OptomechDevice):
    """
    The Microscope device class is used primarily to manage the transformation and calibration changes associated with multi-objective scopes.
    
    * Maintains list of objective positions (most scopes have 2-5 positions)
    * For each position, maintains a list of possible objectives that may be found there
      (this allows the experimenter to change the objective at a certain position 
      during the experiment)
    * Support for automatically selecting the correct objective position based on a Switch device
    * Each objective has an offset and scale factor associated with it. This transormation is communicated
      automatically to all rigidly-connected child devices.
    """
    
    sigObjectiveChanged = QtCore.Signal(object) ## (objective, lastObjective)
    sigObjectiveListChanged = QtCore.Signal()
    
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)
        self.config = config
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.switchDevice = None
        self.currentSwitchPosition = None
        self.currentObjective = None
        
        self.objectives = collections.OrderedDict()
        ## Format of self.objectives is:
        ## { 
        ##    switchPosition1: {objName1: objective1, objName2: objective, ...},
        ##    switchPosition2: {objName1: objective1, objName2: objective, ...},
        ## }
        
        for k1,objs in config['objectives'].iteritems():  ## Set default values for each objective
            self.objectives[k1] = collections.OrderedDict()
            for k2,o in objs.iteritems():
                obj = Objective(o, self, (k1, k2))
                self.objectives[k1][k2] = obj
                #obj.sigTransformChanged.connect(self.objectiveTransformChanged)
                

        ## Keep track of the objective currently in use for each position
        ## Format is: { switchPosition1: objective1,  ... }
        self.selectedObjectives = collections.OrderedDict(
            [(i, self.objectives[i].values()[0]) for i in self.objectives]
        )
        for obj in self.selectedObjectives.values():
            self.addSubdevice(obj)
        
        
        ## If there is a switch device, configure it here
        if 'objectiveSwitch' in config:
            self.switchDevice = dm.getDevice(config['objectiveSwitch'][0])  ## Switch device
            self.objSwitchId = config['objectiveSwitch'][1]           ## Switch ID
            #self.currentSwitchPosition = str(self.switchDevice.getSwitch(self.objSwitchId))
            self.switchDevice.sigSwitchChanged.connect(self.objectiveSwitchChanged)
            self.objectiveSwitchChanged()
        else:
            self.setObjectiveIndex(0)
        
        dm.declareInterface(name, ['microscope'], self)

    def quit(self):
        pass
    
    def objectiveSwitchChanged(self, sw=None, change=None):
        ## Called when the switch device has changed, NOT when the user has selected a different objective.
        ## *change* looks like { switchId1: newValue, switchId2: newValue, ... }
        if sw is None:
            change = {self.objSwitchId: self.switchDevice.getSwitch(self.objSwitchId)}
            
        if self.objSwitchId not in change: ## the switch(es) that changed are not relevant to this device
            return
        state = str(change[self.objSwitchId])
        self.setObjectiveIndex(state)
    
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

    #def updateDeviceTransform(self):
        #obj = self.getObjective()
        #self.setDeviceTransform(obj.transform())
    
    def getObjective(self):
        """Return the currently active Objective."""
        with self.lock:
            if self.currentSwitchPosition not in self.selectedObjectives:
                return None
            return self.selectedObjectives[self.currentSwitchPosition]
            #return self.objectives[self.currentSwitchPosition][selected]
    
    def listObjectives(self):
        """
        Return a list of available objectives. (one objective returned per switch position)
        """
        with self.lock:
            return self.selectedObjectives.values()
            #l = collections.OrderedDict()
            #for i in self.selectedObjectives:
                #l[i] = self.objectives[i][self.selectedObjectives[i]]
            #return l
    
    def deviceInterface(self, win):
        iface = ScopeGUI(self, win)
        iface.objectiveChanged((self.currentObjective, None))
        #iface.positionChanged({'abs': self.getPosition()})
        return iface

    def selectObjective(self, obj):
        ##Set the currently-active objective for a particular switch position
        ##This is _not_ the same as setObjectiveIndex.
        index = obj.key()[0]
        with self.lock:
            self.removeSubdevice(self.selectedObjectives[index])
            self.selectedObjectives[index] = obj
            self.addSubdevice(obj)
        self.setObjectiveIndex(self.currentSwitchPosition) # update self.currentObjective, send signals (if needed)
        self.sigObjectiveListChanged.emit()

    def _allObjectives(self):
        ## used by (preferrably only) GUI interface
        return self.objectives
    
    #def objectiveTransformChanged(self, obj):
        #if obj is self.currentObjective:
            #self.updateDeviceTransform()


class Objective(OptomechDevice):
    
    #class SignalProxyObject(QtCore.QObject):
        #sigTransformChanged = QtCore.Signal(object) ## self
    
    def __init__(self, config, scope, key):
        #self.__sigProxy = Objective.SignalProxyObject()
        #self.sigTransformChanged = self.__sigProxy.sigTransformChanged
        #self._config = config
        self._config = config
        self._scope = scope
        self._key = key
        offset = config.get('offset', pg.Vector(0,0,0))
        scale = config.get('scale', pg.Vector(1,1,1))
        name = config['name']
        
        OptomechDevice.__init__(self, scope.dm, {}, name)
        
        if 'offset' in config:
            self.setOffset(config['offset'])
        if 'scale' in config:
            self.setScale(config['scale'])
            
    #def updateTransform(self):
        #tr = pg.SRTTransform3D()
        #tr.translate(self._offset)
        #tr.scale(self._scale)
        #self.setDeviceTransform(tr)
    
    def deviceTransform(self):
        return pg.SRTTransform3D(OptomechDevice.deviceTransform(self))
    
    def setOffset(self, pos):
        tr = self.deviceTransform()
        tr.setTranslate(pos)
        self.setDeviceTransform(tr)
        #self._offset = pg.Vector(pos)
        #self.sigTransformChanged.emit(self)
        #self.updateTransform()
    
    def setScale(self, scale):
        if not hasattr(scale, '__len__'):
            scale = (scale, scale)
        
        tr = self.deviceTransform()
        tr.setScale(scale)
        self.setDeviceTransform(tr)
        #self._scale = pg.Vector(scale, scale, 1)
        #self.sigTransformChanged.emit(self)
        #self.updateTransform()
    
    def offset(self):
        return self.deviceTransform().getTranslation()
        #return pg.Vector(self._offset)
        
    def scale(self):
        return self.deviceTransform().getScale()
        #return pg.Vector(self._scale)

    #def name(self):
        #return self._name
    
    def key(self):
        return self._key

    def scope(self):
        return self._scope
        
    def __repr__(self):
        return "<Objective %s.%s offset=%0.2g,%0.2g scale=%0.2g>" % (self._scope.name(), self.name(), self.offset().x(), self.offset().y(), self.scale().x())



class ScopeGUI(QtGui.QWidget):
    """Microscope GUI displayed in Manager window.
    Shows selection of objectives and allows scale/offset to be changed for each."""
    
    def __init__(self, dev, win):
        QtGui.QWidget.__init__(self)
        self.win = win
        self.dev = dev
        self.dev.sigObjectiveChanged.connect(self.objectiveChanged)
        #self.dev.sigPositionChanged.connect(self.positionChanged)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.objList = self.dev._allObjectives()
        self.switchN = len(self.objList)
        self.objWidgets = {}
        self.blockSpinChange = False
        row = 1
        for i in self.objList:
            ## For each objective, create a set of widgets for selecting and updating.
            c = QtGui.QComboBox()
            r = QtGui.QRadioButton(i)
            #first = self.objList[i].keys()[0]
            #first = self.objList[i][first]
            xs = pg.SpinBox(step=1e-6, suffix='m', siPrefix=True)
            ys = pg.SpinBox(step=1e-6, suffix='m', siPrefix=True)
            ss = pg.SpinBox(step=1e-7, bounds=(1e-10, None))
            
            xs.index = ys.index = ss.index = i  ## used to determine which row has changed
            widgets = (r, c, xs, ys, ss)
            for col in range(5):
                self.ui.objectiveLayout.addWidget(widgets[col], row, col)
            self.objWidgets[i] = widgets
            
            for o in self.objList[i].values():
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
            ss.sigValueChanged.connect(self.scaleSpinChanged)
            row += 1
        self.updateSpins()
    
    def objectiveChanged(self, obj):
        ## Microscope says new objective has been selected; update selection radio
        (obj, old) = obj
        index = obj.key()[0]
        self.objWidgets[index][0].setChecked(True)
    
    def objRadioClicked(self):
        checked = None
        for r in self.objList:
            if self.objWidgets[r][0].isChecked():
                checked = r
                break
        self.dev.setObjectiveIndex(r)
    
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
        (r, combo, xs, ys, ss) = self.objWidgets[index]
        obj = combo.itemData(combo.currentIndex())
        obj.sigTransformChanged.disconnect(self.updateSpins)
        try:
            obj.setOffset((xs.value(), ys.value()))
        finally:
            obj.sigTransformChanged.connect(self.updateSpins)
    
    def scaleSpinChanged(self, spin):
        if self.blockSpinChange:
            return
        index = spin.index
        (r, combo, xs, ys, ss) = self.objWidgets[index]
        obj = combo.itemData(combo.currentIndex())
        obj.sigTransformChanged.disconnect(self.updateSpins)
        try:
            obj.setScale(ss.value())
        finally:
            obj.sigTransformChanged.connect(self.updateSpins)
        
    def updateSpins(self):
        for k, w in self.objWidgets.iteritems():
            (r, combo, xs, ys, ss) = w
            obj = combo.itemData(combo.currentIndex())
            offset = obj.offset()
            xs.setValue(offset.x())
            ys.setValue(offset.y())
            ss.setValue(obj.scale().x())


