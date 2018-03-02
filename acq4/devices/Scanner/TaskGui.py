# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
import random
import numpy as np
from . import optimize ## for determining random scan patterns
import os, sys

import acq4.pyqtgraph as pg
from acq4.devices.Device import TaskGui
from acq4.Manager import getManager, logMsg, logExc
from acq4.util.debug import Profiler
from acq4.util.HelpfulException import HelpfulException
import acq4.pyqtgraph.parametertree.parameterTypes as pTypes
from acq4.pyqtgraph.parametertree import Parameter, ParameterTree, ParameterItem, registerParameterType

from .TaskTemplate import Ui_Form
from .scan_program import ScanProgram, ScanProgramPreview

### Error IDs:
###  1: Could not find spot size from calibration. (from ScannerTaskGui.pointSize)


class PositionCtrlGroup(pTypes.GroupParameter):
    sigAddNewRequested = Qt.Signal(object, object)
    def __init__(self):
        opts = {
            'name': 'Position Controls',
            'type': 'group',
            'addText': "Add Control..",
            'addList': ['Point', 'Grid', 'Occlusion'],

        }
        pTypes.GroupParameter.__init__(self, **opts)
    
    def addNew(self, typ):
        self.sigAddNewRequested.emit(self, typ)




class ScannerTaskGui(TaskGui):
    
    #sigSequenceChanged = Qt.Signal(object)  ## inherited from Device
    
    def __init__(self, dev, taskRunner):
        TaskGui.__init__(self, dev, taskRunner)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        dm = getManager()
        self.targets = None
        self.items = {}
        self.haveCalibration = True   ## whether there is a calibration for the current combination of laser/optics
        self.currentOpticState = None
        self.currentCamMod = None
        self.displaySize = {}  ## maps (laser,opticState) : display size
                               ## since this setting is remembered for each objective.
        
        # Make sure DQ appears in this task
        daqName = dev.getDaqName()
        taskRunner.getDevice(daqName)
        
        ## Populate module/device lists, auto-select based on device defaults 
        self.defCam = None
        if 'defaultCamera' in self.dev.config:
            self.defCam = self.dev.config['defaultCamera']
        defLaser = None
        if 'defaultLaser' in self.dev.config:
            defLaser = self.dev.config['defaultLaser']
            
        daqDev = dev.getDaqName()
        self.daqUI = taskRunner.getDevice(daqDev)

        self.ui.cameraCombo.setTypes(['cameraModule'])
        self.ui.laserCombo.setTypes(['laser'])
        
        self.positionCtrlGroup = PositionCtrlGroup()
        self.positionCtrlGroup.sigAddNewRequested.connect(self.addPositionCtrl)
        self.ui.itemTree.setParameters(self.positionCtrlGroup, showTop=False)
        self.positionCtrlGroup.sigChildRemoved.connect(self.positionCtrlRemoved)
        self.ui.spotSequenceGroup.setCollapsed(True)
        self.ui.spotDisplayGroup.setCollapsed(True)
        
        self.scanProgram = ScanProgram()
        self.scanProgram.setDevices(scanner=self.dev)
        self.ui.programTree.setParameters(self.scanProgram.ctrlParameter(), showTop=False)

        ## Set up SpinBoxes
        self.ui.minTimeSpin.setOpts(dec=True, step=1, minStep=1e-3, siPrefix=True, suffix='s', bounds=[0, 50])
        self.ui.minDistSpin.setOpts(dec=True, step=1, minStep=1e-6, siPrefix=True, suffix='m', bounds=[0, 10e-3])
        self.ui.sizeSpin.setOpts(dec=True, step=1, minStep=1e-6, siPrefix=True, suffix='m', bounds=[1e-9, 1e-3])
        ## Create state group for saving/restoring state
        self.stateGroup = pg.WidgetGroup([
            (self.ui.cameraCombo,),
            (self.ui.laserCombo,),
            (self.ui.minTimeSpin, 'minTime'),
            (self.ui.minDistSpin, 'minDist'),
            (self.ui.simulateShutterCheck, 'simulateShutter'),
            (self.ui.sizeSpin, 'spotSize'),
            (self.ui.enablePosCtrlCheck, 'enablePosCtrl'),
            (self.ui.enableScanProgCheck, 'enableScanProg'),
        ])
        self.stateGroup.setState({'minTime': 10, 'minDist': 500e-6, 'sizeSpin':100e-6})
        self.tdPlot = self.ui.tdPlotWidget.plotItem
        self.tdPlot.setLabel('bottom', text="Distance", units='m')
        self.tdPlot.setLabel('left', text="Wait time", units='s')

        self.ui.scanProgramSplitter.setSizes([600, 100])
        self.ui.programTimeline.setDownsampling(True)
        ## Note we use lambda functions for all these clicks to strip out the arg sent with the signal
        
        self.ui.showPosCtrlCheck.toggled.connect(self.showPosCtrls)
        self.ui.cameraCombo.currentIndexChanged.connect(self.camModChanged)
        self.ui.laserCombo.currentIndexChanged.connect(self.laserDevChanged)
        self.ui.sizeFromCalibrationRadio.toggled.connect(self.updateSpotSizes)
        self.ui.sizeSpin.valueChanged.connect(self.sizeSpinEdited)
        self.ui.minTimeSpin.valueChanged.connect(self.sequenceChanged)
        self.ui.minDistSpin.valueChanged.connect(self.sequenceChanged)
        self.ui.recomputeBtn.clicked.connect(self.recomputeClicked)
        self.ui.loadConfigBtn.clicked.connect(self.loadConfiguration)
        self.ui.previewBtn.toggled.connect(self.previewProgram)
        self.ui.enablePosCtrlCheck.toggled.connect(self.enablePosCtrlToggled)
        self.ui.enableScanProgCheck.toggled.connect(self.enableScanProgToggled)
        self.ui.showLastSpotCheck.toggled.connect(self.showLastSpotToggled)
        self.ui.programPreviewSlider.valueChanged.connect(self.previewRateChanged)
        
        self.dev.sigGlobalSubdeviceChanged.connect(self.opticStateChanged)
        
        self.testTarget = TargetPoint(name="Test", ptSize=100e-6)
        self.testTarget.setPen(Qt.QPen(Qt.QColor(255, 200, 200)))
        self.spotMarker = TargetPoint(name="Last", ptSize=100e-6, movable=False)
        self.spotMarker.setPen(pg.mkPen(color=(255,255,255), width = 2))

        self.spotMarker.hide()
        self.laserDevChanged()  # also updates spot sizes
        self.camModChanged()
        self.updateTDPlot()
            
        #self.ui.simulateShutterCheck.setChecked(False)
        if 'offVoltage' not in self.dev.config: ## we don't have a voltage for virtual shuttering
            self.ui.simulateShutterCheck.setChecked(False)
            self.ui.simulateShutterCheck.setEnabled(False)

        self.daqChanged(self.daqUI.currentState())
        self.daqUI.sigChanged.connect(self.daqChanged)

            
    def setHaveCalibration(self, have):
        self.haveCalibration = have
        self.updateVisibility()

    def enablePosCtrlToggled(self, b):
        self.ui.positionCtrlGroup.setVisible(b)
        self.updateVisibility()

    def enableScanProgToggled(self, b):
        self.ui.scanProgramGroup.setVisible(b)
        self.updateVisibility()

    def showPosCtrls(self, b):
        self.updateVisibility()
        
    def updateVisibility(self):
        b = self.haveCalibration and self.ui.showPosCtrlCheck.isChecked() and self.ui.enablePosCtrlCheck.isChecked()
        for k in self.items:
            self.items[k].setVisible(b)
        self.testTarget.setVisible(b)

        b = self.haveCalibration and self.ui.enableScanProgCheck.isChecked()
        self.scanProgram.setVisible(b)
        
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
        
        self.scanProgram.setCanvas(camMod.ui)

    def daqChanged(self, state):
        # Something changed in DAQ; check that we have the correct sample rate
        self.scanProgram.setSampling(state['rate'], state['numPts'], state['downsample'])
        
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
            
            for i in self.items.values():
                active = (i.opticState == opticState)
                i.parameters().setValue(active)
                    

    def laserDevChanged(self):
        ## called when laser device combo is changed
        ## need to update spot size
        self.updateSpotSizes()
        self.scanProgram.setDevices(laser=self.ui.laserCombo.getSelectedObj())

        
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
            #camMod = self.cameraModule()
            #if camMod is None:
                #return (1,1)
            #cam = camMod.config['camDev']
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
        if self.ui.enableScanProgCheck.isChecked():
            state['program'] = self.scanProgram.saveState()
        return state
                
    def restoreState(self, state):
        self.stateGroup.setState(state)
        if 'items' in state:
            for itemState in state['items']:
                typ = itemState['type']
                self.addItem(typ, itemState)
        if 'program' in state:
            self.scanProgram.restoreState(state['program'])
    
    def storeConfiguration(self):
        state = self.saveState(saveItems=True)
        self.dev.writeConfigFile(state, 'lastConfig')

    def loadConfiguration(self):
        state = self.dev.readConfigFile('lastConfig')
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
            raise Exception('No camera module selected, cannot build task.')
        
        if params is None or 'targets' not in params:
            target = self.testTarget.listPoints()[0]
            delay = 0
        else:
            if self.targets is None:
                self.generateTargets()
            #print "targets:", len(self.targets), params['targets']
            (target, delay) = self.targets[params['targets']]
            
        if len(self.scanProgram.components) == 0: # doing regular position mapping
            task = {
                'position': target, 
                'minWaitTime': delay,
                #'camera': self.cameraModule().config['camDev'], 
                'laser': self.ui.laserCombo.currentText(),
              #  'simulateShutter': self.ui.simulateShutterCheck.isChecked(), ## was commented out... 
                'duration': self.taskRunner.getParam('duration')
            }
        else: # doing programmed scans
            cmd = self.scanProgram.generateVoltageArray()
            task = {
                'minWaitTime': delay,
                'xCommand': cmd[:, 0],
                'yCommand': cmd[:, 1],
                'program': self.scanProgram.saveState(),
            }
        
        return task
    
    def showLastSpotToggled(self, b):
        self.spotMarker.setVisible(b)
        
    def handleResult(self, result, params):
        #print 'ScannerTaskGui.handleResult() result:', result
        if 'position' in result:
            pos = result['position']
            ss = result['spotSize']
            self.spotMarker.setPos((pos[0]-ss*0.5, pos[1]-ss*0.5))
        #print 'handleResult'
        getManager().scanResult=result
    
    def addPositionCtrl(self, param, typ):
        ## called when "Add Control.." combo is changed
        self.addItem(typ)

    def positionCtrlRemoved(self, param, ctrl):
        item = ctrl.item
        item.scene().removeItem(item)
        try:
            item.parameters().sigValueChanged.disconnect(self.itemActivationChanged)
        except TypeError:
            pass
        del self.items[item.name]
        #self.updateGridLinkCombos()
        self.itemChanged()
        
    def getNextItemName(self, base):
        ## Return the next available item name starting with base
        names = [item.name for item in self.items.values()]
        num = 1
        while True:
            name = base + str(num)
            if name not in names:
                return name
            num += 1
        
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
        
        cls = {'Grid': Grid, 'Point': TargetPoint, 'Occlusion': TargetOcclusion}[itemType]
        item = cls(**state)
        
        camMod = self.cameraModule()
        if camMod is None:
            raise HelpfulException("Cannot add control items until a camera module is available to display them.")
            return False

        item.opticState = self.currentOpticState
        self.items[item.name] = item
        
        pos = state.get('pos', None)  ## if no position is given, the camera will automatically place the item in the middle fo the view
        camMod.ui.addItem(item, pos, [1, 1], 1000)
            
        self.positionCtrlGroup.addChild(item.parameters())
        
        item.sigStateChanged.connect(self.itemChanged)
        item.parameters().sigValueChanged.connect(self.itemActivationChanged)
        
        self.itemChanged(item)
        self.storeConfiguration()
        
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
            
        self.sequenceChanged()
    
    def getTargetList(self):  ## should probably do some caching here.
        items = self.activeItems()
        locations = []
        occArea = Qt.QPainterPath()
        for i in items:
            if isinstance(i, TargetOcclusion):
                occArea |= i.mapToView(i.shape())
            
        for i in items:
            pts = i.listPoints()
            for j in range(len(pts)):
                p = pts[j]
                point = Qt.QPointF(p[0], p[1])
                if occArea.contains(point):
                    i.setTargetPen(j, Qt.QPen(Qt.QColor(0,0,0,160)))
                else:
                    locations.append(p)
                    i.setTargetPen(j, None)
        return locations

    def sequenceChanged(self):
        self.targets = None
        self.sigSequenceChanged.emit(self.dev.name())
        self.updateTDPlot()
        
    def updateTDPlot(self):
        self.tdPlot.clear()
        state = self.stateGroup.state()
        minTime = state['minTime']
        minDist = state['minDist']
        
        dist = np.arange(0, 0.001, 0.00002)
        cost = optimize.costFn(dist, minTime, minDist)
        
        self.tdPlot.plot(dist, cost)

    def recomputeClicked(self):
        try:
            self.ui.recomputeBtn.setEnabled(False)
            self.generateTargets()
        finally:
            self.ui.recomputeBtn.setEnabled(True)

    def generateTargets(self):
        self.targets = []
        locations = self.getTargetList()
        
        bestTime = None
        bestSolution = None

        nTries = np.clip(int(10 - len(locations)/20), 1, 10)
        
        ## About to compute order/timing of targets; display a progress dialog
        deadTime = self.taskRunner.getParam('duration')

        state = self.stateGroup.state()
        minTime = state['minTime']
        minDist = state['minDist']

        with pg.ProgressDialog("Computing random target sequence...", 0, 1000, busyCursor=True) as dlg:
            for i in range(nTries):
                ## Run in a remote process for a little speedup
                for n, m in optimize.opt2(locations, minTime, minDist, deadTime, greed=1.0):
                    ## we can update the progress dialog here.
                    if m is None:
                        solution = n
                    else:
                        prg = int(((i/float(nTries)) + ((n/float(m))/float(nTries))) * 1000)
                        dlg.setValue(prg)
                        if dlg.wasCanceled():
                            raise Exception("Target sequence computation canceled by user.")
                time = sum([l[1] for l in solution])
                if bestTime is None or time < bestTime:
                    bestTime = time
                    bestSolution = solution[:]
        
        self.targets = bestSolution
        self.ui.timeLabel.setText('Total time: %0.1f sec'% bestTime)
        
    def activeItems(self):
        return [self.items[i] for i in self.items if self.items[i].isActive()]
    
    def taskStarted(self, params):
        """Task has started; color the current and previous targets"""
        pass

    def previewProgram(self, b):
        if b:
            if self.currentCamMod is None:
                canvas = None
            else:
                canvas = self.currentCamMod.window()
            self.scanProgram.preview.setRate(self._previewRate())
            self.scanProgram.preview.start(canvas, self.ui.programTimeline)
        else:
            self.scanProgram.preview.stop()

    def _previewRate(self):
        rs = self.ui.programPreviewSlider
        return 10 ** (3. * ((float(rs.value()) / rs.maximum()) - 1))
    
    def previewRateChanged(self):
        self.scanProgram.preview.setRate(self._previewRate())

    def quit(self):
        s = self.testTarget.scene()
        if s is not None:
            for item in self.items.values():
                item.close()
            s.removeItem(self.testTarget)
            s.removeItem(self.spotMarker)
        self.scanProgram.close()


