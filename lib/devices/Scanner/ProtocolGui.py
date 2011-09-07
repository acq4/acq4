# -*- coding: utf-8 -*-
from ProtocolTemplate import Ui_Form
from lib.devices.Device import ProtocolGui
from PyQt4 import QtCore, QtGui
from lib.Manager import getManager
from WidgetGroup import WidgetGroup
import pyqtgraph.widgets as widgets
#from pyqtgraph.widgets import *
import random
import numpy as np
from debug import Profiler
import optimize ## for determining random scan patterns
import ForkedIterator, ProgressDialog
from SpinBox import SpinBox
from pyqtgraph.Point import *
from pyqtgraph.functions import mkPen

class ScannerProtoGui(ProtocolGui):
    
    #sigSequenceChanged = QtCore.Signal(object)  ## inherited from Device
    
    def __init__(self, dev, prot):
        ProtocolGui.__init__(self, dev, prot)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        #self.ui.programControlsLayout.setEnabled(False)
        dm = getManager()
        self.targets = None
        self.items = {}
        #self.occlusions = {}
        self.nextId = 0
        self.defaultGridSpacing = 1.0
        
        ## Populate module/device lists, auto-select based on device defaults 
        self.defCam = None
        if 'defaultCamera' in self.dev.config:
            self.defCam = self.dev.config['defaultCamera']
        defLaser = None
        if 'defaultLaser' in self.dev.config:
            defLaser = self.dev.config['defaultLaser']

        devs = dm.listDevices()
        for d in devs:
            self.ui.laserCombo.addItem(d)
            if d == defLaser:
                self.ui.laserCombo.setCurrentIndex(self.ui.laserCombo.count()-1)

        self.fillModuleList()
        
        ## Set up SpinBoxes
        self.ui.minTimeSpin.setOpts(dec=True, step=1, minStep=1e-3, siPrefix=True, suffix='s', bounds=[0, 50])
        self.ui.minDistSpin.setOpts(dec=True, step=1, minStep=1e-6, siPrefix=True, suffix='m', bounds=[0, 10e-3])
        self.ui.sizeSpin.setOpts(dec=True, step=1, minStep=1e-6, siPrefix=True, suffix='m', bounds=[0, 1e-3])
        ## Create state group for saving/restoring state
        self.stateGroup = WidgetGroup([
            (self.ui.cameraCombo,),
            (self.ui.laserCombo,),
            (self.ui.minTimeSpin, 'minTime'),
            (self.ui.minDistSpin, 'minDist'),
            (self.ui.simulateShutterCheck, 'simulateShutter'),
            (self.ui.sizeSpin, 'spotSize'),
#            (self.ui.packingSpin, 'packingDensity')  ## packing density should be suggested by device rather than loaded with protocol (I think..)
        ])
        self.stateGroup.setState({'minTime': 10, 'minDist': 500e-6, 'sizeSpin':100e-6})

        ## Note we use lambda functions for all these clicks to strip out the arg sent with the signal
        
        #self.prot.sigProtocolChanged.connect(self.protocolChanged)
        self.ui.addPointBtn.clicked.connect(lambda: self.addPoint())
        self.ui.addGridBtn.clicked.connect(lambda: self.addGrid())
        self.ui.addOcclusionBtn.clicked.connect(lambda: self.addOcclusion())
        self.ui.addProgramBtn.clicked.connect(lambda: self.addProgram())
        self.ui.addSpiralScanBtn.clicked.connect(lambda: self.addSpiral())
        self.ui.deleteBtn.clicked.connect(lambda: self.delete())
        self.ui.deleteAllBtn.clicked.connect(lambda: self.deleteAll())
        self.ui.itemTree.itemClicked.connect(self.itemToggled)
        self.ui.itemTree.currentItemChanged.connect(self.itemSelected)
        self.ui.itemTree.sigItemMoved.connect(self.treeItemMoved)
        self.ui.hideCheck.toggled.connect(self.showInterface)
        self.ui.hideMarkerBtn.clicked.connect(self.hideSpotMarker)
        self.ui.cameraCombo.currentIndexChanged.connect(self.camModChanged)
        #self.ui.packingSpin.valueChanged.connect(self.packingSpinChanged)
        self.ui.sizeFromCalibrationRadio.toggled.connect(self.updateSpotSizes)
        self.ui.sizeSpin.valueChanged.connect(self.sizeSpinEdited)
        self.ui.sizeSpin.valueChanged.connect(self.sizeSpinChanged)
        #QtCore.QObject.connect(self.ui.minTimeSpin, QtCore.SIGNAL('valueChanged(double)'), self.sequenceChanged)
        self.ui.minTimeSpin.valueChanged.connect(self.sequenceChanged)
        self.ui.minDistSpin.valueChanged.connect(self.sequenceChanged)
        self.ui.recomputeBtn.clicked.connect(self.recomputeClicked)
        dm.sigModulesChanged.connect(self.fillModuleList)

        #self.currentTargetMarker = QtGui.QGraphicsEllipseItem(0, 0, 1, 1)
        #pen = QtGui.QPen(QtGui.QBrush(QtGui.QColor(255, 255, 255)), 3.0)
        #pen.setCosmetic(True)
        #self.currentTargetMarker.setPen(pen)
        
        #self.currentTargetMarker.hide()
        
        self.testTarget = TargetPoint([0,0], 100e-6, host=self)
        self.testTarget.setPen(QtGui.QPen(QtGui.QColor(255, 200, 200)))
        self.spotMarker = TargetPoint([0,0], 100e-6, host=self)
        self.spotMarker.setPen(mkPen(color=(255,255,255), width = 2))
        self.updateSpotSizes()
        self.spotMarker.hide()
        
        #camMod = self.cameraModule()
        
        self.currentObjective = None
        self.currentScope = None
        self.currentCamMod = None
        self.camModChanged()

        
        ## load target list from device, allowing targets to persist across protocols
        oldTargetList = self.dev.getTargetList()
        self.ui.sizeSpin.setValue(oldTargetList[0])
        for k in oldTargetList[1].keys():
            t = oldTargetList[1][k]
            if t['type'] == 'point':
                pos = t['pos']
                self.addPoint(pos=pos,  name=k)
                #pt.setPos(pos)
            elif t['type'] == 'grid':
                self.addGrid(pos = t['pos'], size = t['size'], angle = t['angle'],  name=k, rebuildOpts = t )
                #gr.setPos(pos)
                #gr.setSize(size)
                #gr.setAngle(angle)
            elif t['type'] == 'occlusion':
                self.addOcclusion(points = t['points'], pos = t['pos'], name=k)
        for item in self.items.values():
            item.resetParents()
    #def protocolChanged(self, name, val):
        #if name == 'duration':
            #self.protDuration = val
        
        
    def fillModuleList(self):
        man = getManager()
        self.ui.cameraCombo.clear()
        mods = man.listModules()
        for m in mods:
            self.ui.cameraCombo.addItem(m)
            mod = man.getModule(m)
            try:
                if 'camDev' in mod.config and mod.config['camDev'] == self.defCam:
                    self.ui.cameraCombo.setCurrentIndex(self.ui.cameraCombo.count()-1)
            except (KeyError,AttributeError):
                continue
        
        
    def camModChanged(self):
        camDev = self.cameraDevice()
        camMod = self.cameraModule()
        if self.currentCamMod is not None:
            self.currentCamMod.ui.removeItem(self.testTarget)
            self.currentCamMod.ui.removeItem(self.spotMarker)
            #self.currentCamMod.ui.removeItem(self.currentTargetMarker)
            #QtCore.QObject.disconnect(self.currentCamMod.ui, QtCore.SIGNAL('cameraScaleChanged'), self.objectiveChanged)
            self.currentCamMod.ui.sigCameraScaleChanged.disconnect(self.objectiveChanged)
            
        if self.currentScope is not None:
            #QtCore.QObject.disconnect(self.currentScope, QtCore.SIGNAL('objectiveChanged'), self.objectiveChanged)
            self.currentScope.sigObjectiveChanged.disconnect(self.objectiveChanged)
            
        self.currentCamMod = camMod
        if camDev is None or camMod is None:
            self.currentScope = None
            return
        self.currentScope = camDev.getScopeDevice()
        self.currentCamMod = camMod
        #QtCore.QObject.connect(self.currentCamMod.ui, QtCore.SIGNAL('cameraScaleChanged'), self.objectiveChanged)
        self.currentCamMod.ui.sigCameraScaleChanged.connect(self.objectiveChanged)
        
        if self.currentScope is not None:
            #QtCore.QObject.connect(self.currentScope, QtCore.SIGNAL('objectiveChanged'), self.objectiveChanged)
            self.currentScope.sigObjectiveChanged.connect(self.objectiveChanged)
            
        camMod.ui.addItem(self.testTarget, None, [1,1], 1010)
        camMod.ui.addItem(self.spotMarker, None, [1,1], 1010)
        #camMod.ui.addItem(self.currentTargetMarker, None, [1,1], 1010)
        self.objectiveChanged()
        
        
    def objectiveChanged(self):
        camDev = self.cameraDevice()
        if camDev is None:
            return
        obj = camDev.getObjective()
        if self.currentObjective != obj:
            self.currentObjective = obj
            self.updateSpotSizes()
            for i in self.items.values():
                li = self.listItem(i.name)
                if i.objective == obj:
                    li.setCheckState(QtCore.Qt.Checked)
                else:
                    li.setCheckState(QtCore.Qt.Unchecked)
                self.itemToggled(li)
            #self.testTarget.setPointSize(self.pointSize()[0])
            self.testTarget.setPointSize()
            self.spotMarker.setPointSize()
            #self.cameraModule().ui.centerItem(self.testTarget)
        camMod = self.cameraModule()
        camMod.ui.removeItem(self.testTarget)
        camMod.ui.removeItem(self.spotMarker)
        camMod.ui.addItem(self.testTarget, None, [1,1], 1010)
        camMod.ui.addItem(self.spotMarker, None, [1,1], 1010)

    def sizeSpinChanged(self):
        #print "packingSpinChanged."
        #self.updateSpotSizes()
        self.dev.updateTargetDisplaySize(self.ui.sizeSpin.value())
        
        
    def sizeSpinEdited(self):
        self.ui.sizeCustomRadio.setChecked(True)
        self.updateSpotSizes()
        
      
    def updateSpotSizes(self):
        #size, displaySize = self.pointSize()
        ##pd = self.pointSize()[1]
        for i in self.items.values():
            i.setPointSize()
        self.testTarget.setPointSize()
        self.spotMarker.setPointSize()

    def showInterface(self, b):
        for k in self.items:
            if self.listItem(k).checkState() == QtCore.Qt.Checked:
                self.items[k].setVisible(not b)
        self.testTarget.setVisible(not b)

    def listItem(self, name):
        return self.ui.itemTree.findItems(name, QtCore.Qt.MatchRecursive)[0]

    def pointSize(self):
        #packing = self.ui.packingSpin.value()
        try:
            cam = self.cameraModule().config['camDev']
            laser = str(self.ui.laserCombo.currentText())
            cal = self.dev.getCalibration(cam, laser)
            ss = cal['spot'][1]
           
        except Exception, e:
            print "Could not find spot size from calibration."
            #logMsg("Could not find spot size from calibration.", msgType='error') ### This should turn into a HelpfulException.
            if isinstance(e[1], HelpfulException):
                e[1].prependInfo("Could not find spot size from calibration. ", exc=e, reasons=["Correct camera and/or laser device are not selected.", "There is no calibration file for selected camera and laser."])
            else:
                raise HelpfulException("Could not find spot size from calibration. ", exc=e, reasons=["Correct camera and/or laser device are not selected.", "There is no calibration file for selected camera and laser."])
            
        if self.ui.sizeFromCalibrationRadio.isChecked():
            displaySize = ss
            ## reconnecting before this to get around reload errors, breaks the disconnect
            self.ui.sizeSpin.valueChanged.disconnect(self.sizeSpinEdited)
            self.stateGroup.setState({'spotSize':ss})
            self.ui.sizeSpin.valueChanged.connect(self.sizeSpinEdited)
        elif self.ui.sizeCustomRadio.isChecked():
            displaySize = self.ui.sizeSpin.value()
        return (ss, displaySize)
        #return (0.0001, packing)
        
    def cameraModule(self):
        modName = str(self.ui.cameraCombo.currentText())
        if modName == '':
            return None
        mod = getManager().getModule(modName)
        if not hasattr(mod.ui, 'addItem'): ## silly. should check to see if this is a camera 
            return None
        return mod
        
    def cameraDevice(self):
        mod = self.cameraModule()
        if mod is None:
            return None
        if 'camDev' not in mod.config:
            return None
        cam = mod.config['camDev']
        return getManager().getDevice(cam)
        
    def calibrationChanged(self):
        pass

    def saveState(self):
        return self.stateGroup.state()
        
    def restoreState(self, state):
        self.stateGroup.setState(state)
        pass
        
    def listSequence(self):
        items = self.activeItems()
        targets = self.getTargetList()
        if targets > 0:
            return {'targets': targets}
        else:
            return {}
        
    def generateProtocol(self, params=None):
        if self.cameraModule() is None:
            raise Exception('No camera module selected, can not build protocol.')
            
        if params is None or 'targets' not in params:
            target = self.testTarget.listPoints()[0]
            delay = 0
        else:
            if self.targets is None:
                self.generateTargets()
            #print "targets:", len(self.targets), params['targets']
            (target, delay) = self.targets[params['targets']]
            
        prot = {
            'position': target, 
            'minWaitTime': delay,
            'camera': self.cameraModule().config['camDev'], 
            'laser': str(self.ui.laserCombo.currentText()),
            'simulateShutter': self.ui.simulateShutterCheck.isChecked(),
            'duration': self.prot.getParam('duration')
        }
        return prot
    
    def hideSpotMarker(self):
        self.spotMarker.hide()
        
        
    def handleResult(self, result, params):
        if not self.spotMarker.isVisible():
            self.spotMarker.show()
        pos = result['position']
        ss = result['spotSize']
        self.spotMarker.setPos((pos[0]-ss*0.5, pos[1]-ss*0.5))
        #print 'handleResult'
    
    def addSpiral(self, pos=None, name=None):
        autoName = False
        if name is None:
            name = 'Point'
            autoName = True
        autoPos = False
        if pos is None:
            pos = [0,0]
            autoPos = True
        pt = widgets.SpiralROI(pos)
        self.addItem(pt, name,  autoPos,  autoName)
        return pt

    def addPoint(self, pos=None,  name=None):
        autoName = False
        if name is None:
            name = 'Point'
            autoName = True
        autoPos = False
        if pos is None:
            pos = [0,0]
            autoPos = True
        else:
            s = self.pointSize()[0]
            pos = [pos[i] - s/2.0 for i in [0, 1]]
        pt = TargetPoint(pos, self.pointSize()[0])
        self.addItem(pt, name,  autoPos,  autoName)
        return pt
        
    def addGrid(self, pos=None, size=None, angle=0,  name=None, rebuildOpts = {}):
        autoName = False
        if name is None:
            name = 'Grid'
            autoName = True
        ptSize, dispSize = self.pointSize()
        autoPos = False
        if pos is None:
            pos = [0,0]
            autoPos = True
        if size is None:
            size = [ptSize*4, ptSize*4]
        pt = TargetGrid(pos, size, ptSize, self.defaultGridSpacing, angle, rebuildOpts=rebuildOpts)
        self.addItem(pt, name,  autoPos,  autoName)
        return pt
    
    def addOcclusion(self, pos=None, points=None, name=None):
        auto = False
        if name is None:
            name = 'Occlusion'
            auto = True
        if points is None:
            s = self.pointSize()[0]
            points = ([0,0], [0,s*3], [s*3,0])
        if pos is None:
            pos = [0,0]
        item =TargetOcclusion(points, pos=pos)
        self.addItem(item, name, autoName=auto, autoPosition=auto)
        return item
        
    def addProgram(self, name=None): 
        pass
        #camMod = self.cameraModule()
        #if camMod is None:
            #return False
        #self.ui.programControlsLayout.setEnabled(True)
        #item = TargetProgram()
        #if name is None:
            #name = 'Program' + str(self.nextId)
        #self.nextId += 1 
        #item.name = name
        #item.objective = self.currentObjective
        #self.items[name] = item
        #treeitem = QtGui.QTreeWidgetItem(QtCore.QStringList(name))
        #treeitem.setCheckState(0, QtCore.Qt.Checked)
        #self.ui.itemTree.addTopLevelItem(treeitem)
        #self.updateItemColor(treeitem)
        #camMod.ui.addItem(item.origin, None, [1,1], 1000)
        #item.connect(QtCore.SIGNAL('regionChangeFinished'), self.itemMoved)
        #item.connect(QtCore.SIGNAL('regionChanged'), self.getTargetList)
        #item.connect(QtCore.SIGNAL('pointsChanged'), self.itemChanged)
        #self.itemChanged(item)
        #self.updateDeviceTargetList(item)
        
        

    def addItem(self, item, name0,  autoPosition=True,  autoName=True):
        camMod = self.cameraModule()
        if camMod is None:
            return False
        if autoName:
            name = name0 + str(self.nextId)
            while name in self.items.keys():
                self.nextId += 1
                name = name0 + str(self.nextId) 
        else:
            name=name0
        item.name = name
        item.objective = self.currentObjective
        self.items[name] = item
        #if isinstance(item, TargetOcclusion):
            #self.occlusions[name] = item
        item.treeItem = QtGui.QTreeWidgetItem(QtCore.QStringList(name))
        
        item.treeItem.setCheckState(0, QtCore.Qt.Checked)
        self.ui.itemTree.addTopLevelItem(item.treeItem)
        
        item.updateInit(self)
        self.nextId += 1
        self.updateItemColor(item.treeItem)
        if autoPosition:
            pos = None
        else:
            pos = item.stateCopy()['pos'] 
        camMod.ui.addItem(item, pos, [1, 1], 1000)
        
        item.sigRegionChangeFinished.connect(self.itemMoved)
        item.sigRegionChanged.connect(self.getTargetList)
        item.sigPointsChanged.connect(self.itemChanged)
        
        
        self.itemChanged(item)
        self.updateDeviceTargetList(item)

    def addTarget(self, t, name):
        self.sequenceChanged()

    def removeTarget(self, name):
        pass
    
    def delete(self):
        item = self.ui.itemTree.currentItem()
        parent = item.parent()
        if item.childCount() > 0:
            for i in range(item.childCount()):
                child = item.child(i)
                self.ui.itemTree.prepareMove(child)
                item.removeChild(child)
                child.graphicsItem.setParentItem(parent)
                child.graphicsItem.updateFamily()
                if parent is not None:
                    parent.addChild(child)
                    self.ui.itemTree.recoverMove(child)
                else:
                    self.ui.itemTree.addTopLevelItem(child)
                    self.ui.itemTree.recoverMove(child)
                    
        if parent == None:
            item = self.ui.itemTree.takeTopLevelItem(self.ui.itemTree.indexOfTopLevelItem(item))
        else:
            item = parent.takeChild(parent.indexOfChild(item))
        #item = self.ui.itemTree.takeItem(row)
        if item is None:
            return
        name = str(item.text(0))
        self.dev.updateTarget(name, None)  ## inform the device that this target is no more
        i = self.items[name]
        #self.removeItemPoints(i)
        i.scene().removeItem(i)
        del self.items[name]
        #self.occlusions.get(name)
        self.sequenceChanged()

    def deleteAll(self, clearHistory=True):
        self.ui.itemTree.clear()
        for k in self.items:
            if clearHistory == True:
                self.dev.updateTarget(k, None)  ## inform the device that this target is no more
            i = self.items[k]
            i.scene().removeItem(i)
            #self.removeItemPoints(i)
        self.items = {}
        #self.occlusions = {}
        self.sequenceChanged()
        
    def treeItemMoved(self, item, parent, index):
        if parent != self.ui.itemTree.invisibleRootItem():
            g = item.graphicsItem
            newPos = parent.graphicsItem.mapFromScene(g.scenePos())
            g.setParentItem(parent.graphicsItem)
            g.setPos(newPos)
        else:
            item.graphicsItem.setParentItem(None)
        item.graphicsItem.updateFamily()
        #print "tree Item Moved"
        
        
    def itemToggled(self, item, column):
        name = str(item.text(0))
        i = self.items[name]
        if item.checkState(0) == QtCore.Qt.Checked and not self.ui.hideCheck.isChecked():
            i.setOpacity(1.0)
            for h in i.handles:
                h['item'].setOpacity(1.0)
            self.cameraModule().ui.update()
        else:
            i.setOpacity(0.0)
            self.cameraModule().ui.update()
            for h in i.handles:
                h['item'].setOpacity(0.0)
            
        #self.updateItemColor(item)
        self.sequenceChanged()
        
    def itemSelected(self, item, prev):
        self.updateItemColor(item)
        self.updateItemColor(prev)
        
    def updateItemColor(self, item):
        if item is None:
            return
        if item is self.ui.itemTree.currentItem():
            color = QtGui.QColor(255, 255, 200)
        else:
            color = QtGui.QColor(200, 255, 100)
        name = str(item.text(0))
        self.items[name].setPen(QtGui.QPen(color))

    def itemMoved(self, item):
        self.targets = None
        self.updateDeviceTargetList(item)
        self.sequenceChanged()
        

    def itemChanged(self, item):
        self.targets = None
        self.sequenceChanged()
        self.updateDeviceTargetList(item)
    
    def updateDeviceTargetList(self, item):
        """For keeping track of items outside of an individual scanner device. Allows multiple protocols to access the same items."""
        name = str(item.name)
        state = item.stateCopy()
        if isinstance(item, TargetPoint):
            pos = state['pos']
            pos[0] += state['size'][0]/2.0
            pos[1] += state['size'][1]/2.0
            info = {'type': 'point', 'pos':pos }
        elif isinstance(item, TargetGrid):
            state['type'] = 'grid'
            info = state
        elif isinstance(item, TargetOcclusion):
            info = {'type':'occlusion', 'pos':item.pos(), 'points': item.listPoints()}
        elif isinstance(item, widgets.SpiralROI):
            info = {'type': 'spiral', 'pos': item.pos()}
        
        self.dev.updateTarget(name, info)
    
    def getTargetList(self):  ## should probably do some caching here.
        items = self.activeItems()
        locations = []
        occArea = QtGui.QPainterPath()
        for i in items:
            if isinstance(i, TargetOcclusion):
                occArea |= i.mapToScene(i.shape())
            
        for i in items:
            if isinstance(i, TargetOcclusion) or isinstance(i, TargetProgram) or isinstance(i, widgets.SpiralROI):
                continue
            pts = i.listPoints()
            #for x in self.occlusions.keys():  ##can we just join the occlusion areas together?
                #area = self.occlusions[x].mapToScene(self.occlusions[x].shape())
            for j in range(len(pts)):
                p=pts[j]
                point = QtCore.QPointF(p[0], p[1])
                if occArea.contains(point):
                    i.setTargetPen(j, QtGui.QPen(QtGui.QColor(0,0,0,160)))
                else:
                    locations.append(p)
                    i.setTargetPen(j, None)
        return locations

    
    def sequenceChanged(self):
        self.targets = None
        #self.emit(QtCore.SIGNAL('sequenceChanged'), self.dev.name)
        self.sigSequenceChanged.emit(self.dev.name)

    def recomputeClicked(self):
        try:
            self.ui.recomputeBtn.setEnabled(False)
            self.generateTargets()
        finally:
            self.ui.recomputeBtn.setEnabled(True)

    def generateTargets(self):
        #items = self.activeItems()
        #prof= Profiler('ScanerProtoGui.generateTargets()')
        self.targets = []
        locations = self.getTargetList()
        
        bestTime = None
        bestSolution = None

        nTries = np.clip(int(10 - len(locations)/20), 1, 10)
        
        ## About to compute order/timing of targets; display a progress dialog
        #prof.mark('setup')
        #progressDlg = QtGui.QProgressDialog("Computing pseudo-optimal target sequence...", 0, 1000)
        #progressDlg.setWindowModality(QtCore.Qt.WindowModal)
        #progressDlg.setMinimumDuration(500)
        #prof.mark('progressDlg')
        deadTime = self.prot.getParam('duration')

        state = self.stateGroup.state()
        minTime = state['minTime']
        minDist = state['minDist']

        #try:
        with ProgressDialog.ProgressDialog("Computing random target sequence...", 0, 1000, busyCursor=True) as dlg:
            #times=[]
            for i in range(nTries):
                #prof.mark('attempt: %i' %i)
                
                ## Run in a remote process for a little speedup
                for n, m in optimize.opt2(locations, minTime, minDist, deadTime, greed=1.0):
                #proc = ForkedIterator.ForkedIterator(optimize.opt2, locations, minTime, minDist, deadTime, greed=1.0)
                #for n,m in proc:
                    ## we can update the progress dialog here.
                    if m is None:
                        solution = n
                    else:
                        prg = int(((i/float(nTries)) + ((n/float(m))/float(nTries))) * 1000)
                        #print n,m, prg
                        dlg.setValue(prg)
                        #print i
                        #QtGui.QApplication.processEvents()
                        if dlg.wasCanceled():
                            raise Exception("Target sequence computation canceled by user.")
                #solution = self.findSolution(locations)
                #prof.mark('foundSolution')
                time = sum([l[1] for l in solution])
                #times.append(time)
                if bestTime is None or time < bestTime:
                    #print "  new best time:", time
                    bestTime = time
                    bestSolution = solution[:]
                    #print "new best:", len(bestSolution), minTime
                #prof.mark('check time')
        #except:
            #raise
        #finally:
            ## close progress dialog no matter what happens
            #print "Times: ", times
            #progressDlg.setValue(1000)
        
        self.targets = bestSolution
        #print "Solution:"
        #for t in self.targets:
            #print "  ", t
        self.ui.timeLabel.setText('Total time: %0.1f sec'% bestTime)
        #prof.mark('Done.')
        #prof.finish()
        
    #def costFn(self, dist):
        #### Takes distance^2 as argument!
        #state = self.stateGroup.state()
        #minTime = state['minTime']
        #minDist = state['minDist']
        #A = 2 * minTime / minDist**2
        #return np.where(
            #dist < minDist, 
            #np.where(
                #dist < minDist/2., 
                #minTime - A * dist**2, 
                #A * (dist-minDist)**2
            #), 
            #0
        #)

    def activeItems(self):
        return [self.items[i] for i in self.items if self.listItem(i).checkState(0) == QtCore.Qt.Checked]

    
    def taskStarted(self, params):
        """Task has started; color the current and previous targets"""
        if 'targets' not in params:
            return
        #t = params['targets']
        #self.currentTargetMarker.setRect
    
    def quit(self):
        #print "scanner dock quit"
        self.deleteAll(clearHistory = False)
        s = self.testTarget.scene()
        if s is not None:
            self.testTarget.scene().removeItem(self.testTarget)
            self.spotMarker.scene().removeItem(self.spotMarker)
        #QtCore.QObject.disconnect(getManager(), QtCore.SIGNAL('modulesChanged'), self.fillModuleList)
        try:
            getManager().sigModulesChanged.disconnect(self.fillModuleList)
        except TypeError:
            pass
            
        if self.currentCamMod is not None:
            try:
                #QtCore.QObject.disconnect(self.currentCamMod.ui, QtCore.SIGNAL('cameraScaleChanged'), self.objectiveChanged)
                self.currentCamMod.ui.sigCameraScaleChanged.disconnect(self.objectiveChanged)
            except:
                pass
        if self.currentScope is not None:
            try:
                #QtCore.QObject.disconnect(self.currentScope, QtCore.SIGNAL('objectiveChanged'), self.objectiveChanged)
                self.currentScope.sigObjectiveChanged.disconnect(self.objectiveChanged)
            except:
                pass
        #print "  ..done."
    
