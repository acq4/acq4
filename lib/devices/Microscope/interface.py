# -*- coding: utf-8 -*-
from __future__ import with_statement
from lib.devices.Device import *
from deviceTemplate import Ui_Form
from lib.util.Mutex import Mutex, MutexLocker

def ftrace(func):
    def w(*args, **kargs):
        print "Microscope:" + func.__name__ + " start"
        rv = func(*args, **kargs)
        print "Microscope:" + func.__name__ + " done"
        return rv
    return w

class Microscope(Device):
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
            nax = len(self.posDev.getPosition())
            self.position = [0.0,] * nax
            if 'positionScale' in config:
                ps = config['positionScale']
                if type(ps) in [tuple, list]:
                    self.positionScale = ps
                else:
                    self.positionScale = (ps,) * nax
            else:
                self.positionScale = (1.0,) * nax
            QtCore.QObject.connect(self.posDev, QtCore.SIGNAL('positionChanged'), self.positionChanged)
        
        self.allObjectives = self.config['objectives']  ## all available objectives
        for l in self.allObjectives.values():  ## Set default values for each objective
            for o in l:
                if 'offset' not in l[o]:
                    l[o]['offset'] = [0,0]

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
            QtCore.QObject.connect(self.posDev, QtCore.SIGNAL('switchChanged'), self.objectiveSwitched)
        
        self.setObjective(currentObj)

    def quit(self):
        pass
    
    #@ftrace
    def positionChanged(self, p):
        with MutexLocker(self.lock):
            #rel = []
            #for i in range(len(self.position)):
                #rel.append(p['rel'][i] * self.positionScale[i])
                #self.position[i] += rel[i]
            self.position = [p['abs'][self.axisOrder[i]] * self.positionScale[i] for i in range(len(self.position))]
            rel = [p['rel'][self.axisOrder[i]] * self.positionScale[i] for i in range(len(self.position))]
            p = self.position[:]

        ## Mutex must be released before emitting!
        self.emit(QtCore.SIGNAL('positionChanged'), {'abs': p, 'rel': rel})
        
    def objectiveSwitched(self, change):
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
            self.emit(QtCore.SIGNAL('objectiveChanged'), (obj, index, lastObj))
        
    #@ftrace
    def getPosition(self):
        """Return x,y,z position of microscope stage"""
        with MutexLocker(self.lock):
            #print "Microscope:getPosition locked"
            return self.position[:]
        
    #@ftrace
    def getObjective(self):
        """Return a tuple ("objective name", scale)"""
        with MutexLocker(self.lock):
            #print "Microscope:getObjective locked"
            if self.currentObjective not in self.objectives:
                return None
            obj = self.objectives[self.currentObjective]
            return self.allObjectives[self.currentObjective][obj].copy()
        
    def listObjectives(self, allObjs=True):
        if allObjs:
            return self.allObjectives
        else:
            l = {}
            for i in self.objectives:
                l[i] = self.allObjectives[i][self.objectives[i]]
            return l
        
    #@ftrace
    def getState(self):
        with MutexLocker(self.lock):
            return {'position': self.position[:], 'objective': self.objective[:]}
    
    def deviceInterface(self):
        iface = ScopeGUI(self)
        iface.objectiveChanged((None, self.currentObjective, None))
        iface.positionChanged({'abs': self.getPosition()})
        return iface

    def selectObjectives(self, sel):
        """Set the objective to be picked from each list when the switch changes"""
        for i in self.allObjectives:
            if i in sel:
                self.objectives[i] = sel[i]
        self.emit(QtCore.SIGNAL('objectiveListChanged'))
                

    
class ScopeGUI(QtGui.QWidget):
    def __init__(self, dev):
        QtGui.QWidget.__init__(self)
        self.dev = dev
        QtCore.QObject.connect(self.dev, QtCore.SIGNAL('objectiveChanged'), self.objectiveChanged)
        QtCore.QObject.connect(self.dev, QtCore.SIGNAL('positionChanged'), self.positionChanged)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.objList = self.dev.listObjectives()
        self.switchN = len(self.objList)
        self.objCombos = {}
        self.objRadios = {}
        for i in self.objList:
            c = QtGui.QComboBox()
            r = QtGui.QRadioButton(i)
            self.ui.objRadioLayout.addWidget(r)
            self.ui.objComboLayout.addWidget(c)
            self.objCombos[i] = c
            self.objRadios[i] = r
            for o in self.objList[i]:
                c.addItem(self.objList[i][o]['name'], QtCore.QVariant(QtCore.QString(o)))
            QtCore.QObject.connect(r, QtCore.SIGNAL('clicked()'), self.objRadioClicked)
            QtCore.QObject.connect(c, QtCore.SIGNAL('currentIndexChanged(int)'), self.objComboChanged)
        
    def objectiveChanged(self,obj):
        (obj, oid, old) = obj
        self.objRadios[oid].setChecked(True)
                
    def positionChanged(self, p):
        self.ui.positionLabel.setText('%0.2f, %0.2f' % (p['abs'][0] * 1e6, p['abs'][1] * 1e6))
                
    def objRadioClicked(self):
        checked = None
        for r in self.objRadios:
            if self.objRadios[r].isChecked():
                checked = r
                break
        self.dev.setObjective(r)
        
    def objComboChanged(self):
        sel = {}
        for i in self.objCombos:
            c = self.objCombos[i]
            sel[i] = str(c.itemData(c.currentIndex()).toString())
        self.dev.selectObjectives(sel)
        
            
            
    
        