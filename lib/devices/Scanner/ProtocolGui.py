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
        self.targets = None
        self.items = {}
        self.nextId = 0

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
        QtCore.QObject.connect(self.ui.deleteBtn, QtCore.SIGNAL('clicked()'), self.delete)
        QtCore.QObject.connect(self.ui.deleteAllBtn, QtCore.SIGNAL('clicked()'), self.deleteAll)
        QtCore.QObject.connect(self.ui.itemList, QtCore.SIGNAL('itemClicked(QListWidgetItem*)'), self.itemClicked)
        QtCore.QObject.connect(self.ui.itemList, QtCore.SIGNAL('currentItemChanged(QListWidgetItem*,QListWidgetItem*)'), self.itemSelected)
        QtCore.QObject.connect(self.ui.displayCheck, QtCore.SIGNAL('toggled(bool)'), self.showInterface)


        self.testTarget = TargetPoint([0,0], self.pointSize())
        self.testTarget.setPen(QtGui.QPen(QtGui.QColor(255, 200, 200)))
        camMod = self.cameraModule()
        camMod.ui.addItem(self.testTarget, None, [1,1], 1010)

    def showInterface(self, b):
        for k in self.items:
            if self.listItem(k).checkState() == QtCore.Qt.Checked:
                self.items[k].setVisible(b)
        self.testTarget.setVisible(b)

    def listItem(self, name):
        return self.ui.itemList.findItems(name, QtCore.Qt.MatchExactly)[0]

    def pointSize(self):
        cam = self.cameraModule().config['camDev']
        laser = str(self.ui.laserCombo.currentText())
        cal = self.dev.getCalibration(cam, laser)
        return cal['spot'][1]
        
    def cameraModule(self):
        modName = str(self.ui.cameraCombo.currentText())
        return getManager().getModule(modName)
        
    def calibrationChanged(self):
        pass

    def saveState(self):
        return self.stateGroup.state()
        
    def restoreState(self, state):
        self.stateGroup.setState(state)
        pass
        
    def listSequence(self):
        items = self.activeItems()
        targets = 0
        for i in items:
            targets += len(i.listPoints())
        if targets > 0:
            return {'targets': targets}
        else:
            return {}
        
    def generateProtocol(self, params=None):
        if params is None or 'target' not in params:
            target = self.testTarget.listPoints()[0]
        else:
            if self.targets is None:
                self.generateTargets()
            target = self.targets[params['target']]
            
        return {'position': target, 'camera': self.cameraModule().config['camDev'], 'laser': str(self.ui.laserCombo.currentText())}
        
    def handleResult(self, result, params):
        pass

    def addPoint(self):
        pt = TargetPoint([0,0], self.pointSize())
        self.addItem(pt, 'Point')

    def addGrid(self):
        s = self.pointSize()
        pt = TargetGrid([0,0], [s*4, s*4], s)
        self.addItem(pt, 'Grid')

    def addItem(self, item, name):
        name = name + str(self.nextId)
        item.name = name
        self.items[name] = item
        listitem = QtGui.QListWidgetItem(name)
        listitem.setCheckState(QtCore.Qt.Checked)
        self.ui.itemList.addItem(listitem)
        self.nextId += 1
        self.updateItemColor(listitem)
        camMod = self.cameraModule()
        camMod.ui.addItem(item, None, [1,1], 1000)
        item.connect(QtCore.SIGNAL('regionChangeFinished'), self.itemMoved)
        item.connect(QtCore.SIGNAL('pointsChanged'), self.itemChanged)
        self.itemChanged(item)

    def addTarget(self, t, name):
        self.sequenceChanged()

    def removeTarget(self, name):
        pass
    
    def delete(self):
        row = self.ui.itemList.currentRow()
        item = self.ui.itemList.takeItem(row)
        name = str(item.text())
        i = self.items[name]
        self.removeItemPoints(i)
        i.scene().removeItem(i)
        del self.items[name]
        self.sequenceChanged()

    def deleteAll(self):
        self.ui.itemList.clear()
        for k in self.items:
            i = self.items[k]
            i.scene().removeItem(i)
            self.removeItemPoints(i)
        self.items = {}
        self.sequenceChanged()
        
    def itemClicked(self, item):
        name = str(item.text())
        i = self.items[name]
        if item.checkState() == QtCore.Qt.Checked and self.ui.displayCheck.isChecked():
            i.show()
        else:
            i.hide()
        
        #self.updateItemColor(item)
        self.sequenceChanged()
        
    def itemSelected(self, item, prev):
        self.updateItemColor(item)
        self.updateItemColor(prev)
        
    def updateItemColor(self, item):
        if item is None:
            return
        if item is self.ui.itemList.currentItem():
            color = QtGui.QColor(255, 255, 200)
        else:
            color = QtGui.QColor(100, 100, 100)
        name = str(item.text())
        self.items[name].setPen(QtGui.QPen(color))

    def itemMoved(self, item):
        self.targets = None

    def itemChanged(self, item):
        self.targets = None
        self.sequenceChanged()
    
    def sequenceChanged(self):
        self.emit(QtCore.SIGNAL('sequenceChanged'), self.dev.name)

    def generateTargets(self):
        items = self.activeItems()
        self.targets = []
        for i in items:
            pts = i.listPoints()
            for p in pts:
                self.targets.append(p)
        ## Order targets here

    def activeItems(self):
        return [self.items[i] for i in self.items if self.listItem(i).checkState() == QtCore.Qt.Checked]

    def quit(self):
        self.deleteAll()
    
