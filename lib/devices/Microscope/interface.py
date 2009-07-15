# -*- coding: utf-8 -*-
from lib.devices.Device import *

class Microscope(Device):
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = QtCore.QMutex(QtCore.QMutex.Recursive)
        self.posDev = None
        self.objDev = None
        if 'positionDevice' in config:
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
            objList = self.config['objectives'][str(state)]
            self.objective = objList[objList.keys()[0]]
            QtCore.QObject.connect(self.posDev, QtCore.SIGNAL('switchChanged'), self.objectiveChanged)
        

    def quit(self):
        pass

    def positionChanged(self, p):
        l = QtCore.QMutexLocker(self.lock)
        rel = []
        for i in range(len(self.position)):
            rel.append(p['rel'][i] * self.positionScale[i])
            self.position[i] += rel[i]
        self.emit(QtCore.SIGNAL('positionChanged'), {'abs': self.position, 'rel': rel})
        
    def objectiveChanged(self, o):
        l = QtCore.QMutexLocker(self.lock)
        if self.objSwitchId in o:
            state = o[self.objSwitchId]
            self.objective = self.config['objectives'][str(state)]
        self.emit(QtCore.SIGNAL('objectiveChanged'), self.objective)

    def getPosition(self):
        """Return x,y,z position of microscope stage"""
        l = QtCore.QMutexLocker(self.lock)
        return self.position[:]
        
    def getObjective(self):
        """Return a tuple ("objective name", scale)"""
        l = QtCore.QMutexLocker(self.lock)
        return self.objective.copy()
        
    def getState(self):
        l = QtCore.QMutexLocker(self.lock)
        return {'position': self.position[:], 'objective': self.objective[:]}
    