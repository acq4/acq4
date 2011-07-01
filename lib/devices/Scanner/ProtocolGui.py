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
        self.ui.itemList.itemClicked.connect(self.itemToggled)
        self.ui.itemList.currentItemChanged.connect(self.itemSelected)
        self.ui.displayCheck.toggled.connect(self.showInterface)
        self.ui.cameraCombo.currentIndexChanged.connect(self.camModChanged)
        self.ui.packingSpin.valueChanged.connect(self.packingSpinChanged)
        self.ui.sizeFromCalibrationRadio.toggled.connect(self.updateSpotSizes)
        self.ui.sizeSpin.valueChanged.connect(self.sizeSpinEdited)
        #QtCore.QObject.connect(self.ui.minTimeSpin, QtCore.SIGNAL('valueChanged(double)'), self.sequenceChanged)
        self.ui.minTimeSpin.valueChanged.connect(self.sequenceChanged)
        self.ui.minDistSpin.valueChanged.connect(self.sequenceChanged)
        self.ui.recomputeBtn.clicked.connect(self.generateTargets)
        dm.sigModulesChanged.connect(self.fillModuleList)

        #self.currentTargetMarker = QtGui.QGraphicsEllipseItem(0, 0, 1, 1)
        #pen = QtGui.QPen(QtGui.QBrush(QtGui.QColor(255, 255, 255)), 3.0)
        #pen.setCosmetic(True)
        #self.currentTargetMarker.setPen(pen)
        
        #self.currentTargetMarker.hide()
        
        self.testTarget = TargetPoint([0,0], 100e-6)
        self.testTarget.setPen(QtGui.QPen(QtGui.QColor(255, 200, 200)))
        self.updateSpotSizes()
        #camMod = self.cameraModule()
        
        self.currentObjective = None
        self.currentScope = None
        self.currentCamMod = None
        self.camModChanged()

        
        ## load target list from device, allowing targets to persist across protocols
        oldTargetList = self.dev.getTargetList()
        self.ui.packingSpin.setValue(oldTargetList[0])
        for k in oldTargetList[1].keys():
            t = oldTargetList[1][k]
            if t[0] == 'point':
                pos = t[1]
                self.addPoint(pos=pos,  name=k)
                #pt.setPos(pos)
            elif t[0] == 'grid':
                pos = t[1]
                size = t[2]
                angle = t[3]
                self.addGrid(pos=pos, size=size, angle=angle,  name=k)
                #gr.setPos(pos)
                #gr.setSize(size)
                #gr.setAngle(angle)
            elif t[0] == 'occlusion':
                self.addOcclusion(t[1], t[2], name=k)

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
            self.testTarget.setPointSize(self.pointSize()[0])
            #self.cameraModule().ui.centerItem(self.testTarget)
        camMod = self.cameraModule()
        camMod.ui.removeItem(self.testTarget)
        camMod.ui.addItem(self.testTarget, None, [1,1], 1010)

    def packingSpinChanged(self):
        #print "packingSpinChanged."
        #self.updateSpotSizes()
        self.dev.updateTargetPacking(self.ui.packingSpin.value())
        self.updateSpotSizes()
        
    def sizeSpinEdited(self):
        self.ui.sizeCustomRadio.setChecked(True)
        self.updateSpotSizes()
        
    def updateSpotSizes(self):
        size, packing, displaySize = self.pointSize()
        #pd = self.pointSize()[1]
        for i in self.items.values():
            i.setPointSize(size, packing, displaySize)
        self.testTarget.setPointSize(size)

    def showInterface(self, b):
        for k in self.items:
            if self.listItem(k).checkState() == QtCore.Qt.Checked:
                self.items[k].setVisible(b)
        self.testTarget.setVisible(b)

    def listItem(self, name):
        return self.ui.itemList.findItems(name, QtCore.Qt.MatchExactly)[0]

    def pointSize(self):
        packing = self.ui.packingSpin.value()
        try:
            cam = self.cameraModule().config['camDev']
            laser = str(self.ui.laserCombo.currentText())
            cal = self.dev.getCalibration(cam, laser)
            ss = cal['spot'][1]
           
        except:
            print "Could not find spot size from calibration."
            raise   
        if self.ui.sizeFromCalibrationRadio.isChecked():
            displaySize = ss
            self.ui.sizeSpin.valueChanged.disconnect(self.sizeSpinEdited)
            self.stateGroup.setState({'spotSize':ss})
            self.ui.sizeSpin.valueChanged.connect(self.sizeSpinEdited)
        elif self.ui.sizeCustomRadio.isChecked():
            displaySize = self.ui.sizeSpin.value()
        return (ss, packing, displaySize)
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
        
        
        
    def handleResult(self, result, params):
        pass
    
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
        
    def addGrid(self, pos=None, size=None, angle=0,  name=None):
        autoName = False
        if name is None:
            name = 'Grid'
            autoName = True
        s, packing, dispSize = self.pointSize()
        autoPos = False
        if pos is None:
            pos = [0,0]
            autoPos = True
        if size is None:
            size = [s*4, s*4]
        pt = TargetGrid(pos, size, s, packing, angle)
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
        #listitem = QtGui.QListWidgetItem(name)
        #listitem.setCheckState(QtCore.Qt.Checked)
        #self.ui.itemList.addItem(listitem)
        #self.updateItemColor(listitem)
        #camMod.ui.addItem(item.origin, None, [1,1], 1000)
        #item.connect(QtCore.SIGNAL('regionChangeFinished'), self.itemMoved)
        #item.connect(QtCore.SIGNAL('regionChanged'), self.getTargetList)
        #item.connect(QtCore.SIGNAL('pointsChanged'), self.itemChanged)
        #self.itemChanged(item)
        #self.updateDeviceTargetList(item)
        
        

    def addItem(self, item, name,  autoPosition=True,  autoName=True):
        camMod = self.cameraModule()
        if camMod is None:
            return False
        if autoName:
            name = name + str(self.nextId)
        item.name = name
        item.objective = self.currentObjective
        self.items[name] = item
        #if isinstance(item, TargetOcclusion):
            #self.occlusions[name] = item
        listitem = QtGui.QListWidgetItem(name)
        listitem.setCheckState(QtCore.Qt.Checked)
        self.ui.itemList.addItem(listitem)
        self.nextId += 1
        self.updateItemColor(listitem)
        if autoPosition:
            pos = None
        else:
            pos = item.stateCopy()['pos'] 
        camMod.ui.addItem(item, pos, [1, 1], 1000)
        #item.connect(QtCore.SIGNAL('regionChangeFinished'), self.itemMoved)
        item.sigRegionChangeFinished.connect(self.itemMoved)
        #item.connect(QtCore.SIGNAL('regionChanged'), self.getTargetList)
        item.sigRegionChanged.connect(self.getTargetList)
        #item.connect(QtCore.SIGNAL('pointsChanged'), self.itemChanged)
        item.sigPointsChanged.connect(self.itemChanged)
        #QtCore.QObject.connect(item, QtCore.SIGNAL('regionChangeFinished'), self.itemMoved)
        #QtCore.QObject.connect(item, QtCore.SIGNAL('pointsChanged'), self.itemChanged)
        self.itemChanged(item)
        self.updateDeviceTargetList(item)

    def addTarget(self, t, name):
        self.sequenceChanged()

    def removeTarget(self, name):
        pass
    
    def delete(self):
        row = self.ui.itemList.currentRow()
        item = self.ui.itemList.takeItem(row)
        if item is None:
            return
        name = str(item.text())
        self.dev.updateTarget(name, None)  ## inform the device that this target is no more
        i = self.items[name]
        #self.removeItemPoints(i)
        i.scene().removeItem(i)
        del self.items[name]
        #self.occlusions.get(name)
        self.sequenceChanged()

    def deleteAll(self, clearHistory=True):
        self.ui.itemList.clear()
        for k in self.items:
            if clearHistory == True:
                self.dev.updateTarget(k, None)  ## inform the device that this target is no more
            i = self.items[k]
            i.scene().removeItem(i)
            #self.removeItemPoints(i)
        self.items = {}
        #self.occlusions = {}
        self.sequenceChanged()
        
    def itemToggled(self, item):
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
            color = QtGui.QColor(200, 255, 100)
        name = str(item.text())
        self.items[name].setPen(QtGui.QPen(color))

    def itemMoved(self, item):
        self.targets = None
        self.updateDeviceTargetList(item)
        self.sequenceChanged()
        

    def itemChanged(self, item):
        self.targets = None
        self.sequenceChanged()
    
    def updateDeviceTargetList(self, item):
        """For keeping track of items outside of an individual scanner device. Allows multiple protocols to access the same items."""
        name = str(item.name)
        state = item.stateCopy()
        if isinstance(item, TargetPoint):
            pos = state['pos']
            pos[0] += state['size'][0]/2.0
            pos[1] += state['size'][1]/2.0
            info = ['point', pos]
        elif isinstance(item, TargetGrid):
            info = ['grid', state['pos'], state['size'], state['angle']]
        elif isinstance(item, TargetOcclusion):
            info = ['occlusion', item.pos(), item.listPoints()]
        elif isinstance(item, widgets.SpiralROI):
            info = ['spiral', item.pos()]
        
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

    def generateTargets(self):
        #items = self.activeItems()
        #prof= Profiler('ScanerProtoGui.generateTargets()')
        self.targets = []
        locations = self.getTargetList()
        
        minTime = None
        bestSolution = None

        nTries = np.clip(int(10 - len(locations)/20), 1, 10)
        
        ## About to compute order/timing of targets; display a progress dialog
        #prof.mark('setup')
        progressDlg = QtGui.QProgressDialog("Computing pseudo-optimal target sequence...", "Cancel", 0, 1000)
        #progressDlg.setWindowModality(QtCore.Qt.WindowModal)
        progressDlg.setMinimumDuration(500)
        #prof.mark('progressDlg')
        deadTime = self.prot.getParam('duration')
        
        try:
            #times=[]
            for i in range(nTries):
                #prof.mark('attempt: %i' %i)
                for n, m in optimize.opt2(locations, self.costFn, deadTime, greed=1.0):
                    ## we can update the progress dialog here.
                    if m is None:
                        solution = n
                    else:
                        prg = int(((i/float(nTries)) + ((n/float(m))/float(nTries))) * 1000)
                        #print n,m, prg
                        progressDlg.setValue(prg)
                        #print i
                        QtGui.QApplication.processEvents()
                        if progressDlg.wasCanceled():
                            raise Exception("Target sequence computation canceled by user.")
                #solution = self.findSolution(locations)
                #prof.mark('foundSolution')
                time = sum([l[1] for l in solution])
                #times.append(time)
                if minTime is None or time < minTime:
                    #print "  new best time:", time
                    minTime = time
                    bestSolution = solution[:]
                    #print "new best:", len(bestSolution), minTime
                #prof.mark('check time')
        except:
            raise
        finally:
            ## close progress dialog no matter what happens
            #print "Times: ", times
            progressDlg.setValue(1000)
        
        self.targets = bestSolution
        #print "Solution:"
        #for t in self.targets:
            #print "  ", t
        self.ui.timeLabel.setText('Total time: %0.1f sec'% minTime)
        #prof.mark('Done.')
        #prof.finish()
        
    def costFn(self, dist):
        ### Takes distance^2 as argument!
        state = self.stateGroup.state()
        minTime = state['minTime']
        minDist = state['minDist']
        A = 2 * minTime / minDist**2
        return np.where(
            dist < minDist, 
            np.where(
                dist < minDist/2., 
                minTime - A * dist**2, 
                A * (dist-minDist)**2
            ), 
            0
        )

    def activeItems(self):
        return [self.items[i] for i in self.items if self.listItem(i).checkState() == QtCore.Qt.Checked]

    
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
        widgets.ROI.__init__(self, pos, [radius] * 2, **args)
        self.aspectLocked = True
        self.overPen = None
        self.underPen = self.pen
        
    def setPointSize(self, size):
        s = size / self.state['size'][0]
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
        