class TargetPoint(EllipseROI):
    def __init__(self, pos, radius, **args):
        ROI.__init__(self, pos, [radius] * 2, **args)
        self.aspectLocked = True
        
    def listPoints(self):
        p = self.mapToScene(self.boundingRect().center())
        return [(p.x(), p.y())]

class TargetGrid(ROI):
    def __init__(self, pos, size, ptSize):
        ROI.__init__(self, pos=pos, size=size)
        self.addScaleHandle([0, 0], [1, 1])
        self.addScaleHandle([1, 1], [0, 0])
        self.addRotateHandle([0, 1], [0.5, 0.5])
        self.addRotateHandle([1, 0], [0.5, 0.5])
        self.lastSize = self.state['size']
        self.connect(QtCore.SIGNAL('regionChanged'), self.rgnChanged)
        self.points = []
        self.pointSize = ptSize
        self.regeneratePoints()
        
    def setPointSize(self, size):
        self.pointSize = size
        self.regeneratePoints()
        
    def rgnChanged(self):
        if self.state['size'] != self.lastSize:
            self.regeneratePoints()
            self.lastSize = self.state['size']

    def regeneratePoints(self):
        self.points = []
        sq3 = 3. ** 0.5
        sepx = self.pointSize
        sepy = sq3 * self.pointSize
        self.generateGrid([self.pointSize*0.5, self.pointSize*0.5], [sepx, sepy])
        self.generateGrid([self.pointSize, .5 * self.pointSize * (1. + sq3)], [sepx, sepy])
        self.update()
        self.emit(QtCore.SIGNAL('pointsChanged'), self)
        
    def listPoints(self):
        pts = []
        for p in self.points:
            p1 = self.mapToScene(p[0], p[1])
            pts.append((p1.x(), p1.y()))
        return pts

    def generateGrid(self, start, sep):
        nx = 1 + int(((self.state['size'][0] - start[0]) - self.pointSize*0.5) / sep[0])
        ny = 1 + int(((self.state['size'][1] - start[1]) - self.pointSize*0.5) / sep[1])
        x = start[0]
        for i in range(nx):
            y = start[1]
            for j in range(ny):
                self.points.append((x, y))
                y += sep[1]
            x += sep[0]
        

    def paint(self, p, opt, widget):
        ROI.paint(self, p, opt, widget)
        ps2 = self.pointSize * 0.5
        p.setPen(self.pen)
        for pt in self.points:
            p.drawEllipse(QtCore.QRectF(pt[0] - ps2, pt[1] - ps2, self.pointSize, self.pointSize))
        
        


