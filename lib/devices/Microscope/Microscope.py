# -*- coding: utf-8 -*-
from __future__ import with_statement
from lib.devices.Device import *
from deviceTemplate import Ui_Form
from Mutex import Mutex
from SpinBox import *

def ftrace(func):
    def w(*args, **kargs):
        print "Microscope:" + func.__name__ + " start"
        rv = func(*args, **kargs)
        print "Microscope:" + func.__name__ + " done"
        return rv
    return w

class Microscope(Device):
    
    sigObjectiveChanged = QtCore.Signal(object)
    sigObjectiveListChanged = QtCore.Signal()
    sigPositionChanged = QtCore.Signal(object)
    
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.posDev = None
        self.objDev = None
        self.currentObjective = None
        if 'positionDevice' in config:
            if 'axisOrder' not in config:
                self.axisOrder = [0,1]
            else:
                self.axisOrder = config['axisOrder']
                
            self.posDev = dm.getDevice(config['positionDevice'])
            pos = self.posDev.getPosition()
            nax = len(pos)
            self.position = [0.0,] * nax
            if 'positionScale' in config:
                ps = config['positionScale']
                if type(ps) in [tuple, list]:
                    self.positionScale = ps
                else:
                    self.positionScale = (ps,) * nax
            else:
                self.positionScale = (1.0,) * nax
            self.positionChanged({'abs': pos, 'rel': pos})
            #QtCore.QObject.connect(self.posDev, QtCore.SIGNAL('positionChanged'), self.positionChanged)
            self.posDev.sigPositionChanged.connect(self.positionChanged)
        else:
            self.position = [0.0, 0.0, 0.0]
        
        self.allObjectives = self.config['objectives']  ## all available objectives
        for l in self.allObjectives.itervalues():  ## Set default values for each objective
            for o in l:
                if 'offset' not in l[o]:
                    l[o]['offset'] = [0,0]
                else:
                    l[o]['offset'] = list(l[o]['offset'])

        ### Keep track of the objective currently in use for each position
        self.objectives = {}                      ## objective to use for each switch state
        for i in self.allObjectives:
            self.objectives[i] = self.allObjectives[i].keys()[0]  ## Default to first obj in each list
            
        currentObj = self.objectives.keys()[0]  ## Just guess that the first position is correct
        
        ## If there is a switch device, configure it here
        if 'objectiveSwitch' in config:
            self.objDev = dm.getDevice(config['objectiveSwitch'][0])  ## Switch device
            self.objSwitchId = config['objectiveSwitch'][1]           ## Switch ID
            currentObj = str(self.objDev.getSwitch(self.objSwitchId))           ## Get current switch state
            #QtCore.QObject.connect(self.posDev, QtCore.SIGNAL('switchChanged'), self.objectiveSwitched)
            self.objDev.sigSwitchChanged.connect(self.objectiveSwitched)
        
        self.setObjective(currentObj)

    def quit(self):
        pass
    
    #@ftrace
    def positionChanged(self, p):
        with self.lock:
            #rel = []
            #for i in range(len(self.position)):
                #rel.append(p['rel'][i] * self.positionScale[i])
                #self.position[i] += rel[i]
            #print p['abs'], self.axisOrder, self.positionScale, self.position
            self.position = [p['abs'][self.axisOrder[i]] * self.positionScale[i] for i in range(len(self.position))]
            rel = [p['rel'][self.axisOrder[i]] * self.positionScale[i] for i in range(len(self.position))]
            p = self.position[:]

        ## Mutex must be released before emitting!
        #self.emit(QtCore.SIGNAL('positionChanged'), {'abs': p, 'rel': rel})
        self.sigPositionChanged.emit({'abs': p, 'rel': rel})
        
    def objectiveSwitched(self, sw, change):
        """Called when the switch device has changed, NOT when the user has selected a different objective."""
        if self.objSwitchId not in change:
            return
        state = str(change[self.objSwitchId])
        self.setObjective(state)
        
    def setObjective(self, index):
        """Selects the objective currently in position 'index'"""
        if index != self.currentObjective:
            if index not in self.objectives:
                print "WARNING: objective position index '%s' invalid, not selecting" % index
                return
            lastObj = self.getObjective()
            self.currentObjective = index
            obj = self.getObjective()
            #self.emit(QtCore.SIGNAL('objectiveChanged'), (obj, index, lastObj))
            self.sigObjectiveChanged.emit((obj, index, lastObj))
        
    #@ftrace
    def getPosition(self):
        """Return x,y,z position of microscope stage"""
        with self.lock:
            #print "Microscope:getPosition locked"
            return self.position[:]
        
    #@ftrace
    def getObjective(self):
        """Return a tuple ("objective name", scale)"""
        with self.lock:
            #print "Microscope:getObjective locked"
            if self.currentObjective not in self.objectives:
                return None
            obj = self.objectives[self.currentObjective]
            return self.allObjectives[self.currentObjective][obj].copy()
        
    def listObjectives(self, allObjs=True):
        with self.lock:
            if allObjs:
                return self.allObjectives
            else:
                l = {}
                for i in self.objectives:
                    l[i] = self.allObjectives[i][self.objectives[i]]
                return l
        
    #@ftrace
    def getState(self):
        with self.lock:
            return {'position': self.position[:], 'objective': self.objective[:]}
    
    def deviceInterface(self, win):
        iface = ScopeGUI(self, win)
        iface.objectiveChanged((None, self.currentObjective, None))
        iface.positionChanged({'abs': self.getPosition()})
        return iface

    def selectObjectives(self, sel):
        """Set the objective to be picked from each list when the switch changes"""
        with self.lock:
            for i in self.allObjectives:
                if i in sel:
                    self.objectives[i] = sel[i]
        #self.emit(QtCore.SIGNAL('objectiveListChanged'))
        self.sigObjectiveListChanged.emit()
                
    def updateObjectives(self, objs):
        with self.lock:
            self.allObjectives = objs.copy()
        #self.emit(QtCore.SIGNAL('objectiveListChanged'))
        self.sigObjectiveListChanged.emit()
    
