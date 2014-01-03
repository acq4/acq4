# -*- coding: utf-8 -*-
from TaskTemplate import Ui_Form
from acq4.devices.Device import TaskGui
#from ScanProgramGenerator import *
from PyQt4 import QtCore, QtGui
from acq4.Manager import getManager, logMsg, logExc
import random
import numpy as np
from acq4.util.debug import Profiler
import optimize ## for determining random scan patterns
#import ForkedIterator
import os, sys
import acq4.pyqtgraph as pg
from acq4.util.HelpfulException import HelpfulException
import acq4.pyqtgraph.parametertree.parameterTypes as pTypes
from acq4.pyqtgraph.parametertree import Parameter, ParameterTree, ParameterItem, registerParameterType


### Error IDs:
###  1: Could not find spot size from calibration. (from ScannerTaskGui.pointSize)


class PositionCtrlGroup(pTypes.GroupParameter):
    sigAddNewRequested = QtCore.Signal(object, object)
    def __init__(self):
        opts = {
            'name': 'Position Controls',
            'type': 'group',
            'addText': "Add Control..",
            'addList': ['Point', 'Grid', 'Occlusion', 'Grid (beta)'],

        }
        pTypes.GroupParameter.__init__(self, **opts)
    
    def addNew(self, typ):
        self.sigAddNewRequested.emit(self, typ)

class ProgramCtrlGroup(pTypes.GroupParameter):
    sigAddNewRequested = QtCore.Signal(object, object)
    def __init__(self):
        opts = {
            'name': 'Program Controls',
            'type': 'group',
            'addText': "Add Control..",
            'addList': ['lineScan', 'multipleLineScan', 'rectangleScan'],
            'autoIncrementName': True,
        }
        pTypes.GroupParameter.__init__(self, **opts)
    
    def addNew(self, typ):
        self.sigAddNewRequested.emit(self, typ)


