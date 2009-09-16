# -*- coding: utf-8 -*-
from ProtocolTemplate import Ui_Form
from lib.devices.Device import ProtocolGui
from PyQt4 import QtCore, QtGui
from lib.Manager import getManager
from lib.util.WidgetGroup import WidgetGroup
from lib.util.qtgraph.widgets import *

class ScannerProtoGui(ProtocolGui):
    def __init__(self, dev, prot):
        ProtocolGui.__init__(self, dev, prot)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        dm = getManager()

        ## Populate module/device lists, auto-select based on device defaults 
        defCam = None
        if 'defaultCamera' in self.dev.config:
            defCam = self.dev.config['defaultCamera']
        defLaser = None
        if 'defaultLaser' in self.dev.config:
            defLaser = self.dev.config['defaultLaser']

        devs = dm.listDevices()
        for d in devs:
            self.ui.laserCombo.addItem(d)
            if d == defLaser:
                self.ui.laserCombo.setCurrentIndex(self.ui.laserCombo.count()-1)

        mods = dm.listModules()
        for m in mods:
            self.ui.cameraCombo.addItem(m)
            mod = dm.getModule(m)
            if 'camDev' in mod.config and mod.config['camDev'] == defCam:
                self.ui.cameraCombo.setCurrentIndex(self.ui.cameraCombo.count()-1)
              
        ## Create state group for saving/restoring state
        self.stateGroup = WidgetGroup([
            (self.ui.cameraCombo,),
            (self.ui.laserCombo,),
            (self.ui.minTimeSpin, 'minTime'),
            (self.ui.minDistSpin, 'minDist', 1e6)
        ])
        self.stateGroup.setState({'minTime': 10, 'minDist': 300e-6})

        QtCore.QObject.connect(self.ui.addPointBtn, QtCore.SIGNAL('clicked()'), self.addPoint)
        QtCore.QObject.connect(self.ui.addGridBtn, QtCore.SIGNAL('clicked()'), self.addGrid)

    def saveState(self):
        return self.stateGroup.state()
        
    def restoreState(self, state):
        self.stateGroup.setState(state)
        pass
        
    def listSequence(self):
        return []
        
    def generateProtocol(self, params=None):
        return {}
        
    def handleResult(self, result, params):
        pass

    def addPoint(self):
        pt = TargetPoint([0,0], 200e-6)
        camMod = self.cameraModule()
        p = [-100e-6,-100e-6]
        s = [1,1]
        z = 1000
        camMod.ui.addItem(pt, p, s, z)

    def addGrid(self):
        pt = TargetGrid([0,0], [200e-6, 200e-6])
        camMod = self.cameraModule()
        p = [-100e-6,-100e-6]
        s = [1,1]
        z = 1000
        camMod.ui.addItem(pt, p, s, z)        

    def cameraModule(self):
        modName = str(self.ui.cameraCombo.currentText())
        return getManager().getModule(modName)
    
    def cameraPos(self):
        pass
    


class TargetPoint(EllipseROI):
    def __init__(self, pos, radius, **args):
        ROI.__init__(self, pos, [2*radius] * 2, **args)
        self.aspectLocked = True

class TargetGrid(ROI):
    def __init__(self, pos, size):
        ROI.__init__(self, pos=pos, size=size)
        self.addScaleHandle([0, 0], [1, 1])
        self.addScaleHandle([1, 1], [0, 0])
        self.addRotateHandle([0, 1], [0.5, 0.5])
        self.addRotateHandle([1, 0], [0.5, 0.5])