class TargetPoint(widgets.EllipseROI):
    
    sigPointsChanged = QtCore.Signal(object)
    
    def __init__(self, pos, radius, **args):
        if 'host' in args:
            self.host = args.pop('host')
        widgets.ROI.__init__(self, pos, [radius] * 2, **args)
        self.aspectLocked = True
        self.overPen = None
        self.underPen = self.pen
        self.treeItem = None
        self.setFlag(QtGui.QGraphicsItem.ItemIgnoresParentOpacity, True)
        #self.host = args.get('host', None)
        self.rebuildOpts = args.get('rebuildOpts', {})
        
        
    def updateInit(self, host):
        self.treeItem.graphicsItem = self
        self.treeItem.setText(3, "1")
        self.host = host
        
    def updateFamily(self):
        pass
    
    def resetParents(self):
        """For use when rebuilding scanner targets from the deviceTargetList"""
        if self.rebuildOpts.get('parentName', None) is not None:
            tw = self.treeItem.treeWidget()
            parent = tw.findItems(self.rebuildOpts['parentName'], QtCore.Qt.MatchRecursive)[0]
            tw.prepareMove(self.treeItem)
            tw.invisibleRootItem().removeChild(self.treeItem)
            parent.insertChild(0, self.treeItem)
            tw.recoverMove(self.treeItem)
            parent.setExpanded(True)
            self.host.treeItemMoved(self.treeItem, parent, 0)
        
    def setPointSize(self):
        size, displaySize = self.host.pointSize()
        if self.treeItem is None: ## then you're the target point and should be the size from calibration
            s = size / self.state['size'][0]
            self.scale(s, [0.5, 0.5])
        else:
            s = displaySize / self.state['size'][0]
            self.scale(s, [0.5, 0.5])
        
    def listPoints(self):
        p = self.mapToScene(self.boundingRect().center())
        return [(p.x(), p.y())]
        
    def setPen(self, pen):
        self.underPen = pen
        widgets.EllipseROI.setPen(self, pen)
    
    def setTargetPen(self, index, pen):
        self.overPen = pen
        if pen is None:
            pen = self.underPen
        widgets.EllipseROI.setPen(self, pen)
        
    def stateCopy(self):
        sc = widgets.ROI.stateCopy(self)
        #sc['displaySize'] = self.displaySize
        return sc
        

