# -*- coding: utf-8 -*-
from lib.devices.RigidDevice import *
from deviceTemplate import Ui_Form
from Mutex import Mutex
import pyqtgraph as pg
import collections

def ftrace(func):
    def w(*args, **kargs):
        print "Microscope:" + func.__name__ + " start"
        rv = func(*args, **kargs)
        print "Microscope:" + func.__name__ + " done"
        return rv
    return w

class Microscope(Device, RigidDevice):
    
    sigObjectiveChanged = QtCore.Signal(object) ## (objective, index, lastObjective)
    sigObjectiveListChanged = QtCore.Signal()
    
    ## we now use RigidDevice.sigTransformChanged instead.
    #sigPositionChanged = QtCore.Signal(object)  ## {'abs': pos, 'rel': pos}
    
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        RigidDevice.__init__(self, dm, config, name)
        self.config = config
        self.lock = Mutex(QtCore.QMutex.Recursive)
        #self.posDev = None
        self.switchDevice = None
        self.currentSwitchPosition = None
        
        #if 'positionDevice' in config:
            #if 'axisOrder' not in config:
                #self.axisOrder = [0,1]
            #else:
                #self.axisOrder = config['axisOrder']
                
            #self.posDev = dm.getDevice(config['positionDevice'])
            #pos = self.posDev.getPosition()
            #nax = len(pos)
            #self.position = [0.0,] * nax
            #if 'positionScale' in config:
                #ps = config['positionScale']
                #if type(ps) in [tuple, list]:
                    #self.positionScale = ps
                #else:
                    #self.positionScale = (ps,) * nax
            #else:
                #self.positionScale = (1.0,) * nax
            #self.positionChanged({'abs': pos, 'rel': pos})
            #self.posDev.sigPositionChanged.connect(self.positionChanged)
        #else:
            #self.position = [0.0, 0.0, 0.0]
        
        #self.objectives = config['objectives']  ## all available objectives
        self.objectives = collections.OrderedDict()
        for k1,objs in config['objectives'].iteritems():  ## Set default values for each objective
            self.objectives[k1] = collections.OrderedDict()
            for k2,o in objs:
                self.objectives[k1][k2] = Objective(o, self, (k1, k2))

        ## Keep track of the objective currently in use for each position
        self.selectedObjectives = collections.OrderedDict(
            [(i, self.objectives[i].keys()[0]) for i in self.objectives]
        )
        
        
        ## If there is a switch device, configure it here
        if 'objectiveSwitch' in config:
            self.switchDevice = dm.getDevice(config['objectiveSwitch'][0])  ## Switch device
            self.objSwitchId = config['objectiveSwitch'][1]           ## Switch ID
            #self.currentSwitchPosition = str(self.switchDevice.getSwitch(self.objSwitchId))
            self.switchDevice.sigSwitchChanged.connect(self.objectiveSwitched)
            self.objectiveSwitched()
        else:
            self.setObjective(0)
        
        dm.declareInterface(name, ['microscope'], self)

    def quit(self):
        pass
    
    #@ftrace
    #def positionChanged(self, p):
        #with self.lock:
            ##rel = []
            ##for i in range(len(self.position)):
                ##rel.append(p['rel'][i] * self.positionScale[i])
                ##self.position[i] += rel[i]
            ##print p['abs'], self.axisOrder, self.positionScale, self.position
            #self.position = [p['abs'][self.axisOrder[i]] * self.positionScale[i] for i in range(len(self.position))]
            #rel = [p['rel'][self.axisOrder[i]] * self.positionScale[i] for i in range(len(self.position))]
            #p = self.position[:]

        ### Mutex must be released before emitting!
        ##self.emit(QtCore.SIGNAL('positionChanged'), {'abs': p, 'rel': rel})
        #self.sigPositionChanged.emit({'abs': p, 'rel': rel})
        
    def objectiveSwitched(self, sw, change):
        ## Called when the switch device has changed, NOT when the user has selected a different objective.
        if self.objSwitchId not in change:
            return
        state = str(change[self.objSwitchId])
        self.setObjective(state)
        
    def setObjective(self, index):
        """Selects the objective currently in position *index*"""
        index = str(index)
        if index == self.currentSwitchPosition:
            return
            
        if index not in self.selectedObjectives:
            raise Exception("Requested invalid objective switch position: %s (options are %s)" % (index, ', '.join(self.objectives.keys())))
            
        lastObj = self.getObjective()
        self.currentSwitchPosition = index
        obj = self.getObjective()
        self.updateDeviceTransform()
        #self.emit(QtCore.SIGNAL('objectiveChanged'), (obj, index, lastObj))
        self.sigObjectiveChanged.emit((obj, index, lastObj))

    def updateDeviceTransform(self):
        obj = self.currentObjective()
        self.setDeviceTransform(obj.transform())
        
            
    #@ftrace
    #def getPosition(self):
        #"""Return x,y,z position of microscope stage"""
        #with self.lock:
            ##print "Microscope:getPosition locked"
            #return self.position[:]
        
    #@ftrace
    def getObjective(self):
        """Return a dict {'name': , 'scale': , 'offset': } for the current objective"""
        with self.lock:
            #print "Microscope:getObjective locked"
            if self.currentSwitchPosition not in self.selectedObjectives:
                return None
            obj = self.selectedObjectives[self.currentSwitchPosition]
            return self.objectives[self.currentSwitchPosition][obj].copy()
        
    def listObjectives(self, allObjs=True):
        with self.lock:
            if allObjs:
                return self.objectives
            else:
                l = {}
                for i in self.selectedObjectives:
                    l[i] = self.objectives[i][self.selectedObjectives[i]]
                return l
        
    #@ftrace
    ## will need a suitable replacement for this..
    #def getState(self):
        #with self.lock:
            #return {'position': self.position[:], 'objective': self.getObjective()}
    
    def deviceInterface(self, win):
        iface = ScopeGUI(self, win)
        iface.objectiveChanged((None, self.currentSwitchPosition, None))
        #iface.positionChanged({'abs': self.getPosition()})
        return iface

    def selectObjectives(self, sel):
        """Set the objective to be picked from each list when the switch changes"""
        with self.lock:
            for i in self.objectives:
                if i in sel:
                    self.selectedObjectives[i] = sel[i]
        #self.emit(QtCore.SIGNAL('objectiveListChanged'))
        self.updateDeviceTransform()
        self.sigObjectiveListChanged.emit()
        
    #def updateObjectives(self, objs):
        #with self.lock:
            #self.objectives = objs.copy()
        ##self.emit(QtCore.SIGNAL('objectiveListChanged'))
        #self.updateDeviceTransform()
        #self.sigObjectiveListChanged.emit()


