# -*- coding: utf-8 -*-
from ProtocolTemplate import Ui_Form
from lib.devices.Device import ProtocolGui
from PyQt4 import QtCore, QtGui
from lib.Manager import getManager
from WidgetGroup import WidgetGroup
import pyqtgraph.widgets as widgets
#from pyqtgraph.widgets import *
import random
import numpy

class ScannerProtoGui(ProtocolGui):
    
    #sigSequenceChanged = QtCore.Signal(object)  ## inherited from Device
    
    def __init__(self, dev, prot):
        ProtocolGui.__init__(self, dev, prot)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.ui.programControlsLayout.setEnabled(False)
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
              
        ## Create state group for saving/restoring state
        self.stateGroup = WidgetGroup([
            (self.ui.cameraCombo,),
            (self.ui.laserCombo,),
            (self.ui.minTimeSpin, 'minTime'),
            (self.ui.minDistSpin, 'minDist', 1e6),
            (self.ui.simulateShutterCheck, 'simulateShutter'),
#            (self.ui.packingSpin, 'packingDensity')  ## packing density should be suggested by device rather than loaded with protocol (I think..)
        ])
        self.stateGroup.setState({'minTime': 10, 'minDist': 500e-6})

        ## Note we use lambda functions for all these clicks to strip out the arg sent with the signal
        
        #QtCore.QObject.connect(self.ui.addPointBtn, QtCore.SIGNAL('clicked()'), self.addPoint)
        self.ui.addPointBtn.clicked.connect(lambda: self.addPoint())
        #QtCore.QObject.connect(self.ui.addGridBtn, QtCore.SIGNAL('clicked()'), self.addGrid)
        self.ui.addGridBtn.clicked.connect(lambda: self.addGrid())
        #QtCore.QObject.connect(self.ui.addOcclusionBtn, QtCore.SIGNAL('clicked()'), self.addOcclusion)
        self.ui.addOcclusionBtn.clicked.connect(lambda: self.addOcclusion())
        #QtCore.QObject.connect(self.ui.addProgramBtn, QtCore.SIGNAL('clicked()'), self.addProgram)
        self.ui.addProgramBtn.clicked.connect(lambda: self.addProgram())
        #QtCore.QObject.connect(self.ui.addSpiralScanBtn, QtCore.SIGNAL('clicked()'), self.addSpiral)
        self.ui.addSpiralScanBtn.clicked.connect(lambda: self.addSpiral())
        #QtCore.QObject.connect(self.ui.deleteBtn, QtCore.SIGNAL('clicked()'), self.delete)
        self.ui.deleteBtn.clicked.connect(lambda: self.delete())
        #QtCore.QObject.connect(self.ui.deleteAllBtn, QtCore.SIGNAL('clicked()'), self.deleteAll)
        self.ui.deleteAllBtn.clicked.connect(lambda: self.deleteAll())
        #QtCore.QObject.connect(self.ui.itemList, QtCore.SIGNAL('itemClicked(QListWidgetItem*)'), self.itemToggled)
        self.ui.itemList.itemClicked.connect(self.itemToggled)
        #QtCore.QObject.connect(self.ui.itemList, QtCore.SIGNAL('currentItemChanged(QListWidgetItem*,QListWidgetItem*)'), self.itemSelected)
        self.ui.itemList.currentItemChanged.connect(self.itemSelected)
        #QtCore.QObject.connect(self.ui.displayCheck, QtCore.SIGNAL('toggled(bool)'), self.showInterface)
        self.ui.displayCheck.toggled.connect(self.showInterface)
        #QtCore.QObject.connect(self.ui.cameraCombo, QtCore.SIGNAL('currentIndexChanged(int)'), self.camModChanged)
        self.ui.cameraCombo.currentIndexChanged.connect(self.camModChanged)
        #QtCore.QObject.connect(self.ui.packingSpin, QtCore.SIGNAL('valueChanged(double)'), self.packingSpinChanged)
        self.ui.packingSpin.valueChanged.connect(self.packingSpinChanged)
        #QtCore.QObject.connect(self.ui.minTimeSpin, QtCore.SIGNAL('valueChanged(double)'), self.sequenceChanged)
        self.ui.minTimeSpin.valueChanged.connect(self.sequenceChanged)
        #QtCore.QObject.connect(self.ui.minDistSpin, QtCore.SIGNAL('valueChanged(double)'), self.sequenceChanged)
        self.ui.minDistSpin.valueChanged.connect(self.sequenceChanged)
        #QtCore.QObject.connect(self.ui.recomputeBtn, QtCore.SIGNAL('clicked()'), self.generateTargets)
        self.ui.recomputeBtn.clicked.connect(self.generateTargets)
        #QtCore.QObject.connect(dm, QtCore.SIGNAL('modulesChanged'), self.fillModuleList)
        dm.sigModulesChanged.connect(self.fillModuleList)

        #self.currentTargetMarker = QtGui.QGraphicsEllipseItem(0, 0, 1, 1)
        #pen = QtGui.QPen(QtGui.QBrush(QtGui.QColor(255, 255, 255)), 3.0)
        #pen.setCosmetic(True)
        #self.currentTargetMarker.setPen(pen)
        
        #self.currentTargetMarker.hide()
        
        self.testTarget = TargetPoint([0,0], self.pointSize()[0])
        self.testTarget.setPen(QtGui.QPen(QtGui.QColor(255, 200, 200)))
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
        
        
    def fillModuleList(self):
        man = getManager()
        self.ui.cameraCombo.clear()
        mods = man.listModules()
        for m in mods:
            self.ui.cameraCombo.addItem(m)
            mod = man.getModule(m)
            if 'camDev' in mod.config and mod.config['camDev'] == self.defCam:
                self.ui.cameraCombo.setCurrentIndex(self.ui.cameraCombo.count()-1)
        
        
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
        print "packingSpinChanged."
        #self.updateSpotSizes()
        self.dev.updateTargetPacking(self.ui.packingSpin.value())
        self.updateSpotSizes()
        
    def updateSpotSizes(self):
        size, packing = self.pointSize()
        #pd = self.pointSize()[1]
        for i in self.items.values():
            i.setPointSize(size, packing)
        self.testTarget.setPointSize(size)

    def showInterface(self, b):
        for k in self.items:
            if self.listItem(k).checkState() == QtCore.Qt.Checked:
                self.items[k].setVisible(b)
        self.testTarget.setVisible(b)

    def listItem(self, name):
        return self.ui.itemList.findItems(name, QtCore.Qt.MatchExactly)[0]

    def pointSize(self):
        try:
            cam = self.cameraModule().config['camDev']
            laser = str(self.ui.laserCombo.currentText())
            cal = self.dev.getCalibration(cam, laser)
            #ss = cal['spot'][1] * self.ui.packingSpin.value()
            packing = self.ui.packingSpin.value()
            ss = cal['spot'][1]
        except:
            ss = 1
            packing = self.ui.packingSpin.value()
        return (ss, packing)
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
        s, packing = self.pointSize()
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
        for i in self.items.itervalues():
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
        self.targets = []
        locations = self.getTargetList()
        #locations = []
        #for i in items:
        #    pts = i.listPoints()
        #    for p in pts:
        #        locations.append(p)

        
        minTime = None
        bestSolution = None
        nTries = 10
        
        
        ## About to compute order/timing of targets; display a progress dialog
        
        progressDlg = QtGui.QProgressDialog("Computing pseudo-optimal target sequence...", "Cancel", 0, nTries)
        #progressDlg.setWindowModality(QtCore.Qt.WindowModal)
        progressDlg.setMinimumDuration(250)
        
        try:
            for i in range(nTries):
                solution = self.findSolution(locations)
                time = sum([l[1] for l in solution])
                if minTime is None or time < minTime:
                    #print "  new best time:", time
                    minTime = time
                    bestSolution = solution[:]
                progressDlg.setValue(i)
                QtGui.QApplication.processEvents()
                if progressDlg.wasCanceled():
                    raise Exception("Target sequence computation canceled by user.")
        except:
            raise
        finally:
            ## close progress dialog no matter what happens
            progressDlg.setValue(nTries)
        
        
        #for i in range(10):
            #solution = self.swapWorst(bestSolution)
            #if solution is None:
                #continue
            #bestSolution = solution
        
        
        self.targets = bestSolution
        #print "Solution:"
        #for t in self.targets:
            #print "  ", t
        self.ui.timeLabel.setText('Total time: %0.1f sec'% minTime)
        
    def findSolution(self, locations):
        locations = locations[:]
        random.shuffle(locations)
        solution = [(locations.pop(), 0.0)]
        
        while len(locations) > 0:
            minTime = None
            minIndex = None
            for i in range(len(locations)):
                time = self.computeTime(solution, locations[i])
                if minTime is None or time < minTime:
                    minTime = time
                    minIndex = i
                if time == 0.0:  ## can't get any better; stop searching
                    break
            solution.append((locations.pop(minIndex), minTime))
        return solution
        
    #def swapWorst(self, solution):
        #"""Find points very close together, swap elsewhere to improve time"""
        #maxTime = None
        #maxInd = None
        ### find worst pair
        #for i in range(len(solution)):
            #if maxTime is None or maxTime < solution[i][1]:
                #maxTime = solution[i][1]
                #maxInd = i
        
        ### Try moving
        
        #minTime = sum([l[1] for l in solution])
        ##print "Trying swap, time is currently", minTime
        #bestSolution = None
        #for i in range(len(solution)):
            #newSoln = solution[:]
            #loc = newSoln.pop(maxInd)
            #newSoln.insert(i, loc)
            #(soln, time) = self.computeTimes([l[0] for l in newSoln])
            #if time < minTime:
                #minTime = time
                #bestSolution = soln
        ##print "  new time is ", minTime
        #return bestSolution
            
    def costFunction(self):
        state = self.stateGroup.state()
        minTime = state['minTime']
        minDist = state['minDist']
        b = numpy.log(0.1) / minDist**2
        return lambda dist: minTime * numpy.exp(b * dist**2)

    def computeTime(self, solution, loc, func=None):
        """Return the minimum time that must be waited before stimulating the location, given that solution has already run"""
        if func is None:
            func = self.costFunction()
        state = self.stateGroup.state()
        minDist = state['minDist']
        minTime = state['minTime']
        minWaitTime = 0.0
        cumWaitTime = 0
        for i in range(len(solution)-1, -1, -1):
            l = solution[i][0]
            dx = loc[0] - l[0]
            dy = loc[1] - l[1]
            dist = (dx **2 + dy **2) ** 0.5
            if dist > minDist:
                time = 0.0
            else:
                time = func(dist) - cumWaitTime
            #print i, "cumulative time:", cumWaitTime, "distance: %0.1fum" % (dist * 1e6), "time:", time
            minWaitTime = max(minWaitTime, time)
            cumWaitTime += solution[i][1]
            if cumWaitTime > minTime:
                break
        #print "--> minimum:", minWaitTime
        return minWaitTime
            
            
            
            
        

    def activeItems(self):
        return [self.items[i] for i in self.items if self.listItem(i).checkState() == QtCore.Qt.Checked]

    
    def taskStarted(self, params):
        """Task has started; color the current and previous targets"""
        if 'targets' not in params:
            return
        #t = params['targets']
        #self.currentTargetMarker.setRect
    
    def quit(self):
        print "scanner dock quit"
        self.deleteAll(clearHistory = False)
        s = self.testTarget.scene()
        if s is not None:
            self.testTarget.scene().removeItem(self.testTarget)
        #QtCore.QObject.disconnect(getManager(), QtCore.SIGNAL('modulesChanged'), self.fillModuleList)
        getManager().sigModulesChanged.disconnect(self.fillModuleList)
            
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
        print "  ..done."
    
