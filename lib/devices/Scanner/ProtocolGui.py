# -*- coding: utf-8 -*-
from ProtocolTemplate import Ui_Form
from lib.devices.Device import ProtocolGui
from PyQt4 import QtCore, QtGui
from lib.Manager import getManager
from lib.util.WidgetGroup import WidgetGroup
from lib.util.pyqtgraph.widgets import *
import random
import numpy

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
            (self.ui.packingSpin, 'packingDensity')
        ])
        self.stateGroup.setState({'minTime': 10, 'minDist': 500e-6})

        QtCore.QObject.connect(self.ui.addPointBtn, QtCore.SIGNAL('clicked()'), self.addPoint)
        QtCore.QObject.connect(self.ui.addGridBtn, QtCore.SIGNAL('clicked()'), self.addGrid)
        QtCore.QObject.connect(self.ui.deleteBtn, QtCore.SIGNAL('clicked()'), self.delete)
        QtCore.QObject.connect(self.ui.deleteAllBtn, QtCore.SIGNAL('clicked()'), self.deleteAll)
        QtCore.QObject.connect(self.ui.itemList, QtCore.SIGNAL('itemClicked(QListWidgetItem*)'), self.itemToggled)
        QtCore.QObject.connect(self.ui.itemList, QtCore.SIGNAL('currentItemChanged(QListWidgetItem*,QListWidgetItem*)'), self.itemSelected)
        QtCore.QObject.connect(self.ui.displayCheck, QtCore.SIGNAL('toggled(bool)'), self.showInterface)
        QtCore.QObject.connect(self.ui.cameraCombo, QtCore.SIGNAL('currentIndexChanged(int)'), self.camModChanged)
        QtCore.QObject.connect(self.ui.packingSpin, QtCore.SIGNAL('valueChanged(double)'), self.updateSpotSizes)
        QtCore.QObject.connect(self.ui.recomputeBtn, QtCore.SIGNAL('clicked()'), self.generateTargets)
        QtCore.QObject.connect(dm, QtCore.SIGNAL('modulesChanged'), self.fillModuleList)
        

        self.testTarget = TargetPoint([0,0], self.pointSize())
        self.testTarget.setPen(QtGui.QPen(QtGui.QColor(255, 200, 200)))
        #camMod = self.cameraModule()
        
        self.currentObjective = None
        self.currentScope = None
        self.currentCamMod = None
        self.camModChanged()
        
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
            QtCore.QObject.disconnect(self.currentCamMod.ui, QtCore.SIGNAL('cameraScaleChanged'), self.objectiveChanged)
        if self.currentScope is not None:
            QtCore.QObject.disconnect(self.currentScope, QtCore.SIGNAL('objectiveChanged'), self.objectiveChanged)
            
        self.currentCamMod = camMod
        if camDev is None or camMod is None:
            self.currentScope = None
            return
        self.currentScope = camDev.getScopeDevice()
        self.currentCamMod = camMod
        QtCore.QObject.connect(self.currentCamMod.ui, QtCore.SIGNAL('cameraScaleChanged'), self.objectiveChanged)
        
        if self.currentScope is not None:
            QtCore.QObject.connect(self.currentScope, QtCore.SIGNAL('objectiveChanged'), self.objectiveChanged)
        camMod.ui.addItem(self.testTarget, None, [1,1], 1010)
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
            self.testTarget.setPointSize(self.pointSize())
            #self.cameraModule().ui.centerItem(self.testTarget)
        camMod = self.cameraModule()
        camMod.ui.removeItem(self.testTarget)
        camMod.ui.addItem(self.testTarget, None, [1,1], 1010)

    def updateSpotSizes(self):
        size = self.pointSize()
        for i in self.items.values():
            i.setPointSize(size)
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
            ss = cal['spot'][1] * self.ui.packingSpin.value()
        except:
            ss = 1
        return ss
        
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
        targets = 0
        for i in items:
            targets += len(i.listPoints())
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
            'laser': str(self.ui.laserCombo.currentText())
        }
        return prot
        
        
        
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
        camMod = self.cameraModule()
        if camMod is None:
            return False
        name = name + str(self.nextId)
        item.name = name
        item.objective = self.currentObjective
        self.items[name] = item
        listitem = QtGui.QListWidgetItem(name)
        listitem.setCheckState(QtCore.Qt.Checked)
        self.ui.itemList.addItem(listitem)
        self.nextId += 1
        self.updateItemColor(listitem)
        
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
        #self.removeItemPoints(i)
        i.scene().removeItem(i)
        del self.items[name]
        self.sequenceChanged()

    def deleteAll(self):
        self.ui.itemList.clear()
        for k in self.items:
            i = self.items[k]
            i.scene().removeItem(i)
            #self.removeItemPoints(i)
        self.items = {}
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

    def itemChanged(self, item):
        self.targets = None
        self.sequenceChanged()
    
    def sequenceChanged(self):
        self.emit(QtCore.SIGNAL('sequenceChanged'), self.dev.name)

    def generateTargets(self):
        items = self.activeItems()
        self.targets = []
        locations = []
        for i in items:
            pts = i.listPoints()
            for p in pts:
                locations.append(p)
        
        minTime = None
        bestSolution = None
        nTries = 10
        
        
        ## About to compute order/timing of targets; display a progress dialog
        
        progressDlg = QtGui.QProgressDialog("Computing pseudo-optimal target sequence...", "Cancel", 0, nTries)
        progressDlg.setWindowModality(QtCore.Qt.WindowModal)
        progressDlg.setMinimumDuration(0)
        
        try:
            for i in range(nTries):
                solution = self.findSolution(locations)
                time = sum([l[1] for l in solution])
                if minTime is None or time < minTime:
                    #print "  new best time:", time
                    minTime = time
                    bestSolution = solution[:]
                QtGui.QApplication.processEvents()
                progressDlg.setValue(i)
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

    def quit(self):
        print "scanner dock quit"
        self.deleteAll()
        s = self.testTarget.scene()
        if s is not None:
            self.testTarget.scene().removeItem(self.testTarget)
        QtCore.QObject.disconnect(getManager(), QtCore.SIGNAL('modulesChanged'), self.fillModuleList)
            
        if self.currentCamMod is not None:
            try:
                QtCore.QObject.disconnect(self.currentCamMod.ui, QtCore.SIGNAL('cameraScaleChanged'), self.objectiveChanged)
            except:
                pass
        if self.currentScope is not None:
            try:
                QtCore.QObject.disconnect(self.currentScope, QtCore.SIGNAL('objectiveChanged'), self.objectiveChanged)
            except:
                pass
        print "  ..done."
    
class TargetPoint(EllipseROI):
    def __init__(self, pos, radius, **args):
        ROI.__init__(self, pos, [radius] * 2, **args)
        self.aspectLocked = True
        
    def setPointSize(self, size):
        s = size / self.state['size'][0]
        self.scale(s, [0.5, 0.5])
        
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
        p.scale(self.pointSize, self.pointSize) ## do scaling here because otherwise we end up with squares instead of circles (GL bug)
        for pt in self.points:
            p.drawEllipse(QtCore.QRectF((pt[0] - ps2)/self.pointSize, (pt[1] - ps2)/self.pointSize, 1, 1))
        
        


