# -*- coding: utf-8 -*-
from lib.devices.Device import *
from deviceTemplate import Ui_Form

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
        self.lock = QtCore.QMutex(QtCore.QMutex.Recursive)
        self.posDev = None
        self.objDev = None
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
        if 'objectiveSwitch' in config:
            self.objDev = dm.getDevice(config['objectiveSwitch'][0])
            self.objSwitchId = config['objectiveSwitch'][1]
            state = self.objDev.getSwitch(self.objSwitchId)
            self.objList = self.config['objectives']  ## all available objectives
            self.objSelList = {}                      ## objective to use for each switch state
            for i in self.objList:
                self.objSelList[i] = self.objList[i].keys()[0]  ## Default to first obj in each list
            self.objective = self.objList[str(state)][self.objSelList[str(state)]]
            QtCore.QObject.connect(self.posDev, QtCore.SIGNAL('switchChanged'), self.objectiveChanged)
        

    def quit(self):
        pass
    
    #@ftrace
    def positionChanged(self, p):
        l = QtCore.QMutexLocker(self.lock)
        #rel = []
        #for i in range(len(self.position)):
            #rel.append(p['rel'][i] * self.positionScale[i])
            #self.position[i] += rel[i]
        self.position = [p['abs'][self.axisOrder[i]] * self.positionScale[i] for i in range(len(self.position))]
        rel = [p['rel'][self.axisOrder[i]] * self.positionScale[i] for i in range(len(self.position))]
        p = self.position[:]
        
        l.unlock() ## always release mutex before emitting!
        self.emit(QtCore.SIGNAL('positionChanged'), {'abs': p, 'rel': rel})
        
    #@ftrace
    def objectiveChanged(self, o):
        l = QtCore.QMutexLocker(self.lock)
        if self.objSwitchId in o:
            state = str(o[self.objSwitchId])
            lastObj = self.objective
            self.objective = self.objList[str(state)][self.objSelList[str(state)]]
            #self.objective = self.config['objectives'][state]
            obj = self.objective.copy()
            l.unlock()  ## always release mutex before emitting!
            self.emit(QtCore.SIGNAL('objectiveChanged'), (obj, state, lastObj))

    #@ftrace
    def getPosition(self):
        """Return x,y,z position of microscope stage"""
        l = QtCore.QMutexLocker(self.lock)
        #print "Microscope:getPosition locked"
        return self.position[:]
        
    #@ftrace
    def getObjective(self):
        """Return a tuple ("objective name", scale)"""
        l = QtCore.QMutexLocker(self.lock)
        #print "Microscope:getObjective locked"
        return self.objective.copy()
        
    def listObjectives(self):
        return self.objList
        
    #@ftrace
    def getState(self):
        l = QtCore.QMutexLocker(self.lock)
        return {'position': self.position[:], 'objective': self.objective[:]}
    
    def deviceInterface(self):
        return ScopeGUI(self)

    def selectObjectives(self, sel):
        """Set the objective to be picked from each list when the switch changes"""
        for i in self.objList:
            if i in sel:
                self.objSelList[i] = sel[i]
                

    
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
            QtCore.QObject.connect(c, QtCore.SIGNAL('clicked()'), self.objRadioClicked)
            QtCore.QObject.connect(c, QtCore.SIGNAL('currentIndexChanged(int)'), self.objComboChanged)
        
    def objectiveChanged(self,obj):
        (obj, oid, old) = obj
        self.objRadios[oid].setChecked(True)
                
    def positionChanged(self, p):
        self.ui.positionLabel.setText('%0.2f, %0.2f' % (p['abs'][0] * 1e6, p['abs'][1] * 1e6))
                
    def objRadioClicked(self):
        pass
        
        
    def objComboChanged(self):
        sel = {}
        for i in self.objList:
            c = self.objCombos[i]
            o = str(c.itemData(c.currentIndex()).toString())
            sel[i] = o
        self.dev.selectObjectives(sel)
        
            
            
    
        