class TargetPoint(widgets.EllipseROI):
    
    
    
    
    
    
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
        self.gridPacking = pd
        self.setCacheMode(QtGui.QGraphicsItem.DeviceCoordinateCache)
        self.regeneratePoints()
        
    def setPointSize(self, size, packing):
        self.pointSize = size
        self.gridPacking = packing
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
        #ps2 = self.pointSize * 0.5 * self.gridPacking
        #p.setPen(self.pen)
        p.scale(self.pointSize, self.pointSize) ## do scaling here because otherwise we end up with squares instead of circles (GL bug)
        for i in range(len(self.points)):
            pt = self.points[i]
            if self.pens[i] != None:
                p.setPen(self.pens[i])
            else:
                p.setPen(self.pen)
            p.drawEllipse(QtCore.QRectF((pt[0] - ps2)/self.pointSize, (pt[1] - ps2)/self.pointSize, 1, 1))
        
class TargetOcclusion(widgets.PolygonROI):
    
    
    
    
    
    
    def __init__(self, points, pos=None):
        widgets.PolygonROI.__init__(self, points, pos)
        self.setZValue(10000000)
    
    def setPointSize(self, size, packing):
        pass
    
class TargetProgram(QtCore.QObject):
    
    
    
    
    
    
    def __init__(self):
        self.origin = QtGui.QGraphicsEllipseItem(0,0,1,1)
        self.paths = []
        
    def setPen(self, pen):
        self.origin.setPen(pen)
        
    def listPoints(self):
        pass
        