class ScannerTaskGui(TaskGui):
    
    #sigSequenceChanged = QtCore.Signal(object)  ## inherited from Device
    
    def __init__(self, dev, task):
        TaskGui.__init__(self, dev, task)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        dm = getManager()
        self.targets = None
        self.items = {}
        self.haveCalibration = True   ## whether there is a calibration for the current combination of laser/optics
        self.currentOpticState = None
        self.currentCamMod = None
        self.programCtrls = []
        self.displaySize = {}  ## maps (laser,opticState) : display size
                               ## since this setting is remembered for each objective.
        
        ## Populate module/device lists, auto-select based on device defaults 
        self.defCam = None
        if 'defaultCamera' in self.dev.config:
            self.defCam = self.dev.config['defaultCamera']
        defLaser = None
        if 'defaultLaser' in self.dev.config:
            defLaser = self.dev.config['defaultLaser']

        self.ui.cameraCombo.setTypes(['cameraModule'])
        self.ui.laserCombo.setTypes(['laser'])
        
        self.positionCtrlGroup = PositionCtrlGroup()
        self.positionCtrlGroup.sigAddNewRequested.connect(self.addPositionCtrl)
        self.ui.itemTree.setParameters(self.positionCtrlGroup, showTop=False)
        self.positionCtrlGroup.sigChildRemoved.connect(self.positionCtrlRemoved)
        
        self.programCtrlGroup = ProgramCtrlGroup()
        self.programCtrlGroup.sigAddNewRequested.connect(self.addProgramCtrl)
        self.ui.programTree.setParameters(self.programCtrlGroup, showTop=False)
        self.programCtrlGroup.sigChildRemoved.connect(self.programCtrlRemoved)

        ## Set up SpinBoxes
        self.ui.minTimeSpin.setOpts(dec=True, step=1, minStep=1e-3, siPrefix=True, suffix='s', bounds=[0, 50])
        self.ui.minDistSpin.setOpts(dec=True, step=1, minStep=1e-6, siPrefix=True, suffix='m', bounds=[0, 10e-3])
        self.ui.sizeSpin.setOpts(dec=True, step=1, minStep=1e-6, siPrefix=True, suffix='m', bounds=[0, 1e-3])
        ## Create state group for saving/restoring state
        self.stateGroup = pg.WidgetGroup([
            (self.ui.cameraCombo,),
            (self.ui.laserCombo,),
            (self.ui.minTimeSpin, 'minTime'),
            (self.ui.minDistSpin, 'minDist'),
            (self.ui.simulateShutterCheck, 'simulateShutter'),
            (self.ui.sizeSpin, 'spotSize'),
#            (self.ui.packingSpin, 'packingDensity')  ## packing density should be suggested by device rather than loaded with task (I think..)
        ])
        self.stateGroup.setState({'minTime': 10, 'minDist': 500e-6, 'sizeSpin':100e-6})
        self.tdPlot = self.ui.tdPlotWidget.plotItem
        self.tdPlot.setLabel('bottom', text="Distance", units='m')
        self.tdPlot.setLabel('left', text="Wait time", units='s')

        ## Note we use lambda functions for all these clicks to strip out the arg sent with the signal
        
        self.ui.hideCheck.toggled.connect(self.showInterface)
        self.ui.hideMarkerBtn.clicked.connect(self.hideSpotMarker)
        self.ui.cameraCombo.currentIndexChanged.connect(self.camModChanged)
        self.ui.laserCombo.currentIndexChanged.connect(self.laserDevChanged)
        self.ui.sizeFromCalibrationRadio.toggled.connect(self.updateSpotSizes)
        self.ui.sizeSpin.valueChanged.connect(self.sizeSpinEdited)
        self.ui.minTimeSpin.valueChanged.connect(self.sequenceChanged)
        self.ui.minDistSpin.valueChanged.connect(self.sequenceChanged)
        self.ui.recomputeBtn.clicked.connect(self.recomputeClicked)
        self.ui.loadConfigBtn.clicked.connect(self.loadConfiguration)
        
        self.dev.sigGlobalSubdeviceChanged.connect(self.opticStateChanged)
        
        self.testTarget = TargetPoint(name="Test", ptSize=100e-6)
        self.testTarget.setPen(QtGui.QPen(QtGui.QColor(255, 200, 200)))
        self.spotMarker = TargetPoint(name="Last", ptSize=100e-6, movable=False)
        self.spotMarker.setPen(pg.mkPen(color=(255,255,255), width = 2))

        #try:
            #self.updateSpotSizes()
        #except HelpfulException as exc:
            #if exc.kwargs.get('errId',None) == 1:
                #self.testTarget.hide()
            #else:
                #raise

        self.spotMarker.hide()
        self.updateSpotSizes()

        self.camModChanged()
        self.updateTDPlot()
        
            
        #self.ui.simulateShutterCheck.setChecked(False)
        if 'offVoltage' not in self.dev.config: ## we don't have a voltage for virtual shuttering
            self.ui.simulateShutterCheck.setChecked(False)
            self.ui.simulateShutterCheck.setEnabled(False)
            
    def setHaveCalibration(self, have):
        self.haveCalibration = have
        self.updateVisibility()
        
    def showInterface(self, b):
        self.updateVisibility()
        
    def updateVisibility(self):
        b = self.haveCalibration and not self.ui.hideCheck.isChecked()
        for k in self.items:
            self.items[k].setVisible(b)
        self.testTarget.setVisible(b)
        
    def camModChanged(self):
        camMod = self.cameraModule()
        if self.currentCamMod is not None:
            self.currentCamMod.ui.removeItem(self.testTarget)
            self.currentCamMod.ui.removeItem(self.spotMarker)
            
        self.currentCamMod = camMod
        if camMod is None:
            return
        self.currentCamMod = camMod
            
        camMod.ui.addItem(self.testTarget, None, [1,1], 1010)
        camMod.ui.addItem(self.spotMarker, None, [1,1], 1010)
        
        self.opticStateChanged()
        
    def getLaser(self):
        return self.ui.laserCombo.currentText()
    
    def opticStateChanged(self):
        opticState = self.dev.getDeviceStateKey()
        laser = self.getLaser()
        if self.currentOpticState != opticState:
            self.currentOpticState = opticState
            
            ## recall display size settings for this objective
            dispSize = self.displaySize.get((laser,opticState), None)
            if dispSize is None:
                self.ui.sizeFromCalibrationRadio.setChecked(True)
            else:
                self.ui.sizeSpin.setValue(dispSize)
            
            ## update spots
            #self.updateSpotSizes()  Do we need this??
                
            for i in self.items.values():
                active = (i.opticState == opticState)
                i.parameters().setValue(active)
                    

    def laserDevChanged(self):
        ## called when laser device combo is changed
        ## need to update spot size
        self.updateSpotSizes()
        
    def sizeSpinEdited(self):
        self.ui.sizeCustomRadio.setChecked(True)
        self.updateSpotSizes()
        
      
    def updateSpotSizes(self):
        try:
            size, display = self.pointSize()
            for i in self.items.values():
                i.setPointSize(display, size)
            self.testTarget.setPointSize(size)
            self.spotMarker.setPointSize(size)
            
            self.setHaveCalibration(True)
        except HelpfulException as exc:
            if exc.kwargs.get('errId', None) == 1:
                self.setHaveCalibration(False)
            else:
                raise

    def pointSize(self):
        ## returns (calibrated spot size, requested display size)
        try:
            camMod = self.cameraModule()
            if camMod is None:
                return (1,1)
            cam = camMod.config['camDev']
            laser = self.getLaser()
            cal = self.dev.getCalibration(laser)
            ss = cal['spot'][1]
            
            
        except:
            #logMsg("Could not find spot size from calibration.", msgType='error') ### This should turn into a HelpfulException.
            exc = sys.exc_info()
            raise HelpfulException("Could not find spot size from calibration. ", exc=exc, reasons=["Correct camera and/or laser device are not selected.", "There is no calibration file for selected camera and laser."], errId=1)
            
        if self.ui.sizeFromCalibrationRadio.isChecked():
            displaySize = ss
            ## reconnecting before this to get around reload errors, breaks the disconnect
            #try:
                #self.ui.sizeSpin.valueChanged.disconnect(self.sizeSpinEdited)
            #except TypeError:
                #logExc("A TypeError was caught in ScannerTaskGui.pointSize(). It was probably caused by a reload.", msgType='status', importance=0)
            self.stateGroup.setState({'spotSize':ss})
            #self.ui.sizeSpin.valueChanged.connect(self.sizeSpinEdited)
            self.displaySize[(laser, self.currentOpticState)] = None
        elif self.ui.sizeCustomRadio.isChecked():
            displaySize = self.ui.sizeSpin.value()
            self.displaySize[(laser, self.currentOpticState)] = displaySize
            
        return (ss, displaySize)
        #return (0.0001, packing)
        
    def cameraModule(self):
        mod = self.ui.cameraCombo.getSelectedObj()
        if mod is None:
            return None
        return mod
        
    def saveState(self, saveItems=False):
        state = self.stateGroup.state()
        if saveItems:
            state['items'] = [param.item.saveState() for param in self.positionCtrlGroup.children()]
        return state
        
    def restoreState(self, state):
        self.stateGroup.setState(state)
        if 'items' in state:
            for itemState in state['items']:
                typ = itemState['type']
                self.addItem(typ, itemState)
    
    def storeConfiguration(self):
        state = self.saveState(saveItems=True)
        fileName = os.path.join(self.dev.configDir(), 'lastConfig')
        self.dev.dm.writeConfigFile(state, fileName)

    def loadConfiguration(self):
        fileName = os.path.join(self.dev.configDir(), 'lastConfig')
        state = self.dev.dm.readConfigFile(fileName)
        self.restoreState(state)
        
    def listSequence(self):
        #items = self.activeItems()
        targets = self.getTargetList()
        if targets > 0:
            return {'targets': targets}
        else:
            return {}
        
    def generateTask(self, params=None):
        if self.cameraModule() is None:
            raise Exception('No camera module selected, can not build task.')
        
        if params is None or 'targets' not in params:
            target = self.testTarget.listPoints()[0]
            delay = 0
        else:
            if self.targets is None:
                self.generateTargets()
            #print "targets:", len(self.targets), params['targets']
            (target, delay) = self.targets[params['targets']]
            
        if len(self.programCtrls) == 0: # doing regular position mapping
            task = {
                'position': target, 
                'minWaitTime': delay,
                #'camera': self.cameraModule().config['camDev'], 
                'laser': self.ui.laserCombo.currentText(),
              #  'simulateShutter': self.ui.simulateShutterCheck.isChecked(), ## was commented out... 
                'duration': self.task.getParam('duration')
            }
        else: # doing programmed scans
            daqName = self.dev.getDaqName()
            task = {
               # 'position': target, 
                'minWaitTime': delay,
                #'camera': self.cameraModule().config['camDev'], 
                'laser': self.ui.laserCombo.currentText(),
                'simulateShutter': self.ui.simulateShutterCheck.isChecked(),
                'duration': self.task.getParam('duration'),
                'numPts': self.task.getDevice(daqName).currentState()['numPts'],
                'program': [],
                   #('step', 0.0, None),           ## start with step to "off" position 
                   #('step', 0.2, (1.3e-6, 4e-6)), ## step to the given location after 200ms
                   #('line', (0.2, 0.205), (1.3e-6, 4e-6))  ## 5ms sweep to the new position 
                   #('step', 0.205, None),           ## finish step to "off" position at 205ms
               #]
            }
            for ctrl in self.programCtrls:
                if ctrl.isActive():
                    task['program'].append(ctrl.generateTask())
        return task
    
    def hideSpotMarker(self):
        self.spotMarker.hide()
        
        
    def handleResult(self, result, params):
        if not self.spotMarker.isVisible():
            self.spotMarker.show()
        #print 'ScannerTaskGui.handleResult() result:', result
        if 'position' in result:
            pos = result['position']
            ss = result['spotSize']
            self.spotMarker.setPos((pos[0]-ss*0.5, pos[1]-ss*0.5))
        #print 'handleResult'
    
    def addPositionCtrl(self, param, typ):
        ## called when "Add Control.." combo is changed
        self.addItem(typ)

    def positionCtrlRemoved(self, param, ctrl):
        item = ctrl.item
        item.scene().removeItem(item)
        item.parameters().sigValueChanged.disconnect(self.itemActivationChanged)
        del self.items[item.name]
        #self.updateGridLinkCombos()
        self.itemChanged()
        
    def addProgramCtrl(self, param, itemType):
        ## called when "Add Control.." combo is changed
        cls = {'lineScan': ProgramLineScan, 'multipleLineScan': ProgramMultipleLineScan, 'rectangleScan': ProgramRectScan}[itemType]
        state = {}
        ctrl = cls(**state)
        #ctrl.parameters().sigValueChanged.connect(self.itemActivationChanged)
        self.programCtrlGroup.addChild(ctrl.parameters())
        self.programCtrls.append(ctrl)
        camMod = self.cameraModule()
        if camMod is None:
            raise HelpfulException("Cannot add control items until a camera module is available to display them.")
            return False
        for item in ctrl.getGraphicsItems():
            camMod.ui.addItem(item, None, [1, 1], 1000)

    def programCtrlRemoved(self, parent, param):
        ctrl = param.ctrl
        for item in ctrl.getGraphicsItems():
            if item.scene() is not None: # only try this when we have a scene that the item was inserted into (pbm 6/6/2013)
                item.scene().removeItem(item)
        self.programCtrls.remove(ctrl)
        
        #item.parameters().sigValueChanged.disconnect(self.itemActivationChanged)
        #del self.items[item.name]
        #self.itemChanged()
            
    #def addSpiral(self, pos=None, name=None):
        #autoName = False
        #if name is None:
            #name = 'Point'
            #autoName = True
        #autoPos = False
        #if pos is None:
            #pos = [0,0]
            #autoPos = True
        #pt = pg.SpiralROI(pos)
        #self.addItem(pt, name,  autoPos,  autoName)
        #return pt

    #def addPoint(self, state=None):
        #if state is None:
            #state = {}
        #if state.get('name', None) is None:
            #state['name'] = self.getNextItemName('Point')
            
            
        #autoPos = False
        #if pos is None:
            #pos = [0,0]
            #autoPos = True
        #else:
            #s = self.pointSize()[0]
            #pos = [pos[i] - s/2.0 for i in [0, 1]]
        #pt = TargetPoint(name, pos, self.pointSize()[0], **opts)
        #self.addItem(pt, autoPosition=autoPos, parent=parent)
        #return pt
        
    #def addGrid(self, state=None):
        #if state is None:
            #state = {}
        #if name is None:
            #name = self.getNextItemName('Grid')
            
        #try:
            #ptSize, dispSize = self.pointSize()
        #except HelpfulException as ex:
            #exc = sys.exc_info()
            #if ex.kwargs.get('errId', None) == 1:
                #raise HelpfulException('%s has no calibration for %s, so cannot add a grid.' %(str(self.ui.laserCombo.currentText()), self.currentObjective), exc=exc)
            #else:
                #raise HelpfulException('Scanner is unable to find the size of grid points, so cannot add a grid.', exc=exc)
        #autoPos = False
        #if pos is None:
            #pos = [0,0]
            #autoPos = True
        #if size is None:
            #size = [ptSize*4, ptSize*4]
        #pt = TargetGrid(name, pos, size, ptSize, angle, **opts)
        #self.addItem(pt, autoPosition=autoPos, parent=parent)
        #return pt
    
    #def addOcclusion(self, state=None):
        #if state is None:
            #state = {}
        #auto = pos is None
        #if name is None:
            #name = self.getNextItemName('Occlusion')
            
        #if points is None:
            #s = self.pointSize()[0]
            #points = ([0,0], [0,s*3], [s*3,0])
        #if pos is None:
            #pos = [0,0]
        #item = TargetOcclusion(name, points, pos=pos, **opts)
        #self.addItem(item, autoPosition=auto, parent=parent)
        #return item

    def getNextItemName(self, base):
        ## Return the next available item name starting with base
        names = [item.name for item in self.items.values()]
        num = 1
        while True:
            name = base + str(num)
            if name not in names:
                return name
            num += 1
        
    #def addProgram(self, name=None): 
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
        
        

    def addItem(self, itemType, state=None):
        
        if state is None:
            state = {}
            
        if state.get('name', None) is None:
            state['name'] = self.getNextItemName(itemType)
            
        try:
            ptSize, dispSize = self.pointSize()
        except HelpfulException as ex:
            exc = sys.exc_info()
            if ex.kwargs.get('errId', None) == 1:
                raise HelpfulException('Cannot add items: %s is not calibrated for %s.' %(str(self.ui.laserCombo.currentText()), self.currentOpticState), exc=exc)
            else:
                raise
            
        state['ptSize'] = dispSize
        
        cls = {'Grid (beta)': Grid, 'Point': TargetPoint, 'Occlusion': TargetOcclusion, 'Grid':TargetGrid}[itemType]
        item = cls(**state)
        
        camMod = self.cameraModule()
        if camMod is None:
            raise HelpfulException("Cannot add control items until a camera module is available to display them.")
            return False

        item.opticState = self.currentOpticState
        self.items[item.name] = item
        
        #if autoPosition:
            #pos = None
        #else:
            #pos = item.pos()
        pos = state.get('pos', None)  ## if no position is given, the camera will automatically place the item in the middle fo the view
        camMod.ui.addItem(item, pos, [1, 1], 1000)
        #if parent is not None:
            #item.setParentItem(self.items[parent])
            
        self.positionCtrlGroup.addChild(item.parameters())
        
        item.sigStateChanged.connect(self.itemChanged)
        item.parameters().sigValueChanged.connect(self.itemActivationChanged)
        
        self.itemChanged(item)
        #self.updateDeviceTargetList(item)
        self.storeConfiguration()
        #self.updateGridLinkCombos()
        
    #def updateGridLinkCombos(self):
        #grids = [g for g in self.items.keys() if g[:4] == 'Grid']
        #for k,v in self.items.iteritems():
            #l = []
            #for g in grids:
                #if g != v.name:
                    #l.append(g)
            #l.sort()
            #v.updateLinkCombo(l)

    #def addTarget(self, t, name):
        #self.sequenceChanged()

    #def removeTarget(self, name):
        #pass
    
    #def delete(self):
        #item = self.ui.itemTree.currentItem()
        #if item is None:
            #logMsg("No item is selected, nothing was deleted.", msgType='error')
            #return
        #parent = item.parent()
        
        ### If this item has chilren, they are NOT deleted, but instead propagated to the next parent
        #if item.childCount() > 0:
            #for i in range(item.childCount()):
                
                ### Move item up in the tree
                #child = item.child(i)
                #self.ui.itemTree.prepareMove(child)
                #item.removeChild(child)
                #if parent is not None:
                    #parent.addChild(child)
                #else:
                    #self.ui.itemTree.addTopLevelItem(child)
                #self.ui.itemTree.recoverMove(child)
                
                ### reparent and reposition the graphics item
                #cgi = child.graphicsItem
                #pgi = cgi.parentItem()
                #pState = pgi.stateCopy()
                #transform = pg.SRTTransform({'pos': pState['pos'], 'angle': pState['angle']})
                
                ##pos = cgi.parentItem().parentItem().mapFromScene(cgi.scenePos())
                #cgi.setParentItem(cgi.parentItem().parentItem())
                #cgi.applyGlobalTransform(transform)
                ##cgi.setPos(pos, update=False)
                #child.graphicsItem.updateFamily()
                    
        #if parent == None:
            #item = self.ui.itemTree.takeTopLevelItem(self.ui.itemTree.indexOfTopLevelItem(item))
        #else:
            #item = parent.takeChild(parent.indexOfChild(item))
        ##item = self.ui.itemTree.takeItem(row)
        #if item is None:
            #return
        #name = str(item.text(0))
        ##self.dev.updateTarget(name, None)  ## inform the device that this target is no more
        #i = self.items[name]
        ##self.removeItemPoints(i)
        #i.scene().removeItem(i)
        #del self.items[name]
        ##self.occlusions.get(name)
        #self.sequenceChanged()
        #self.storeConfiguration()

    #def deleteAll(self, clearHistory=True):
        #self.ui.itemTree.clear()
        #for k in self.items:
            ##if clearHistory == True:
                ##self.dev.updateTarget(k, None)  ## inform the device that this target is no more
            #i = self.items[k]
            #if i.scene() is not None:
                #i.scene().removeItem(i)
            ##self.removeItemPoints(i)
        #self.items = {}
        ##self.occlusions = {}
        #self.sequenceChanged()
        #self.storeConfiguration()
        
    #def treeItemMoved(self, item, parent, index):
        ### called when items are dragged in the item tree
        
        #g = item.graphicsItem
        #if parent is not self.ui.itemTree.invisibleRootItem():
            #newPos = parent.graphicsItem.mapFromItem(g.parentItem(), g.pos())
            #g.setParentItem(parent.graphicsItem)
        #else:
            #newPos = g.viewPos()
            #print g.pos(), g.viewPos()
            #view = g.getViewBox()
            #g.scene().removeItem(g)
            #view.addItem(g)
            
        #g.setPos(newPos)
        #item.graphicsItem.updateFamily()
        ##print "tree Item Moved"
        #self.storeConfiguration()
        
        
    #def itemToggled(self, item, column=None):
        #name = str(item.text(0))
        #i = self.items[name]
        #if item.checkState(0) == QtCore.Qt.Checked:
            #i.setOpacity(1.0)  ## have to hide this way since we still want the children to be visible
            #for h in i.handles:
                #h['item'].setOpacity(1.0)
            #self.cameraModule().ui.update()
        #else:
            #i.setOpacity(0.0)
            #self.cameraModule().ui.update()
            #for h in i.handles:
                #h['item'].setOpacity(0.0)
            
        ##self.updateItemColor(item)
        #self.sequenceChanged()
        
    #def itemSelected(self, item, prev):
        #self.updateItemColor(item)
        #self.updateItemColor(prev)
        
    #def updateItemColor(self, item):
        #if item is None:
            #return
        #if item is self.ui.itemTree.currentItem():
            #color = QtGui.QColor(255, 255, 200)
        #else:
            #color = QtGui.QColor(200, 255, 100)
        #name = str(item.text(0))
        #self.items[name].setPen(QtGui.QPen(color))

    def itemMoved(self, item):
        self.itemChanged()
       

    def itemChanged(self, item=None):
        self.targets = None
        self.sequenceChanged()
        self.storeConfiguration()
        
    def itemActivationChanged(self, param, val):
        i = param.item
        if val:
            i.setOpacity(1.0)  ## have to hide this way since we still want the children to be visible
            for h in i.handles:
                h['item'].setOpacity(1.0)
        else:
            i.setOpacity(0.0)
            for h in i.handles:
                h['item'].setOpacity(0.0)
        self.cameraModule().ui.update()
            
        #self.updateItemColor(item)
        self.sequenceChanged()
        
    
    #def updateDeviceTargetList(self, item):
        #"""For keeping track of items outside of an individual scanner device. Allows multiple tasks to access the same items."""
        #name = str(item.name)
        #state = item.stateCopy()
        #if isinstance(item, TargetPoint):
            #pos = state['pos']
            #pos[0] += state['size'][0]/2.0
            #pos[1] += state['size'][1]/2.0
            #info = {'type': 'point', 'pos':pos }
        #elif isinstance(item, TargetGrid):
            #state['type'] = 'grid'
            #info = state
        #elif isinstance(item, TargetOcclusion):
            #info = {'type':'occlusion', 'pos':item.pos(), 'points': item.listPoints()}
        #elif isinstance(item, pg.SpiralROI):
            #info = {'type': 'spiral', 'pos': item.pos()}
        
        ##self.dev.updateTarget(name, info)

    
    def getTargetList(self):  ## should probably do some caching here.
        items = self.activeItems()
        locations = []
        occArea = QtGui.QPainterPath()
        for i in items:
            if isinstance(i, TargetOcclusion):
                occArea |= i.mapToView(i.shape())
            
        for i in items:
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
        self.sigSequenceChanged.emit(self.dev.name())
        self.updateTDPlot()
        
    def updateTDPlot(self):
        self.tdPlot.clear()
        state = self.stateGroup.state()
        minTime = state['minTime']
        minDist = state['minDist']
        
        #print 'minDist:', minDist, '   minTime:', minTime
        
        dist = np.arange(0, 0.001, 0.00002)
        cost = optimize.costFn(dist, minTime, minDist)

        #print 'dist:', dist
        #print 'cost:', cost
        
        self.tdPlot.plot(dist, cost)
        
        
    

    def recomputeClicked(self):
        try:
            self.ui.recomputeBtn.setEnabled(False)
            self.generateTargets()
        finally:
            self.ui.recomputeBtn.setEnabled(True)

    def generateTargets(self):
        #items = self.activeItems()
        #prof= Profiler('ScanerTaskGui.generateTargets()')
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
        deadTime = self.task.getParam('duration')

        state = self.stateGroup.state()
        minTime = state['minTime']
        minDist = state['minDist']

        #try:
        with pg.ProgressDialog("Computing random target sequence...", 0, 1000, busyCursor=True) as dlg:
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
        return [self.items[i] for i in self.items if self.items[i].isActive()]

    
    def taskStarted(self, params):
        """Task has started; color the current and previous targets"""
        pass
        #if 'targets' not in params:
            #return
        #t = params['targets']
        #self.currentTargetMarker.setRect
    
    def quit(self):
        #self.deleteAll(clearHistory = False)
        s = self.testTarget.scene()
        if s is not None:
            for item in self.items.values():
                s.removeItem(item)
            s.removeItem(self.testTarget)
            s.removeItem(self.spotMarker)
            for ctrl in self.programCtrls:
                for item in ctrl.getGraphicsItems():
                    s.removeItem(item)


        #QtCore.QObject.disconnect(getManager(), QtCore.SIGNAL('modulesChanged'), self.fillModuleList)
        #try:
            #getManager().sigModulesChanged.disconnect(self.fillModuleList)
        #except TypeError:
            #pass
            
        #if self.currentCamMod is not None:
            #try:
                #self.currentCamMod.ui.sigCameraScaleChanged.disconnect(self.opticStateChanged)
            #except:
                #pass
        #if self.currentScope is not None:
            #try:
                #self.currentScope.sigObjectiveChanged.disconnect(self.objectiveChanged)
            #except:
                #pass