class Objective(QtCore.QObject):
    
    sigTransformChanged = QtCore.Signal(object) ## self
    
    def __init__(self, config, scope, key):
        QtCore.QObject.__init__(self)
        self.config = config
        self.scope = scope
        self.key = key
                if 'offset' not in l[o]:
                    l[o]['offset'] = pg.Vector(0,0)
                else:
                    l[o]['offset'] = pg.Vector(l[o]['offset'])
                if 'scale' not in l[o]:
                    l[o]['scale'] = pg.Vector(1,1,1)
                else:
                    
                    l[o]['scale'] = pg.Vector(l[o]['scale'])
    
    def transform(self):
            obj = self.getObjective()
            tr = pg.Transform3D()
            tr.translate(*obj['offset'])
            tr.scale(*obj['scale'])
            return tr
            
    def setOffset(self, pos):
        pass
    
    def setScale(self, scale):
        pass



class ScopeGUI(QtGui.QWidget):
    
    
    def __init__(self, dev, win):
        QtGui.QWidget.__init__(self)
        self.win = win
        self.dev = dev
        self.dev.sigObjectiveChanged.connect(self.objectiveChanged)
        #self.dev.sigPositionChanged.connect(self.positionChanged)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.objList = self.dev.listObjectives()
        self.switchN = len(self.objList)
        self.objWidgets = {}
        row = 1
        for i in self.objList:
            ## For each objective, create a set of widgets for selecting and updating.
            c = QtGui.QComboBox()
            r = QtGui.QRadioButton(i)
            first = self.objList[i].keys()[0]
            first = self.objList[i][first]
            xs = pg.SpinBox(value=first['offset'][0], step=1e-6, suffix='m', siPrefix=True)
            ys = pg.SpinBox(value=first['offset'][1], step=1e-6, suffix='m', siPrefix=True)
            ss = pg.SpinBox(value=first['scale']    , step=1e-7, bounds=(1e-10, None))
            xs.obj = ys.obj = ss.obj = i
            widgets = (r, c, xs, ys, ss)
            for col in range(5):
                self.ui.objectiveLayout.addWidget(widgets[col], row, col)
            self.objWidgets[i] = widgets
            
            for o in self.objList[i]:
                c.addItem(self.objList[i][o]['name'], o)
            r.clicked.connect(self.objRadioClicked)
            c.currentIndexChanged.connect(self.objComboChanged)
            xs.sigValueChanged.connect(self.xSpinChanged)
            ys.sigValueChanged.connect(self.ySpinChanged)
            ss.sigValueChanged.connect(self.sSpinChanged)
            row += 1
        
    def objectiveChanged(self,obj):
        (obj, oid, old) = obj
        self.objWidgets[oid][0].setChecked(True)
                
    #def positionChanged(self, p):
        #self.ui.positionLabel.setText('%0.2f, %0.2f' % (p['abs'][0] * 1e6, p['abs'][1] * 1e6))
                
    def objRadioClicked(self):
        checked = None
        for r in self.objList:
            if self.objWidgets[r][0].isChecked():
                checked = r
                break
        self.dev.setObjective(r)
        
    def objComboChanged(self):
        sel = {}
        for i in self.objList:
            sel[i] = self.selectedObj(i)
            xs, ys, ss = self.objWidgets[i][2:]
            obj = self.objList[i][sel[i]]
            xs.setValue(obj['offset'][0])
            ys.setValue(obj['offset'][1])
            ss.setValue(obj['scale'])
        self.dev.selectObjectives(sel)
        
            
    def xSpinChanged(self, spin):
        o = spin.obj
        o1 = self.selectedObj(o)
        self.objList[o][o1]['offset'][0] = spin.value()
        self.dev.updateObjectives(self.objList)
        
        
    def ySpinChanged(self, spin):
        o = spin.obj
        o1 = self.selectedObj(o)
        self.objList[o][o1]['offset'][1] = spin.value()
        self.dev.updateObjectives(self.objList)
        
    def sSpinChanged(self, spin):
        o = spin.obj
        o1 = self.selectedObj(o)
        self.objList[o][o1]['scale'] = spin.value()
        self.dev.updateObjectives(self.objList)
            
    def selectedObj(self, i):
        c = self.objWidgets[i][1]
        #return str(c.itemData(c.currentIndex()).toString())
        return c.itemData(c.currentIndex())
        