class ScopeGUI(QtGui.QWidget):
    
    
    def __init__(self, dev, win):
        QtGui.QWidget.__init__(self)
        self.win = win
        self.dev = dev
        #QtCore.QObject.connect(self.dev, QtCore.SIGNAL('objectiveChanged'), self.objectiveChanged)
        self.dev.sigObjectiveChanged.connect(self.objectiveChanged)
        #QtCore.QObject.connect(self.dev, QtCore.SIGNAL('positionChanged'), self.positionChanged)
        self.dev.sigPositionChanged.connect(self.positionChanged)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.objList = self.dev.listObjectives()
        self.switchN = len(self.objList)
        #self.objCombos = {}
        #self.objRadios = {}
        self.objWidgets = {}
        row = 1
        for i in self.objList:
            ## For each objective, create a set of widgets for selecting and updating.
            #print self.objList[i]
            c = QtGui.QComboBox()
            r = QtGui.QRadioButton(i)
            first = self.objList[i].keys()[0]
            first = self.objList[i][first]
            xs = SpinBox(value=first['offset'][0], step=1e-6, suffix='m', siPrefix=True)
            ys = SpinBox(value=first['offset'][1], step=1e-6, suffix='m', siPrefix=True)
            ss = SpinBox(value=first['scale']    , step=1e-7, bounds=(1e-10, None))
            xs.obj = ys.obj = ss.obj = i
            widgets = (r, c, xs, ys, ss)
            for col in range(5):
                self.ui.objectiveLayout.addWidget(widgets[col], row, col)
            self.objWidgets[i] = widgets
            
            for o in self.objList[i]:
                c.addItem(self.objList[i][o]['name'], QtCore.QVariant(QtCore.QString(o)))
            #QtCore.QObject.connect(r, QtCore.SIGNAL('clicked()'), self.objRadioClicked)
            r.clicked.connect(self.objRadioClicked)
            #QtCore.QObject.connect(c, QtCore.SIGNAL('currentIndexChanged(int)'), self.objComboChanged)
            c.currentIndexChanged.connect(self.objComboChanged)
            #QtCore.QObject.connect(xs, QtCore.SIGNAL('valueChanged'), self.xSpinChanged)
            xs.sigValueChanged.connect(self.xSpinChanged)
            #QtCore.QObject.connect(ys, QtCore.SIGNAL('valueChanged'), self.ySpinChanged)
            ys.sigValueChanged.connect(self.ySpinChanged)
            #QtCore.QObject.connect(ss, QtCore.SIGNAL('valueChanged'), self.sSpinChanged)
            ss.sigValueChanged.connect(self.sSpinChanged)
            row += 1
        
    def objectiveChanged(self,obj):
        (obj, oid, old) = obj
        self.objWidgets[oid][0].setChecked(True)
                
    def positionChanged(self, p):
        self.ui.positionLabel.setText('%0.2f, %0.2f' % (p['abs'][0] * 1e6, p['abs'][1] * 1e6))
                
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
        return str(c.itemData(c.currentIndex()).toString())
        