class TargetPoint(pg.EllipseROI):
    
    sigStateChanged = QtCore.Signal(object)
    
    def __init__(self, name, ptSize, **args):
        self.name = name
        #if 'host' in args:
            #self.host = args.pop('host')
        
        pg.ROI.__init__(self, (0,0), [ptSize] * 2, movable=args.get('movable', True))
        self.aspectLocked = True
        self.overPen = None
        self.underPen = self.pen
        #self.treeItem = None
        self.setFlag(QtGui.QGraphicsItem.ItemIgnoresParentOpacity, True)
        #self.host = args.get('host', None)
        #self.rebuildOpts = args.get('rebuildOpts', {})
        self.params = pTypes.SimpleParameter(name=self.name, type='bool', value=args.get('active', True), removable=True, renamable=True, children=[
        ])
        self.params.item = self

    def isActive(self):
        return self.params.value()

    def parameters(self):
        return self.params
        
    #def updateInit(self, host):
        #self.treeItem.graphicsItem = self
        #self.treeItem.setText(3, "1")
        #self.host = host
        
    #def updateFamily(self):
        #pass
    
    #def resetParents(self):
        #"""For use when rebuilding scanner targets from the deviceTargetList"""
        #if self.rebuildOpts.get('parentName', None) is not None:
            #tw = self.treeItem.treeWidget()
            #parent = tw.findItems(self.rebuildOpts['parentName'], QtCore.Qt.MatchRecursive)[0]
            #tw.prepareMove(self.treeItem)
            #tw.invisibleRootItem().removeChild(self.treeItem)
            #parent.insertChild(0, self.treeItem)
            #tw.recoverMove(self.treeItem)
            #parent.setExpanded(True)
            #self.host.treeItemMoved(self.treeItem, parent, 0)
        
    def setPointSize(self, displaySize, realSize=None):
        s = displaySize / self.state['size'][0]
        self.scale(s, [0.5, 0.5])
        
    def listPoints(self):
        p = self.mapToView(self.boundingRect().center())
        return [(p.x(), p.y())]
        
    def setPen(self, pen):
        self.underPen = pen
        pg.EllipseROI.setPen(self, pen)
    
    def setTargetPen(self, index, pen):
        self.overPen = pen
        if pen is None:
            pen = self.underPen
        pg.EllipseROI.setPen(self, pen)
        
    #def stateCopy(self):
        #sc = pg.ROI.stateCopy(self)
        ##sc['displaySize'] = self.displaySize
        #return sc
    
    def resetParents(self):
        pass
        
    
    def saveState(self):
        pos = self.listPoints()[0]
        #pos = state['pos']
        #pos[0] += state['size'][0]/2.0
        #pos[1] += state['size'][1]/2.0
        return {'type': 'Point', 'pos': pos, 'active': self.params.value()}