class TargetGrid(widgets.ROI):
    
    sigPointsChanged = QtCore.Signal(object)
    
    def __init__(self, pos, size, ptSize, pd, angle):
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
        self.gridPacking = pd
        ## cache is not working in qt 4.7
        self.setCacheMode(QtGui.QGraphicsItem.DeviceCoordinateCache)
        self.regeneratePoints()
        
    def setPointSize(self, size, packing, displaySize):
        self.pointSize = size
        self.gridPacking = packing
        self.pointDisplaySize = displaySize
        self.regeneratePoints()
        
        
    def rgnChanged(self):
        if self.state['size'] != self.lastSize:
            self.regeneratePoints()
            self.lastSize = self.state['size']

    def regeneratePoints(self):
        self.points = []
        self.pens = []
        sq3 = 3. ** 0.5
        sepx = self.pointSize * self.gridPacking
        sepy = sq3 * sepx
        self.generateGrid([self.pointSize*0.5, self.pointSize*0.5], [sepx, sepy])  ## make every other row of the grid starting from top
        self.generateGrid([self.pointSize*0.5+0.5*sepx, 0.5*self.pointSize + sepy/2.0 ], [sepx, sepy]) ### make every other row of the grid starting with 2nd row
        self.update()
        #self.emit(QtCore.SIGNAL('pointsChanged'), self)
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
        
class TargetOcclusion(widgets.PolygonROI):
    
    
    sigPointsChanged = QtCore.Signal(object)
    
    def __init__(self, points, pos=None):
        widgets.PolygonROI.__init__(self, points, pos)
        self.setZValue(10000000)
    
    def setPointSize(self, size, packing, displaySize=None):
        pass
    
class TargetProgram(QtCore.QObject):
    
    
    
    
    
    
    def __init__(self):
        self.origin = QtGui.QGraphicsEllipseItem(0,0,1,1)
        self.paths = []
        
    def setPen(self, pen):
        self.origin.setPen(pen)
        
    def listPoints(self):
        pass
        