class TargetGrid(widgets.ROI):
    
    sigPointsChanged = QtCore.Signal(object)
    
    def __init__(self, pos, size, ptSize, pd, angle, rebuildOpts = {}):
        ### These need to be initialized before the ROI is initialized because they are included in stateCopy(), which is called by ROI initialization.
        self.gridSpacingSpin = SpinBox(step=0.1)
        self.gridSpacingSpin.setValue(pd)
        self.gridPacking = self.gridSpacingSpin.value()
        self.gridLayoutCombo = QtGui.QComboBox()
        self.gridLayoutCombo.addItems(["Hexagonal", "Square"])
        self.gridSpacingSpin.valueChanged.connect(self.updateGridPacking)
        self.gridLayoutCombo.currentIndexChanged.connect(self.regeneratePoints)
        self.treeItem = None ## will become a QTreeWidgetItem when ScannerProtoGui runs addItem()
        
        widgets.ROI.__init__(self, pos=pos, size=size, angle=angle)
        self.addScaleHandle([0, 0], [1, 1])
        self.addScaleHandle([1, 1], [0, 0])
        self.addRotateHandle([0, 1], [0.5, 0.5])
        self.addRotateHandle([1, 0], [0.5, 0.5])
        self.lastSize = self.state['size']
        #self.connect(QtCore.SIGNAL('regionChanged'), self.rgnChanged)
        self.sigRegionChanged.connect(self.rgnChanged)
        self.points = []
        self.pens = []
        self.pointSize = ptSize
        self.pointDisplaySize = self.pointSize
        self.setFlag(QtGui.QGraphicsItem.ItemIgnoresParentOpacity, True)
        
        
        ## cache is not working in qt 4.7
        self.setCacheMode(QtGui.QGraphicsItem.DeviceCoordinateCache)
        self.regeneratePoints()
        self.rebuildOpts = rebuildOpts
        
    def updateInit(self, host):
        self.treeItem.graphicsItem = self ## make grid accessible from tree
        self.treeItem.treeWidget().setItemWidget(self.treeItem, 1, self.gridSpacingSpin)
        self.treeItem.treeWidget().setItemWidget(self.treeItem, 2, self.gridLayoutCombo)
        self.treeItem.setText(3, "14")
        self.host = host
        self.pointSize, self.pointDisplaySize = self.host.pointSize()
        if len(self.rebuildOpts) > 0:
            self.gridSpacingSpin.setValue(self.rebuildOpts.get('gridPacking', self.gridPacking))
            layout = self.rebuildOpts.get('gridLayout', "Hexagonal")
            if layout == "Hexagonal":
                self.gridLayoutCombo.setCurrentIndex(0)
            elif layout == "Square":
                self.gridLayoutCombo.setCurrentIndex(1)       
        self.host.updateDeviceTargetList(self)
    
    def resetParents(self):
        """For use when rebuilding scanner targets from the deviceTargetList"""
        if self.rebuildOpts.get('parentName', None) is not None:
            tw = self.treeItem.treeWidget()
            parent = tw.findItems(self.rebuildOpts['parentName'], QtCore.Qt.MatchRecursive)[0]
            tw.prepareMove(self.treeItem)
            tw.invisibleRootItem().removeChild(self.treeItem)
            parent.insertChild(0, self.treeItem)
            tw.recoverMove(self.treeItem)
            parent.setExpanded(True)
            self.host.treeItemMoved(self.treeItem, parent, 0)
            
           
            
    def updateFamily(self):
        if self.treeItem.parent() is not None:
            self.gridSpacingSpin.setEnabled(False)
            self.gridLayoutCombo.setEnabled(False)
            self.parentGridSpacingSpin = self.treeItem.treeWidget().itemWidget(self.treeItem.parent(), 1)
            self.parentGridSpacingSpin.valueChanged.connect(self.parentValueChanged)
            self.parentGridLayoutCombo = self.treeItem.treeWidget().itemWidget(self.treeItem.parent(), 2)
            self.parentGridLayoutCombo.currentIndexChanged.connect(self.parentValueChanged)
            self.translateSnap = True
            self.rotateAllowed = False
            self.setAngle(0)
            #self.setAngle(self.treeItem.parent().graphicsItem.stateCopy()['angle'])
            self.parentValueChanged()
        if self.treeItem.parent() is None:
            self.gridSpacingSpin.setEnabled(True)
            self.gridLayoutCombo.setEnabled(True)
            self.translateSnap = False
            self.rotateAllowed = True
        self.host.updateDeviceTargetList(self)
        #self.updateSnapSize()
        
    def parentValueChanged(self):
        if self.treeItem.parent() is not None:
            self.gridSpacingSpin.setValue(self.parentGridSpacingSpin.value())
            self.gridLayoutCombo.setCurrentIndex(self.parentGridLayoutCombo.currentIndex())
            
        
    def updateGridPacking(self):
        self.gridPacking = self.gridSpacingSpin.value()
        #self.updateSnapSize()
        self.regeneratePoints()
        
    #def updateSnapSize(self):
        #self.snapSizeX = self.pointSize * self.gridPacking
        #if self.gridLayoutCombo.currentText() == "Square":
            #self.snapSizeY = self.snapSizeX
        #elif self.gridLayoutCombo.currentText() == "Hexagonal":
            #self.snapSizeY = 0.5 * self.snapSizeX * 3.**0.5
        
    def setPointSize(self):
        size, displaySize = self.host.pointSize()
        self.pointSize = size
        self.pointDisplaySize = displaySize
        self.regeneratePoints()
        
    def rgnChanged(self):
        if self.state['size'] != self.lastSize:
            self.regeneratePoints()
            self.lastSize = self.state['size']
            
    def getSnapPosition(self, pos, snap=None):
        ## Given that pos has been requested, return the nearest snap-to position
        ## optionally, snap may be passed in to specify a rectangular snap grid.
        ## override this function for more interesting snap functionality..
        
        if snap is None:
            if self.snapSize is None:
                return pos
        layout = self.gridLayoutCombo.currentText()
        
        if layout == 'Square':
            snap = Point(self.pointSize * self.gridPacking, self.pointSize*self.gridPacking)
            w = round(pos[0] / snap[0]) * snap[0]
            h = round(pos[1] / snap[1]) * snap[1]
            return Point(w, h)
        
        elif layout == 'Hexagonal':
            snap1 = Point(self.pointSize*self.gridPacking, self.pointSize*self.gridPacking*3.0**0.5)
            dx = 0.5*snap1[0]
            dy = 0.5*snap1[1]
            w1 = round(pos[0] / snap1[0]) * snap1[0]
            h1 = round(pos[1] / snap1[1]) * snap1[1]
            w2 = round((pos[0]-dx) / snap1[0]) * snap1[0] + dx
            h2 = round((pos[1]-dy) / snap1[1]) * snap1[1] + dy
            #snap2 = snap1 + Point(snap1[0]*0.5, snap1[1]/2)
            #w2 = round(pos[0] / snap2[0]) * snap2[0]
            #h2 = round(pos[1] / snap2[1]) * snap2[1] 
            if (Point(w1, h1)-pos).length() < (Point(w2,h2) - pos).length():
                return Point(w1, h1)
            else:
                return Point(w2, h2)
        

    def regeneratePoints(self):
        if self.treeItem is None:
            layout = "Hexagonal"
        else:
            layout = self.gridLayoutCombo.currentText()
        self.points = []
        self.pens = []
        sq3 = 3. ** 0.5
        sepx = self.pointSize * self.gridPacking
        sepy = sq3 * sepx

        if layout == "Hexagonal":
            self.generateGrid([self.pointSize*0.5, self.pointSize*0.5], [sepx, sepy])  ## make every other row of the grid starting from top
            self.generateGrid([self.pointSize*0.5+0.5*sepx, 0.5*self.pointSize + 0.5*sepy ], [sepx, sepy]) ### make every other row of the grid starting with 2nd row
        elif layout == "Square":
            self.generateGrid([self.pointSize*0.5, self.pointSize*0.5], [sepx, sepx]) ## points in x and y dimensions have same separation, so use same value.
      
        self.update()
        #self.emit(QtCore.SIGNAL('pointsChanged'), self)
        if self.treeItem is not None:
            self.treeItem.setText(3, str(len(self.points)))
        self.sigPointsChanged.emit(self)
        
        
    def listPoints(self):
        pts = []
        for p in self.points:
            p1 = self.mapToScene(p[0], p[1])
            pts.append((p1.x(), p1.y()))
        
        return pts

    def setTargetPen(self, index, pen):
        self.pens[index] = pen
        self.update()

    def generateGrid(self, start, sep):
        nx = 1 + int(((self.state['size'][0] - start[0]) - self.pointSize*0.5) / sep[0])
        ny = 1 + int(((self.state['size'][1] - start[1]) - self.pointSize*0.5) / sep[1])
        x = start[0]
        for i in range(nx):
            y = start[1]
            for j in range(ny):
                self.points.append((x, y))
                self.pens.append(None)
                y += sep[1]
            x += sep[0]
        

    def paint(self, p, opt, widget):
        widgets.ROI.paint(self, p, opt, widget)
        ps2 = self.pointSize * 0.5
        radius = self.pointDisplaySize*0.5
        #ps2 = self.pointSize * 0.5 * self.gridPacking
        #p.setPen(self.pen)
        p.scale(self.pointSize, self.pointSize) ## do scaling here because otherwise we end up with squares instead of circles (GL bug)
        for i in range(len(self.points)):
            pt = self.points[i]
            if self.pens[i] != None:
                p.setPen(self.pens[i])
            else:
                p.setPen(self.pen)
            #p.drawEllipse(QtCore.QRectF((pt[0] - ps2)/self.pointSize, (pt[1] - ps2)/self.pointSize, 1, 1))
            p.drawEllipse(QtCore.QPointF(pt[0]/self.pointSize, pt[1]/self.pointSize), radius/self.pointSize, radius/self.pointSize)
            
    def stateCopy(self):
        sc = widgets.ROI.stateCopy(self)
        sc['gridPacking'] = self.gridPacking
        sc['gridLayout'] = str(self.gridLayoutCombo.currentText())
        if self.treeItem is not None:
            if self.treeItem.parent() is None:
                sc['parentName'] = None
            else:
                sc['parentName'] = self.treeItem.parent().text(0)
        return sc
        #sc['displaySize'] = self.displaySize
        
class TargetOcclusion(widgets.PolygonROI):
    
    
    sigPointsChanged = QtCore.Signal(object)
    
    def __init__(self, points, pos=None):
        widgets.PolygonROI.__init__(self, points, pos)
        self.setZValue(10000000)
        
    def updateInit(self, host):
        self.treeItem.graphicsItem = self
        self.host = host
        
    def setPointSize(self):
        pass
    
    def resetParents(self):
        pass
    
class TargetProgram(QtCore.QObject):
    
    
    
    
    
    
    def __init__(self):
        self.origin = QtGui.QGraphicsEllipseItem(0,0,1,1)
        self.paths = []
        
    def setPen(self, pen):
        self.origin.setPen(pen)
        
    def listPoints(self):
        pass
        