class Grid(pg.CrosshairROI):
    
    sigStateChanged = QtCore.Signal(object)
    
    def __init__(self, name, ptSize, **args):
        self.name = name

        self.params = pTypes.SimpleParameter(name=self.name, type='bool', value=True, removable=True, renamable=True, children=[
            dict(name='layout', type='list', value=args.get('layout', 'Hexagonal'), values=['Square', 'Hexagonal']),
            dict(name='spacing', type='float', value=args.get('spacing', ptSize), suffix='m', siPrefix=True, bounds=[1e-9, None], step=10e-6),
            dict(name='Active Regions', type='group', addText="Add region...", addList=['Rectangle', 'Region'])
        ])
        
        self.params.item = self
        self.params.param('Active Regions').addNew = self.addActiveRegion
        self.rgns = []
        self.pointSize = ptSize
        self._points = []
        self.params.param('layout').sigStateChanged.connect(self.regeneratePoints)
        self.params.param('spacing').sigStateChanged.connect(self.regeneratePoints)
        #a = self.params
        #b = self.params.param('Active Regions')
        #c = self.params.param('Active Regions').sigChildRemoved
        #d = self.params.param('Active Regions').sigChildRemoved.connect
        self.params.param('Active Regions').sigChildRemoved.connect(self.rgnRemoved)
        
        pg.CrosshairROI.__init__(self, pos=(0,0), size=args.get('size', [ptSize*4]*2), angle=args.get('angle', 0), **args)
        self.sigRegionChanged.connect(self.regeneratePoints)
        self.params.sigValueChanged.connect(self.toggled)
        self.params.sigRemoved.connect(self.removed)
        
    def isActive(self):
        return self.params.value()
    
    def parameters(self):
        return self.params
    
    def setTargetPen(self, *args):
        pass
    
    def toggled(self, b):
        if b:
            self.show()
            for r in self.rgns:
                r.item.show()
        else:
            self.hide()
            for r in self.rgns:
                r.item.hide()
                
    def removed(self, child):
        #print "Grid.removed called.", self, child
        if child is self.params:
            for r in self.rgns:
                self.rgnRemoved(r)
    
    def addActiveRegion(self, rgnType):
        rgn = self.params.param('Active Regions').addChild(pTypes.SimpleParameter(name=self.getNextRgnName(rgnType), type='bool', value=True, removable=True, renamable=True))
        pos= self.getViewBox().viewRect().center() 
        size = self.params.param('spacing').value()*4
        
        if rgnType == 'Rectangle':
            roi = pg.ROI(pos=pos, size=size, angle=self.angle())
            roi.addScaleHandle([0, 0], [1, 1])
            roi.addScaleHandle([1, 1], [0, 0])
            roi.addRotateHandle([0, 1], [0.5, 0.5])
            roi.addRotateHandle([1, 0], [0.5, 0.5])
        elif rgnType == 'Region':
            roi = pg.PolyLineROI((pos, pos+pg.Point(0,1)*size, pos+pg.Point(1,0)*size), closed=True)
        else:
            raise Exception('Not sure how to add region of type:%s' %rgnType)
        
        rgn.item = roi
        self.rgns.append(rgn)
        self.getViewBox().addItem(roi)
        roi.sigRegionChanged.connect(self.regeneratePoints)
        rgn.sigValueChanged.connect(self.rgnToggled)
        self.regeneratePoints()
        
    def rgnToggled(self, rgn, b):
        if b:
            rgn.item.setVisible(True)
        else:
            rgn.item.setVisible(False)
            
    def rgnRemoved(self, rgn):
        roi = rgn.item
        roi.scene().removeItem(roi)
        
                                                     
    def getNextRgnName(self, base):
        ## Return the next available item name starting with base
        names = [rgn.name() for rgn in self.params.param('Active Regions').children()]
        num = 1
        while True:
            name = base + str(num)
            if name not in names:
                return name
            num += 1                  
            
    def listPoints(self):
        points = []
        activeArea = QtGui.QPainterPath()
        for rgn in self.rgns:
            if rgn.value():
                roi = rgn.item
                activeArea |= self.mapFromItem(roi, roi.shape())
            
        for pt in self._points:
            point = QtCore.QPointF(pt[0], pt[1])
            if activeArea.contains(point):
                points.append(pt)
        points = list(set(points))
        return points
    
    def setPointSize(self, displaySize, realSize):
        self.pointSize = displaySize
        #self.params.spacing.setDefault(displaySize)
        self.update()
    
    def regeneratePoints(self, emit=True):
        layout = self.params['layout']
        self._points = []
        #self.pens = []
        sepx = self.params['spacing']
        sq3 = 3. ** 0.5
        sepy = sq3 * sepx
        ## find 'snap' position of first spot
        for rgn in self.rgns:
            if not rgn.value():
                continue
            roi = rgn.item
            rect = self.mapFromItem(roi, roi.boundingRect()).boundingRect()
            newPos = self.getSnapPosition((rect.x(), rect.y()))
            x = newPos.x()-5*sepx
            y = newPos.y()-5*sepy
            w = rect.width()+5*sepx
            h = rect.height()+5*sepy
            if layout == "Hexagonal":
                self.generateGrid([x+self.pointSize*0.5, y+self.pointSize*0.5], [x+w, y+h], [sepx, sepy])  ## make every other row of the grid starting from top
                self.generateGrid([x+self.pointSize*0.5+0.5*sepx, y+0.5*self.pointSize + 0.5*sepy ],[x+w, y+h], [sepx, sepy]) ### make every other row of the grid starting with 2nd row
            elif layout == "Square":
                self.generateGrid([x+self.pointSize*0.5, y+self.pointSize*0.5], [x+w, y+h],[sepx, sepx]) ## points in x and y dimensions have same separation, so use same value.
          
        #self._points = list(set(self._points))
        #print "Grid.regeneratePoints", len(self._points)
        self.update()
        if emit:
            self.sigStateChanged.emit(self)
            
    def generateGrid(self, start, stop, sep):
        nx = int((stop[0] - (start[0] + self.pointSize*0.5) + sep[0]) / sep[0])
        ny = int((stop[1] - (start[1] + self.pointSize*0.5) + sep[1]) / sep[1])
        x = start[0]
        for i in range(nx):
            y = start[1]
            for j in range(ny):
                self._points.append((x, y))
                #self.pens.append(None)
                y += sep[1]
            x += sep[0]
            
    def getSnapPosition(self, pos):
        ## Given that pos has been requested, return the nearest snap-to position
        ## optionally, snap may be passed in to specify a rectangular snap grid.
        ## override this function for more interesting snap functionality..
    
        layout = self.params['layout']
        spacing = self.params['spacing']
        
        if layout == 'Square':
            snap = pg.Point(spacing, spacing)
            w = round(pos[0] / snap[0]) * snap[0]
            h = round(pos[1] / snap[1]) * snap[1]
            return pg.Point(w, h)
        
        elif layout == 'Hexagonal':
            snap1 = pg.Point(spacing, spacing*3.0**0.5)
            dx = 0.5*snap1[0]
            dy = 0.5*snap1[1]
            w1 = round(pos[0] / snap1[0]) * snap1[0]
            h1 = round(pos[1] / snap1[1]) * snap1[1]
            w2 = round((pos[0]-dx) / snap1[0]) * snap1[0] + dx
            h2 = round((pos[1]-dy) / snap1[1]) * snap1[1] + dy
            if (pg.Point(w1, h1)-pos).length() < (pg.Point(w2,h2) - pos).length():
                return pg.Point(w1, h1)
            else:
                return pg.Point(w2, h2)
    
    def boundingRect(self):
        rect= pg.CrosshairROI.boundingRect(self)
        for r in self.rgns:
            rect |= self.mapRectFromItem(r.item, r.item.boundingRect())
        rect.adjust(-self.pointSize, -self.pointSize, self.pointSize, self.pointSize)
        return rect
                                           
    def paint(self, p, *opts):
        pg.CrosshairROI.paint(self, p, *opts)
        ## paint spots
        p.scale(self.pointSize, self.pointSize) ## do scaling here because otherwise we end up with squares instead of circles (GL bug)
        p.setPen(pg.mkPen('w'))
        for pt in self.listPoints():
            p.drawEllipse(QtCore.QPointF(pt[0]/self.pointSize, pt[1]/self.pointSize), 0.5, 0.5)
            