class TargetPoint(pg.EllipseROI):
    
    sigStateChanged = Qt.Signal(object)
    
    def __init__(self, name, ptSize, **args):
        self.name = name
        #if 'host' in args:
            #self.host = args.pop('host')
        
        pg.EllipseROI.__init__(self, (0,0), [ptSize] * 2, movable=args.get('movable', True))
        self.aspectLocked = True
        self.overPen = None
        self.underPen = self.pen
        self.setFlag(Qt.QGraphicsItem.ItemIgnoresParentOpacity, True)
        self.params = pTypes.SimpleParameter(name=self.name, type='bool', value=args.get('active', True), removable=True, renamable=True, children=[
        ])
        self.params.item = self

    def _addHandles(self):
        pass

    def isActive(self):
        return self.params.value()

    def parameters(self):
        return self.params
        
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
        
    def resetParents(self):
        pass
    
    def saveState(self):
        pos = self.listPoints()[0]
        return {'type': 'Point', 'pos': pos, 'active': self.params.value()}

    def close(self):
        if self.scene() is not None:
            self.scene().removeItem(self)
        self.dev.sigGlobalSubdeviceChanged.disconnect(self.opticStateChanged)


class Grid(pg.CrosshairROI):
    
    sigStateChanged = Qt.Signal(object)
    
    def __init__(self, name, ptSize, **args):
        pg.CrosshairROI.__init__(self, pos=(0,0), size=args.get('size', [ptSize*4]*2), angle=args.get('angle', 0), **args)

        self.name = name

        self.params = pTypes.SimpleParameter(name=self.name, type='bool', value=True, removable=True, renamable=True, children=[
            dict(name='layout', type='list', value=args.get('layout', 'Hexagonal'), values=['Square', 'Hexagonal']),
            dict(name='spacing', type='float', value=args.get('spacing', ptSize), suffix='m', siPrefix=True, bounds=[1e-9, None], step=10e-6),
            dict(name='Active Regions', type='group', addText="Add region...", addList=['Rectangle', 'Polygon'])
        ])
        
        self.params.item = self
        self.params.param('Active Regions').addNew = self.addActiveRegion
        self.rgns = []
        self.pointSize = ptSize
        self._points = np.empty((0,2), dtype=float)
        self._scene = None 
        self._scatter = pg.ScatterPlotItem(pxMode=False, brush=None, antialias=True)
        self._scatter.setParentItem(self)
        self._needScatterUpdate = False
        self.params.param('layout').sigStateChanged.connect(self.invalidatePoints)
        self.params.param('spacing').sigStateChanged.connect(self.invalidatePoints)
        self.params.param('Active Regions').sigChildRemoved.connect(self.rgnRemoved)
        
        self.sigRegionChanged.connect(self.invalidatePoints)
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

    def setVisible(self, vis):
        super(Grid, self).setVisible(vis)
        for rgn in self.rgns:
            rgn.item.setVisible(vis)
                
    def removed(self, child):
        #print "Grid.removed called.", self, child
        self.close()

    def close(self):
        for r in self.rgns:
            self.rgnRemoved(self, r)
        if self.scene() is not None:
            self.scene().removeItem(self)
    
    def addActiveRegion(self, rgnType):
        rgn = pTypes.SimpleParameter(name=rgnType, autoIncrementName=True,
                                     type='bool', value=True, 
                                     removable=True, renamable=True)
        self.params.param('Active Regions').addChild(rgn)
        pos = self.getViewBox().viewRect().center() 
        size = self.params.param('spacing').value()*4
        
        if rgnType == 'Rectangle':
            roi = pg.ROI(pos=pos, size=size, angle=self.angle())
            roi.addScaleHandle([0, 0], [1, 1])
            roi.addScaleHandle([1, 1], [0, 0])
            roi.addRotateHandle([0, 1], [0.5, 0.5])
            roi.addRotateHandle([1, 0], [0.5, 0.5])
        elif rgnType == 'Polygon':
            roi = pg.PolyLineROI((pos, pos+pg.Point(0,1)*size, pos+pg.Point(1,0)*size), closed=True)
        else:
            raise Exception('Not sure how to add region of type:%s' % rgnType)
        
        rgn.item = roi
        self.rgns.append(rgn)
        self.getViewBox().addItem(roi)
        roi.sigRegionChanged.connect(self.invalidatePoints)
        roi.sigRegionChangeFinished.connect(self.stateChangeFinished)
        rgn.sigValueChanged.connect(self.rgnToggled)
        self.invalidatePoints()
        self.stateChangeFinished()
        
    def rgnToggled(self, rgn, b):
        if b:
            rgn.item.setVisible(True)
        else:
            rgn.item.setVisible(False)
        self.invalidatePoints()
        self.stateChangeFinished()
            
    def rgnRemoved(self, grp, rgn):
        roi = rgn.item
        if roi.scene() is not None:
            roi.scene().removeItem(roi)
        self.invalidatePoints()
        self.stateChangeFinished()
        
    def localPoints(self):
        """Return active points in local coordinate system"""
        if self._points is None:
            self._points = self.generatePoints()
        return self._points
            
    def listPoints(self):
        pts = self.localPoints()
        tr = self.viewTransform()
        if tr is None:
            return []
        return pg.transformCoordinates(tr, pts, transpose=True)
    
    def setPointSize(self, displaySize, realSize):
        self.pointSize = displaySize
        self.update()
    
    def invalidatePoints(self):
        self._points = None
        self._needScatterUpdate = True
        # Update points in scatter plot item
        # NOTE: we would rather have this inside prepareForPaint()
        if self._needScatterUpdate:
            pts = self.localPoints()
            self._scatter.setData(x=pts[:,0], y=pts[:,1], size=self.pointSize)
            self._needScatterUpdate = False
        self.update()
        
    def stateChangeFinished(self):
        self.sigStateChanged.emit(self)

    def generatePoints(self):
        layout = self.params['layout']

        # get x/y point spacing
        sepx = sepy = self.params['spacing']
        if layout == 'Hexagonal':
            sepy *= 3 ** 0.5

        # find grid points inside each active region
        points = []
        for rgn in self.rgns:
            if not rgn.value():
                continue
            roi = rgn.item
            rect = self.mapFromItem(roi, roi.boundingRect()).boundingRect()

            ## find 'snap' position of first spot
            newPos = self.getSnapPosition((rect.x(), rect.y()))
            x = newPos.x() - sepx
            y = newPos.y() - sepy
            w = rect.width() + 2*sepx
            h = rect.height() + 2*sepy

            if layout == "Hexagonal":
                # make every other row of the grid starting from top
                points.append(self.generateGrid([x, y], [x+w, y+h], [sepx, sepy]))
                # make every other row of the grid starting with 2nd row
                points.append(self.generateGrid([x+0.5*sepx, y+0.5*sepy], [x+w, y+h], [sepx, sepy]))
            elif layout == "Square":
                points.append(self.generateGrid([x, y], [x+w, y+h], [sepx, sepx]))
        
        if len(points) == 0:
            return np.empty((0,2), dtype=float)
        
        # stack all point arrays together
        points = np.ascontiguousarray(np.vstack(points))
        # do some rounding to make it easier to detect duplicate points
        dec = int(-np.log10(sepx) + 4)
        points = np.round(points, dec)
        # keep only unique points
        points = np.unique(points.view(dtype=[('x', float), ('y', float)]))        
        # convert back to normal array
        points = points.view(dtype=float).reshape(len(points), 2)
        
        # get shape of total active region
        activeArea = Qt.QPainterPath()
        for rgn in self.rgns:
            if rgn.value():
                roi = rgn.item
                activeArea |= self.mapFromItem(roi, roi.shape())
            
        # filter for all points within active region
        mask = np.array([activeArea.contains(pg.Point(*pt)) for pt in points], dtype=bool)

        return points[mask]

    @staticmethod
    def generateGrid(start, stop, sep):
        # 2-dimensional range(); generates point locations filling a rectangular grid
        nx = int((stop[0] - start[0]) / sep[0]) + 1
        ny = int((stop[1] - start[1]) / sep[1]) + 1
        pts = np.mgrid[0:nx,0:ny].reshape(2, nx*ny).transpose()
        pts = pts * np.array(sep).reshape(1, 2)
        pts += np.array(start).reshape(1, 2)
        return pts
    
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
    
    def parentChanged(self):
        # Called when grid gets a new parent or scene. 
        super(Grid, self).parentChanged()
        if self._scene is not None:
            try:
                self._scene.sigPrepareForPaint.disconnect(self.prepareForPaint)
            except TypeError:
                pass
        self._scene = self.scene()
        if self._scene is not None:
            self._scene.sigPrepareForPaint.connect(self.prepareForPaint)

    def prepareForPaint(self):
        # NOTE: disabled for now because this generates artifacts. 
        # Update is moved to invalidatePoints()
        pass
        ## Update points in scatter plot item
        #if self._needScatterUpdate:
            #pts = self.localPoints()
            #self._scatter.setData(x=pts[:,0], y=pts[:,1], size=self.pointSize)
            #self._needScatterUpdate = False

        
class TargetOcclusion(pg.PolygonROI):
    
    sigStateChanged = Qt.Signal(object)
    
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
        
    def setPointSize(self, size, realSize):
        pass
    
    def resetParents(self):
        pass
    
    def saveState(self):
        return {'type':'Occlusion', 'pos': (self.pos().x(), self.pos().y()), 'points': [(p.x(), p.y()) for p in self.listPoints()]}
    
    def listPoints(self):
        return []

    def close(self):
        if self.scene() is not None:
            self.scene().removeItem(self)
    
                