class TargetGrid(pg.ROI):
    
    sigStateChanged = QtCore.Signal(object)
    
    def __init__(self, name, ptSize, **args):
        self.name = name
            
        ### These need to be initialized before the ROI is initialized because they are included in stateCopy(), which is called by ROI initialization.
        #self.gridSpacingSpin = SpinBox(step=0.1)
        #self.gridSpacingSpin.setValue(pd)
        #self.gridSpacingSpin = pg.SpinBox(value=ptSize, dec=True, step=0.1, suffix='m', siPrefix=True)
        #self.gridSpacing = self.gridSpacingSpin.value()
        #self.gridLayoutCombo = QtGui.QComboBox()
        #self.gridLayoutCombo.addItems(["Hexagonal", "Square"])
        #self.gridSpacingSpin.valueChanged.connect(self.updateGridSpacing)
        #self.gridLayoutCombo.currentIndexChanged.connect(self.regeneratePoints)
        #self.treeItem = None ## will become a QTreeWidgetItem when ScannerTaskGui runs addItem()
        
        self.params = pTypes.SimpleParameter(name=self.name, type='bool', value=True, removable=True, renamable=True, children=[
            dict(name='layout', type='list', value=args.get('layout', 'Hexagonal'), values=['Square', 'Hexagonal']),
            dict(name='spacing', type='float', value=args.get('spacing', ptSize), suffix='m', siPrefix=True, bounds=[1e-9, None], step=10e-6),
        ])
        self.params.item = self
        self.params.param('layout').sigStateChanged.connect(self.regeneratePoints)
        self.params.param('spacing').sigStateChanged.connect(self.regeneratePoints)
        pg.ROI.__init__(self, pos=(0,0), size=args.get('size', [ptSize*4]*2), angle=args.get('angle', 0))
        self.addScaleHandle([0, 0], [1, 1])
        self.addScaleHandle([1, 1], [0, 0])
        self.addRotateHandle([0, 1], [0.5, 0.5])
        self.addRotateHandle([1, 0], [0.5, 0.5])
        self.lastSize = self.state['size']
        #self.connect(QtCore.SIGNAL('regionChanged'), self.rgnChanged)
        self.sigRegionChanged.connect(self.rgnChanging)
        self.sigRegionChangeFinished.connect(self.rgnChanged)
        #self.params.param('snap-to grid').sigValueChanged.connect(self.linkGridChanged)
        self.points = []
        self.pens = []
        self.pointSize = ptSize
        #self.pointDisplaySize = self.pointSize
        self.oldDisplaySize = self.pointSize
        self.setFlag(QtGui.QGraphicsItem.ItemIgnoresParentOpacity, True)
        
        
        
        ## cache is not working in qt 4.7
        #self.setCacheMode(QtGui.QGraphicsItem.DeviceCoordinateCache)
        self.regeneratePoints()
        #self.rebuildOpts = rebuildOpts

    def isActive(self):
        return self.params.value()
    
    def parameters(self):
        return self.params
    
    #def updateLinkCombo(self, grids):
    #    print 'updating Combo:', self, grids
    #    self.params.param('snap-to grid').setLimits(['']+grids)
        
    #def linkGridChanged(self, val):
    #    print "linkGridChanged called.", self.name, val
    
    #def updateInit(self, host):
        #self.treeItem.graphicsItem = self ## make grid accessible from tree
        #self.treeItem.treeWidget().setItemWidget(self.treeItem, 1, self.gridSpacingSpin)
        #self.treeItem.treeWidget().setItemWidget(self.treeItem, 2, self.gridLayoutCombo)
        #self.treeItem.setText(3, "14")
        #self.host = host
        #self.pointSize, self.pointDisplaySize = self.host.pointSize()
        #if len(self.rebuildOpts) > 0:
            #self.gridSpacingSpin.setValue(self.rebuildOpts.get('gridSpacing', self.gridSpacing))
            #layout = self.rebuildOpts.get('gridLayout', "Hexagonal")
            #if layout == "Hexagonal":
                #self.gridLayoutCombo.setCurrentIndex(0)
            #elif layout == "Square":
                #self.gridLayoutCombo.setCurrentIndex(1)       
        #self.host.updateDeviceTargetList(self)
        #self.host.storeConfiguration()
    
    #def resetParents(self):
        #"""For use when rebuilding scanner targets from the deviceTargetList"""
        #if self.rebuildOpts.get('parentName', None) is not None:
            #tw = self.treeItem.treeWidget()
            #parent = tw.findItems(self.rebuildOpts['parentName'], QtCore.Qt.MatchRecursive)[0]
            #tw.prepareMove(self.treeItem)
            #tw.invisibleRootItem().removeChild(self.treeItem)
            #parent.insertChild(0, self.treeItem)
            #tw.recoverMove(self.treeItem)
            #parent.setExpanded(True)
            #self.host.treeItemMoved(self.treeItem, parent, 0)
            
           
            
    #def updateFamily(self):
        #if self.treeItem.parent() is not None:
            #self.gridSpacingSpin.setEnabled(False)
            #self.gridLayoutCombo.setEnabled(False)
            #self.parentGridSpacingSpin = self.treeItem.treeWidget().itemWidget(self.treeItem.parent(), 1)
            #self.parentGridSpacingSpin.valueChanged.connect(self.parentValueChanged)
            #self.parentGridLayoutCombo = self.treeItem.treeWidget().itemWidget(self.treeItem.parent(), 2)
            #self.parentGridLayoutCombo.currentIndexChanged.connect(self.parentValueChanged)
            #self.translateSnap = True
            #self.rotateAllowed = False
            #self.setAngle(0)
            ##self.setAngle(self.treeItem.parent().graphicsItem.stateCopy()['angle'])
            #self.parentValueChanged()
        #if self.treeItem.parent() is None:
            #self.gridSpacingSpin.setEnabled(True)
            #self.gridLayoutCombo.setEnabled(True)
            #self.translateSnap = False
            #self.rotateAllowed = True
        #self.host.updateDeviceTargetList(self)
        ##self.updateSnapSize()
        
    def parentValueChanged(self):
        ## called when any of the parent's grid parameters has changed (spacing, layout)
        if self.treeItem.parent() is not None:
            self.gridSpacingSpin.setValue(self.parentGridSpacingSpin.value())
            self.gridLayoutCombo.setCurrentIndex(self.parentGridLayoutCombo.currentIndex())
            
        
    #def updateGridSpacing(self):
        #self.gridSpacing = self.gridSpacingSpin.value()
        ##self.updateSnapSize()
        #self.regeneratePoints()
        
    #def updateSnapSize(self):
        #self.snapSizeX = self.pointSize * self.gridPacking
        #if self.gridLayoutCombo.currentText() == "Square":
            #self.snapSizeY = self.snapSizeX
        #elif self.gridLayoutCombo.currentText() == "Hexagonal":
            #self.snapSizeY = 0.5 * self.snapSizeX * 3.**0.5
        
    def setPointSize(self, displaySize, realSize):
        #size, displaySize = self.host.pointSize()
        self.pointSize = displaySize
        #self.pointDisplaySize = displaySize
        self.params.spacing.setDefault(displaySize)
        self.regeneratePoints()  ## point size changes the position of grid points even though spacing is unaffected.
        #self.update()
        
    def rgnChanging(self):
        if self.state['size'] != self.lastSize:
            self.regeneratePoints(emit=False)
            self.lastSize = self.state['size']
        
        
    def rgnChanged(self):
        self.sigStateChanged.emit(self)
            
    def getSnapPosition(self, pos, snap=None):
        ## Given that pos has been requested, return the nearest snap-to position
        ## optionally, snap may be passed in to specify a rectangular snap grid.
        ## override this function for more interesting snap functionality..
        
        if snap is None:
            if self.snapSize is None:
                return pos
        layout = self.params['layout']
        #layout = self.gridLayoutCombo.currentText()
        
        if layout == 'Square':
            #snap = Point(self.pointSize * self.gridPacking, self.pointSize*self.gridPacking)
            snap = pg.Point(self.gridSpacing, self.gridSpacing)
            w = round(pos[0] / snap[0]) * snap[0]
            h = round(pos[1] / snap[1]) * snap[1]
            return pg.Point(w, h)
        
        elif layout == 'Hexagonal':
            #snap1 = Point(self.pointSize*self.gridPacking, self.pointSize*self.gridPacking*3.0**0.5)
            snap1 = pg.Point(self.gridSpacing, self.gridSpacing*3.0**0.5)
            dx = 0.5*snap1[0]
            dy = 0.5*snap1[1]
            w1 = round(pos[0] / snap1[0]) * snap1[0]
            h1 = round(pos[1] / snap1[1]) * snap1[1]
            w2 = round((pos[0]-dx) / snap1[0]) * snap1[0] + dx
            h2 = round((pos[1]-dy) / snap1[1]) * snap1[1] + dy
            #snap2 = snap1 + Point(snap1[0]*0.5, snap1[1]/2)
            #w2 = round(pos[0] / snap2[0]) * snap2[0]
            #h2 = round(pos[1] / snap2[1]) * snap2[1] 
            if (pg.Point(w1, h1)-pos).length() < (pg.Point(w2,h2) - pos).length():
                return pg.Point(w1, h1)
            else:
                return pg.Point(w2, h2)
        

    def regeneratePoints(self, emit=True):
        #if self.treeItem is None:
            #layout = "Hexagonal"
        #else:
            #layout = self.gridLayoutCombo.currentText()
        layout = self.params['layout']
        self.points = []
        self.pens = []
        sq3 = 3. ** 0.5
        #sepx = self.pointSize * self.gridPacking
        sepx = self.params['spacing']
        sepy = sq3 * sepx

        if layout == "Hexagonal":
            self.generateGrid([self.pointSize*0.5, self.pointSize*0.5], [sepx, sepy])  ## make every other row of the grid starting from top
            self.generateGrid([self.pointSize*0.5+0.5*sepx, 0.5*self.pointSize + 0.5*sepy ], [sepx, sepy]) ### make every other row of the grid starting with 2nd row
        elif layout == "Square":
            self.generateGrid([self.pointSize*0.5, self.pointSize*0.5], [sepx, sepx]) ## points in x and y dimensions have same separation, so use same value.
      
        self.update()
        #self.emit(QtCore.SIGNAL('pointsChanged'), self)
        #if self.treeItem is not None:
            #self.treeItem.setText(3, str(len(self.points)))
        if emit:
            self.sigStateChanged.emit(self)
        
        
    def listPoints(self):
        pts = []
        for p in self.points:
            p1 = self.mapToView(pg.Point(p[0], p[1]))
            pts.append((p1.x(), p1.y()))
        
        return pts

    def setTargetPen(self, index, pen):
        self.pens[index] = pen
        self.update()

    def generateGrid(self, start, sep):
        nx = int((self.state['size'][0] - (start[0] + self.pointSize*0.5) + sep[0]) / sep[0])
        ny = int((self.state['size'][1] - (start[1] + self.pointSize*0.5) + sep[1]) / sep[1])
        x = start[0]
        for i in range(nx):
            y = start[1]
            for j in range(ny):
                self.points.append((x, y))
                self.pens.append(None)
                y += sep[1]
            x += sep[0]
        
    def boundingRect(self):
        #displaySize = max([self.oldDisplaySize, self.pointSize])
        #a = displaySize-self.pointSize
        #if a <= 0:
            #a = 0
        #self.oldDisplaySize = self.pointSize
        return QtCore.QRectF(0, 0, self.state['size'][0], self.state['size'][1]) #.adjusted(-a, -a, a, a)


    def paint(self, p, opt, widget):
        #graphicsItems.ROI.paint(self, p, opt, widget)
        ##draw rectangle
        p.save()
        r = QtCore.QRectF(0,0, self.state['size'][0], self.state['size'][1])
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(self.pen)
        p.translate(r.left(), r.top())
        p.scale(r.width(), r.height())
        p.drawRect(0, 0, 1, 1)
        p.restore()
        
        ## draw circles
        #ps2 = self.pointSize * 0.5
        #radius = self.pointSize*0.5
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
            p.drawEllipse(QtCore.QPointF(pt[0]/self.pointSize, pt[1]/self.pointSize), 0.5, 0.5)
            
    #def stateCopy(self):
        #sc = pg.ROI.stateCopy(self)
        #sc['gridSpacing'] = self.params['spacing']
        #sc['gridLayout'] = self.params['layout']
        #sc['active'] = self.params['active']
        ##if self.treeItem is not None:
            ##if self.treeItem.parent() is None:
                ##sc['parentName'] = None
            ##else:
                ##sc['parentName'] = self.treeItem.parent().text(0)
        #return sc
        #sc['displaySize'] = self.displaySize
        
    def saveState(self):
        state = pg.ROI.saveState(self)
        state['spacing'] = self.params['spacing']
        state['layout'] = self.params['layout']
        state['active'] = self.params.value()
        state['type'] = 'Grid'
        return state
        
class TargetOcclusion(pg.PolygonROI):
    
    
    sigStateChanged = QtCore.Signal(object)
    
    def __init__(self, name, ptSize, **args):
        self.name = name
        points = args.get('points', ([0,0], [0,ptSize*3], [ptSize*3,0]))
        pos = (0,0)
        pg.PolygonROI.__init__(self, points, pos)
        self.setZValue(10000000)
        self.params = pTypes.SimpleParameter(name=self.name, type='bool', value=True, removable=True, renamable=True, children=[
        ])
        self.params.item = self
        self.sigRegionChanged.connect(self.rgnChanged)

    def isActive(self):
        return self.params.value()

    def rgnChanged(self):
        self.sigStateChanged.emit(self)

    def parameters(self):
        return self.params
        
    #def updateInit(self, host):
        #self.treeItem.graphicsItem = self
        #self.host = host
        
    def setPointSize(self, size, realSize):
        pass
    
    def resetParents(self):
        pass
    
    def saveState(self):
        return {'type':'Occlusion', 'pos': (self.pos().x(), self.pos().y()), 'points': [(p.x(), p.y()) for p in self.listPoints()]}
    
    def listPoints(self):
        return []
    
class ProgramLineScan(QtCore.QObject):
    
    sigStateChanged = QtCore.Signal(object)
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        self.name = 'lineScan'
        ### These need to be initialized before the ROI is initialized because they are included in stateCopy(), which is called by ROI initialization.
        
        self.params = pTypes.SimpleParameter(name=self.name, autoIncrementName = True, type='bool', value=True, removable=True, renamable=True, children=[
            dict(name='length', type='float', value=1e-5, suffix='m', siPrefix=True, bounds=[1e-6, None], step=1e-6),
            dict(name='startTime', type='float', value=5e-2, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2),
            dict(name='sweepDuration', type='float', value=4e-3, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2),
            dict(name='retraceDuration', type='float', value=1e-3, suffix='s', siPrefix=True, bounds=[0., None], step=1e-3),
            dict(name='nScans', type='int', value=100, bounds=[1, None]),
            dict(name='endTime', type='float', value=5.5e-1, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2, readonly=True),
        ])
        self.params.ctrl = self        
        self.roi = pg.LineSegmentROI([[0.0, 0.0], [self.params['length'], self.params['length']]])
 #       print dir(self.roi)
        self.params.sigTreeStateChanged.connect(self.update)
        self.roi.sigRegionChangeFinished.connect(self.updateFromROI)
        
    def getGraphicsItems(self):
        return [self.roi]

    def isActive(self):
        return self.params.value()

    def setVisible(self, vis):
        if vis:
            self.roi.setOpacity(1.0)  ## have to hide this way since we still want the children to be visible
            for h in self.roi.handles:
                h['item'].setOpacity(1.0)
        else:
            self.roi.setOpacity(0.0)
            for h in self.roi.handles:
                h['item'].setOpacity(0.0)
#        self.cameraModule().ui.update()            
        
    def parameters(self):
        return self.params
    
    def update(self):
        self.params['endTime'] = self.params['startTime']+self.params['nScans']*(self.params['sweepDuration'] + self.params['retraceDuration'])
        self.setVisible(self.params.value())
            
    def updateFromROI(self):
        p =self.roi.listPoints()
        dist = (pg.Point(p[0])-pg.Point(p[1])).length()
        self.params['length'] = dist
        
    def generateTask(self):
        points = self.roi.listPoints() # in local coordinates local to roi.
        points = [self.roi.mapToView(p) for p in points] # convert to view points (as needed for scanner)
        return {'type': 'lineScan', 'active': self.isActive(), 'points': points, 'startTime': self.params['startTime'], 'sweepDuration': self.params['sweepDuration'], 
                'endTime': self.params['endTime'], 'retraceDuration': self.params['retraceDuration'], 'nScans': self.params['nScans']}

class MultiLineScanROI(pg.PolyLineROI):
    """ custom class over ROI polyline to allow alternate coloring of different segments
    """
    def addSegment(self, *args, **kwds):
        pg.PolyLineROI.addSegment(self, *args, **kwds)
        self.recolor()
    
    def removeSegment(self, *args, **kwds):
        pg.PolyLineROI.removeSegment(self, *args, **kwds)
        self.recolor()
    
    def recolor(self):
        for i, s in enumerate(self.segments):
            if i % 2 == 0:
                s.setPen(self.pen)
            else:
                s.setPen(pg.mkPen([75, 200, 75]))

class ProgramMultipleLineScan(QtCore.QObject):
    
    sigStateChanged = QtCore.Signal(object)
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        self.name = 'multipleLineScan'
        ### These need to be initialized before the ROI is initialized because they are included in stateCopy(), which is called by ROI initialization.
        
        self.params = pTypes.SimpleParameter(name=self.name, type='bool', value=True, removable=True, renamable=True, children=[
            dict(name='Length', type='float', value=1e-5, suffix='m', siPrefix=True, bounds=[1e-6, None], step=1e-6),
            dict(name='startTime', type='float', value=5e-2, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2),
            dict(name='sweepSpeed', type='float', value=1e-6, suffix='m/ms', siPrefix=True, bounds=[1e-8, None], minStep=5e-7, step=0.5, dec=True),
            dict(name='interSweepSpeed', type='float', value=5e-6, suffix='m/ms', siPrefix=True, bounds=[1e-8, None], minStep=5e-7, step=0.5, dec=True),
            dict(name='nScans', type='int', value=100, bounds=[1, None]),
            dict(name='endTime', type='float', value=5.5e-1, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2, readonly=True),
        ])
        self.params.ctrl = self        
        self.roi = MultiLineScanROI([[0.0, 0.0], [self.params['Length'], self.params['Length']]])
        self.roi.sigRegionChangeFinished.connect(self.updateFromROI)
 #       print dir(self.roi)
        self.params.sigTreeStateChanged.connect(self.update)
        
    def getGraphicsItems(self):
        return [self.roi]

    def isActive(self):
        return self.params.value()
    
    def setVisible(self, vis):
        if vis:
            self.roi.setOpacity(1.0)  ## have to hide this way since we still want the children to be visible
            for h in self.roi.handles:
                h['item'].setOpacity(1.0)
        else:
            self.roi.setOpacity(0.0)
            for h in self.roi.handles:
                h['item'].setOpacity(0.0)
                
    def parameters(self):
        return self.params
    
    def update(self):
        pts = self.roi.listPoints()
        scanTime = 0.
        interScanFlag = False
        for k in xrange(len(pts)): # loop through the list of points
            k2 = k + 1
            if k2 > len(pts)-1:
                k2 = 0
            dist = (pts[k]-pts[k2]).length()
            if interScanFlag is False:
                scanTime += dist/(self.params['sweepSpeed']*1000.)
            else:
                scanTime += dist/(self.params['interSweepSpeed']*1000.)
            interScanFlag = not interScanFlag
        self.params['endTime'] = self.params['startTime']+(self.params['nScans']*scanTime)
        self.setVisible(self.params.value())
    
    def updateFromROI(self):
        self.update()
    #p =self.roi.listPoints()
        #dist = (pg.Point(p[0])-pg.Point(p[1])).length()
        #self.params['length'] = dist
        
    def generateTask(self):
        points=self.roi.listPoints() # in local coordinates local to roi.
        points = [self.roi.mapToView(p) for p in points] # convert to view points (as needed for scanner)
        points = [(p.x(), p.y()) for p in points]   ## make sure we can write this data to HDF5 eventually..
        return {'type': 'multipleLineScan', 'active': self.isActive(), 'points': points, 'startTime': self.params['startTime'], 'sweepSpeed': self.params['sweepSpeed'], 
                'endTime': self.params['endTime'], 'interSweepSpeed': self.params['interSweepSpeed'], 'nScans': self.params['nScans']}
                
    
class ProgramRectScan(QtCore.QObject):
    
    sigStateChanged = QtCore.Signal(object)
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        self.name = 'rectScan'
        ### These need to be initialized before the ROI is initialized because they are included in stateCopy(), which is called by ROI initialization.
        
        self.params = pTypes.SimpleParameter(name=self.name, type='bool', value=True, removable=True, renamable=True, children=[
            dict(name='width', type='float', value=2e-5, suffix='m', siPrefix=True, bounds=[1e-6, None], step=1e-6),
            dict(name='height', type='float', value=1e-5, suffix='m', siPrefix=True, bounds=[1e-6, None], step=1e-6),
            dict(name='linespacing', type='float', value=4e-7, suffix='m', siPrefix=True, bounds=[2e-7, None], step=2e-7),
            dict(name='startTime', type='float', value=1e-2, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2),
            dict(name='endTime', type='float', value=5e-1, suffix='s', siPrefix=True, bounds=[0., None], step=1e-2),
            dict(name='nScans', type='int', value=10, bounds=[1, None]),
        ])
        self.params.ctrl = self
        #self.params.layout.sigStateChanged.connect(self.regeneratePoints)
        #self.params.spacing.sigStateChanged.connect(self.regeneratePoints)
        #pg.ROI.__init__(self, pos=(0,0), size=args.get('size', [ptSize*4]*2), angle=args.get('angle', 0))
        #self.addScaleHandle([0, 0], [1, 1])
        #self.addScaleHandle([1, 1], [0, 0])
        #self.addRotateHandle([0, 1], [0.5, 0.5])
        #self.addRotateHandle([1, 0], [0.5, 0.5])
        #self.lastSize = self.state['size']
        ##self.connect(QtCore.SIGNAL('regionChanged'), self.rgnChanged)
        #self.sigRegionChanged.connect(self.rgnChanging)
        #self.sigRegionChangeFinished.connect(self.rgnChanged)
        #self.points = []
        #self.pens = []
        #self.pointSize = ptSize
        ##self.pointDisplaySize = self.pointSize
        #self.oldDisplaySize = self.pointSize
        #self.setFlag(QtGui.QGraphicsItem.ItemIgnoresParentOpacity, True)
        
        #self.roi = pg.RectangleROI([self.params['width'], self.params['height']], pos=[0.0, 0.0] )
        self.roi = pg.ROI(size=[self.params['width'], self.params['height']], pos=[0.0, 0.0])
        self.roi.addScaleHandle([1,1], [0.5, 0.5])
        self.roi.addRotateHandle([0,0], [0.5, 0.5])
        self.params.sigTreeStateChanged.connect(self.update)
        self.roi.sigRegionChangeFinished.connect(self.updateFromROI)
        
    def getGraphicsItems(self):
        return [self.roi]

    def isActive(self):
        return self.params.value()
 
    def setVisible(self, vis):
        if vis:
            self.roi.setOpacity(1.0)  ## have to hide this way since we still want the children to be visible
            for h in self.roi.handles:
                h['item'].setOpacity(1.0)
        else:
            self.roi.setOpacity(0.0)
            for h in self.roi.handles:
                h['item'].setOpacity(0.0)
                
    def parameters(self):
        return self.params

    def update(self):
        self.setVisible(self.params.value())
    
    def updateFromROI(self):
        """ read the ROI rectangle width and height and repost
        in the parameter tree """
        state = self.roi.getState()
        w, h = state['size']
        self.params['width'] = w
        self.params['height'] = h
        
    def generateTask(self):
        state = self.roi.getState()
        w, h = state['size']
        p0 = pg.Point(0,0)
        p1 = pg.Point(w,0)
        p2 = pg.Point(0, h)
        points = [p0, p1, p2]
        points = [pg.Point(self.roi.mapToView(p)) for p in points] # convert to view points (as needed for scanner)
        return {'type': self.name, 'active': self.isActive(), 'points': points, 'startTime': self.params['startTime'], 
                'endTime': self.params['endTime'], 'nScans': self.params['nScans'],
                'lineSpacing': self.params['linespacing']}
        


