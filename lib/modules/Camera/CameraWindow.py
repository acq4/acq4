#!/usr/bin/python
# -*- coding: utf-8 -*-

## TODO
# reliable error messaging for missed frames
# Add fast/simple histogram 

from __future__ import with_statement

from CameraTemplate import Ui_MainWindow
from pyqtgraph.GraphicsView import *
from pyqtgraph.graphicsItems import *
from pyqtgraph.widgets import ROI
import ptime
from lib.filetypes.ImageFile import *
from Mutex import Mutex, MutexLocker
from PyQt4 import QtGui, QtCore
import scipy.ndimage
import time, types, os.path, re, sys
from pyqtgraph.functions import intColor
from debug import *
from metaarray import *
import sip
from SignalProxy import proxyConnect
from lib.Manager import getManager
import numpy as np

traceDepth = 0
def trace(func):
    #def newFunc(*args, **kargs):
        #global traceDepth
        #print "  "*traceDepth + func.__name__
        #traceDepth += 2
        #ret = func(*args, **kargs)
        #traceDepth -= 2
        #print "  "*traceDepth + func.__name__, "done"
        #return ret
    #return newFunc
    return func


class CamROI(ROI):
    def __init__(self, size, parent=None):
        ROI.__init__(self, pos=[0,0], size=size, maxBounds=QtCore.QRectF(0, 0, size[0], size[1]), scaleSnap=True, translateSnap=True, parent=parent)
        self.addScaleHandle([0, 0], [1, 1])
        self.addScaleHandle([1, 0], [0, 1])
        self.addScaleHandle([0, 1], [1, 0])
        self.addScaleHandle([1, 1], [0, 0])

class PlotROI(ROI):
    def __init__(self, pos, size):
        ROI.__init__(self, pos, size=size)
        self.addScaleHandle([1, 1], [0, 0])

class CameraWindow(QtGui.QMainWindow):
    
    sigCameraPosChanged = QtCore.Signal()
    sigCameraScaleChanged = QtCore.Signal()
    
    def __init__(self, module):
        
        self.module = module ## handle to the rest of the application
        self.cam = self.module.cam
        self.roi = None
        self.exposure = 0.001
        self.binning = 1
        self.region = None
        #self.acquireThread = self.module.cam.acqThread
        #self.acquireThread.setParam('binning', self.binning)
        #self.acquireThread.setParam('exposure', self.exposure)
        
        #self.frameBuffer = []
        self.lastPlotTime = None
        self.ROIs = []
        self.plotCurves = []
        
        
        self.nextFrame = None
        self.updateFrame = False
        self.currentFrame = None
        self.currentClipMask = None
        self.backgroundFrame = None
        self.lastDrawTime = None
        self.fps = None
        
        QtGui.QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        
        self.stateFile = os.path.join('modules', self.module.name + '_ui.cfg')
        uiState = getManager().readConfigFile(self.stateFile)
        if 'geometry' in uiState:
            geom = QtCore.QRect(*uiState['geometry'])
            self.setGeometry(geom)
        if 'window' in uiState:
            ws = QtCore.QByteArray.fromPercentEncoding(uiState['window'])
            self.restoreState(ws)
        
        
        self.ui.histogram.invertY(False)
        self.avgLevelLine = QtGui.QGraphicsLineItem()
        self.avgLevelLine.setPen(QtGui.QPen(QtGui.QColor(200, 200, 0)))
        self.histogramCurve = PlotCurveItem()
        self.ui.histogram.scene().addItem(self.avgLevelLine)
        self.ui.histogram.scene().addItem(self.histogramCurve)
        self.histogramCurve.rotate(90)
        self.histogramCurve.scale(1.0, -1.0)
        self.lastHistogramUpdate = 0
        
        
        self.ticks = [t[0] for t in self.ui.gradientWidget.listTicks()]
        self.ticks[0].colorChangeAllowed = False
        self.ticks[1].colorChangeAllowed = False
        self.ui.gradientWidget.allowAdd = False
        self.ui.gradientWidget.setTickColor(self.ticks[1], QtGui.QColor(255,255,255))
        self.ui.gradientWidget.setOrientation('right')
        
        ## Set up level thermo and scale widgets
        #self.scaleEngine = Qwt.QwtLinearScaleEngine()
        #self.ui.levelThermo.setScalePosition(Qwt.QwtThermo.NoScale)
        #self.ui.levelScale.setAlignment(Qwt.QwtScaleDraw.LeftScale)
        #self.ui.levelScale.setColorBarEnabled(True)
        #self.ui.levelScale.setColorBarWidth(10)
        
        
        ## Create device configuration dock 
        #dw = self.module.cam.deviceInterface()
        #dock = QtGui.QDockWidget(self)
        #dock.setFeatures(dock.DockWidgetMovable|dock.DockWidgetFloatable|dock.DockWidgetVerticalTitleBar)
        #dock.setWidget(dw)
        #self.addDockWidget(QtCore.Qt.TopDockWidgetArea, dock)
        
        self.hasQuit = False
        
        
        ## Set up camera graphicsView
        l = QtGui.QVBoxLayout(self.ui.graphicsWidget)
        l.setContentsMargins(0,0,0,0)
        self.gv = GraphicsView(self.ui.graphicsWidget)
        l.addWidget(self.gv)
        self.gv.enableMouse()

        #self.ui.plotWidget.setCanvasBackground(QtGui.QColor(0,0,0))
        #self.ui.plotWidget.enableAxis(Qwt.QwtPlot.xBottom, False)
        #self.ui.plotWidget.replot()

        self.setCentralWidget(self.ui.centralwidget)
        #self.scene = QtGui.QGraphicsScene(self)
        self.scene = self.gv.scene()
        
        #self.cameraItemGroup = QtGui.QGraphicsItemGroup()   ## Parent for objects which follow and scale with camera view
        #self.scopeItemGroup = QtGui.QGraphicsItemGroup()    ## Parent for objects which follow scope position
        self.cameraItemGroup = ItemGroup()
        self.scopeItemGroup = ItemGroup()
        
        self.scene.addItem(self.cameraItemGroup)
        self.scene.addItem(self.scopeItemGroup)
        self.scopeItemGroup.setZValue(10)
        self.cameraItemGroup.setZValue(0)
        self.imageItem = ImageItem(parent=self.cameraItemGroup)
        self.scene.addItem(self.imageItem)
        self.imageItem.setParentItem(self.cameraItemGroup)
        #self.cameraItemGroup.addToGroup(self.imageItem)
        
        #grid = Grid(self.gv)
        #self.scene.addItem(grid)
        
        self.scaleBar = ScaleBar(self.gv, 100e-6)
        self.scene.addItem(self.scaleBar)
        
        #self.gv.setScene(self.scene)
        self.gv.setAspectLocked(True)
        self.gv.invertY()
        self.AGCLastMax = None

        self.persistentFrames = []
        
        self.recLabel = QtGui.QLabel()
        self.fpsLabel = QtGui.QLabel()
        self.rgnLabel = QtGui.QLabel()
        self.xyLabel = QtGui.QLabel()
        self.tLabel = QtGui.QLabel()
        self.vLabel = QtGui.QLabel()
        font = self.xyLabel.font()
        font.setPointSize(8)
        self.recLabel.setFont(font)
        self.rgnLabel.setFont(font)
        self.xyLabel.setFont(font)
        self.tLabel.setFont(font)
        self.vLabel.setFont(font)
        self.fpsLabel.setFont(font)
        self.fpsLabel.setFixedWidth(50)
        self.vLabel.setFixedWidth(50)
        self.statusBar().addPermanentWidget(self.recLabel)
        self.statusBar().addPermanentWidget(self.xyLabel)
        self.statusBar().addPermanentWidget(self.rgnLabel)
        self.statusBar().addPermanentWidget(self.tLabel)
        self.statusBar().addPermanentWidget(self.vLabel)
        self.statusBar().addPermanentWidget(self.fpsLabel)
        self.show()
        self.openCamera()
        self.ui.plotWidget.resize(self.ui.plotWidget.size().width(), 40)
        
        self.setUiBinning(self.binning)
        self.ui.spinExposure.setValue(self.exposure)
        self.ui.spinExposure.setOpts(dec=True, step=1, minStep=100e-6, siPrefix=True, suffix='s', bounds=[0, 10])

        self.recordThread = RecordThread(self, self.module.manager)
        self.recordThread.start()



        ## Initialize values
        self.cameraCenter = self.scopeCenter = [self.camSize[0]*0.5, self.camSize[1]*0.5]
        self.cameraScale = [1, 1]
        self.gv.setRange(QtCore.QRect(0, 0, self.camSize[0], self.camSize[1]), lockAspect=True)
        
        
        self.roi = CamROI(self.camSize, parent=self.cameraItemGroup)
        #QtCore.QObject.connect(self.roi, QtCore.SIGNAL('regionChangeFinished'), self.updateRegion)
        #self.roi.connect(QtCore.SIGNAL('regionChangeFinished'), self.regionWidgetChanged)
        self.roi.sigRegionChangeFinished.connect(self.regionWidgetChanged)
        #self.cameraItemGroup.addToGroup(self.roi)
        self.roi.setZValue(10000)
        self.setRegion()
        
        self.borders = []
        scope = self.module.cam.getScopeDevice()
        if scope is not None:
            #QtCore.QObject.connect(scope, QtCore.SIGNAL('objectiveListChanged'), self.updateBorders)
            scope.sigObjectiveListChanged.connect(self.updateBorders)
            #QtCore.QObject.connect(scope, QtCore.SIGNAL('objectiveChanged'), self.objectiveChanged)
            self.cameraCenter = self.cam.getPosition()
            self.cameraScale = self.cam.getPixelSize()
            self.scopeCenter = self.cam.getPosition(justScope=True)
            #print self.cameraCenter, self.scopeCenter
            #self.updateBorders()
            self.centerView()
        self.updateBorders()
        
        #QtCore.QObject.connect(self.ui.btnAcquire, QtCore.SIGNAL('clicked()'), self.toggleAcquire)
        self.ui.btnAcquire.clicked.connect(self.toggleAcquire)
        #QtCore.QObject.connect(self.ui.btnRecord, QtCore.SIGNAL('toggled(bool)'), self.toggleRecord)
        self.ui.btnRecord.toggled.connect(self.toggleRecord)
        #QtCore.QObject.connect(self.ui.btnAutoGain, QtCore.SIGNAL('toggled(bool)'), self.toggleAutoGain)
        self.ui.btnAutoGain.toggled.connect(self.toggleAutoGain)
        #QtCore.QObject.connect(self.ui.btnFullFrame, QtCore.SIGNAL('clicked()'), self.setRegion)
        self.ui.btnFullFrame.clicked.connect(lambda: self.setRegion())
        
        #QtCore.QObject.connect(self.ui.spinBinning, QtCore.SIGNAL('valueChanged(int)'), self.setBinning)
        #QtCore.QObject.connect(self.ui.spinExposure, QtCore.SIGNAL('valueChanged(double)'), self.setExposure)
        
        ## Use delayed connection for these two widgets
        self.proxy1 = proxyConnect(self.ui.binningCombo, QtCore.SIGNAL('currentIndexChanged(int)'), self.setBinning)
        #QtCore.QObject.connect(self.ui.spinExposure, QtCore.SIGNAL('valueChanged(double)'), self.setExposure)  ## note that this signal (from lib.util.SpinBox) is delayed.
        self.ui.spinExposure.valueChanged.connect(self.setExposure)  ## note that this signal (from lib.util.SpinBox) is delayed.
        
        #QtCore.QObject.connect(self.recordThread, QtCore.SIGNAL('showMessage'), self.showMessage)
        self.recordThread.sigShowMessage.connect(self.showMessage)
        #QtCore.QObject.connect(self.recordThread, QtCore.SIGNAL('finished()'), self.recordThreadStopped)
        self.recordThread.finished.connect(self.recordThreadStopped)
        QtCore.QObject.connect(self.recordThread, QtCore.SIGNAL('recordingFailed'), self.recordingFailed, QtCore.Qt.QueuedConnection)
        #QtCore.QObject.connect(self.cam, QtCore.SIGNAL('newFrame'), self.newFrame)
        self.cam.sigNewFrame.connect(self.newFrame)
        #QtCore.QObject.connect(self.cam, QtCore.SIGNAL('cameraStopped'), self.cameraStopped)
        self.cam.sigCameraStopped.connect(self.cameraStopped)
        #QtCore.QObject.connect(self.cam, QtCore.SIGNAL('cameraStarted'), self.cameraStarted)
        self.cam.sigCameraStarted.connect(self.cameraStarted)
        #QtCore.QObject.connect(self.cam, QtCore.SIGNAL('showMessage'), self.showMessage)
        self.cam.sigShowMessage.connect(self.showMessage)
        #QtCore.QObject.connect(self.gv, QtCore.SIGNAL("sceneMouseMoved(PyQt_PyObject)"), self.setMouse)
        self.gv.sigSceneMouseMoved.connect(self.setMouse)
        #QtCore.QObject.connect(self.ui.btnDivideBackground, QtCore.SIGNAL('clicked()'), self.divideClicked)
        self.ui.btnDivideBackground.clicked.connect(self.divideClicked)
        
        #QtCore.QObject.connect(self.ui.btnAddROI, QtCore.SIGNAL('clicked()'), self.addROI)
        self.ui.btnAddROI.clicked.connect(self.addROI)
        #QtCore.QObject.connect(self.ui.btnClearROIs, QtCore.SIGNAL('clicked()'), self.clearROIs)
        self.ui.btnClearROIs.clicked.connect(self.clearROIs)
        #QtCore.QObject.connect(self.ui.checkEnableROIs, QtCore.SIGNAL('valueChanged(bool)'), self.enableROIsChanged)
        self.ui.checkEnableROIs.stateChanged.connect(self.enableROIsChanged)
        #QtCore.QObject.connect(self.ui.spinROITime, QtCore.SIGNAL('valueChanged(double)'), self.setROITime)
        self.ui.spinROITime.valueChanged.connect(self.setROITime)
        #QtCore.QObject.connect(self.ui.sliderWhiteLevel, QtCore.SIGNAL('valueChanged(int)'), self.levelsChanged)
        #QtCore.QObject.connect(self.ui.sliderBlackLevel, QtCore.SIGNAL('valueChanged(int)'), self.levelsChanged)
        #QtCore.QObject.connect(self.ui.gradientWidget, QtCore.SIGNAL('gradientChanged'), self.levelsChanged)
        self.ui.gradientWidget.sigGradientChanged.connect(self.levelsChanged)
        #QtCore.QObject.connect(self.ui.spinFlattenSize, QtCore.SIGNAL('valueChanged(int)'), self.requestFrameUpdate)
        self.ui.spinFlattenSize.valueChanged.connect(self.requestFrameUpdate)

        #QtCore.QObject.connect(self.ui.addFrameBtn, QtCore.SIGNAL('clicked()'), self.addPersistentFrame)
        self.ui.addFrameBtn.clicked.connect(self.addPersistentFrame)
        #QtCore.QObject.connect(self.ui.clearFramesBtn, QtCore.SIGNAL('clicked()'), self.clearPersistentFrames)
        self.ui.clearFramesBtn.clicked.connect(self.clearPersistentFrames)
        self.ui.scaleToImageBtn.clicked.connect(self.scaleToImage)
        
        self.ui.btnAutoGain.setChecked(True)
        
        ## Check for new frame updates every 10ms
        ## Some checks may be skipped even if there is a new frame waiting to avoid drawing more than 
        ## 60fps.
        self.frameTimer = QtCore.QTimer()
        self.frameTimer.timeout.connect(self.drawFrame)
        self.frameTimer.start(10)
        #QtCore.QTimer.singleShot(1, self.drawFrame)
        ## avoiding possible singleShot-induced crashes

    #@trace
    def updateBorders(self):
        """Draw the camera boundaries for each objective"""
        for b in self.borders:
            self.scene.removeItem(b)
        self.borders = []
        
        scope = self.module.cam.getScopeDevice()
        if scope is None:
            return
            
        bounds = self.module.cam.getBoundaries()
        for b in bounds:
            border = QtGui.QGraphicsRectItem(QtCore.QRectF(0, 0, 1, 1), self.scopeItemGroup)
            border.scale(b.width(), b.height())
            border.setPos(b.x(), b.y())
            border.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            border.setPen(QtGui.QPen(QtGui.QColor(50,80,80))) 
            border.setZValue(10)
            self.scopeItemGroup.resetTransform()
            #self.scopeItemGroup.addToGroup(border)
            self.borders.append(border)
        self.updateCameraDecorations()

    def centerView(self):
        center = self.cam.getPosition(justScope=True)
        bounds = self.cam.getBoundary().adjusted(center[0], center[1], center[0], center[1])
        self.gv.setRange(bounds, lockAspect=True)
        self.updateCameraDecorations()
        
    #@trace
    def addPersistentFrame(self):
        """Make a copy of the current camera frame and store it in the background"""
        px = self.imageItem.getPixmap()
        if px is None:
            return
        im = QtGui.QGraphicsPixmapItem(px.copy())
        im.setCacheMode(im.NoCache)
        if len(self.persistentFrames) == 0:
            z = -10000
        else:
            z = self.persistentFrames[-1].zValue() + 1
        
        (img, info) = self.currentFrame
        s = info['pixelSize']
        p = info['imagePosition']
        #r = info['region']
        #b = info['binning']
        self.persistentFrames.append(im)
        self.addItem(im, p, s, z)
        
    #@trace
    def addItem(self, item, pos, scale, z):
        """Adds an item into the scene. The image will be automatically scaled and translated when the scope moves."""
        
        self.scene.addItem(item)
        
        if pos is None:
            pos = self.cameraCenter
#        item.resetTransform()
        item.setPos(QtCore.QPointF(pos[0], pos[1]))
        item.scale(scale[0], scale[1])
        item.setZValue(z)
        #print pos, item.mapRectToScene(item.boundingRect())
    
    def removeItem(self, item):
        self.scene.removeItem(item)
    
    #@trace
    def  clearPersistentFrames(self):
        for i in self.persistentFrames:
            #self.persistentGroup1.removeFromGroup(i)
            self.scene.removeItem(i)
        self.persistentFrames = []

    #@trace
    def addROI(self):
        pen = QtGui.QPen(intColor(len(self.ROIs)))
        roi = PlotROI(self.cameraCenter, self.cameraScale[0] * 10)
        roi.setZValue(4000)
        roi.setPen(pen)
        self.scene.addItem(roi)
        plot = self.ui.plotWidget.plot(pen=pen)
        #plot = PlotCurve('roi%d'%len(self.ROIs))
        #plot.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
        #plot.attach(self.ui.plotWidget)
        self.ROIs.append({'roi': roi, 'plot': plot, 'vals': [], 'times': []})
        
    def clearROIs(self):
        for r in self.ROIs:
            self.scene.removeItem(r['roi'])
            self.ui.plotWidget.removeItem(r['plot'])
        self.ROIs = []
        
    #@trace
    def clearFrameBuffer(self):
        #self.frameBuffer = []
        for r in self.ROIs:
            r['vals'] = []
            r['times'] = []

    #@trace
    def enableROIsChanged(self, b):
        pass
    
    #@trace
    def setROITime(self, val):
        pass

    #@trace
    def toggleRecord(self, b):
        if b:
            self.ui.btnRecord.setChecked(True)
        else:
            #printExc( "Record button toggled off.")
            self.ui.btnRecord.setChecked(False)

    def recordThreadStopped(self):
        self.toggleRecord(False)
        self.ui.btnRecord.setEnabled(False)  ## Recording thread has stopped, can't record anymore.
        self.showMessage("Recording thread died! See console for error message.")
        #print "Recording thread stopped."
            
    def recordingFailed(self):
        self.toggleRecord(False)
        self.showMessage("Recording failed! See console for error message.")
        #print "Recording failed."

    #@trace
    def levelsChanged(self):
        #self.updateColorScale()
        self.requestFrameUpdate()

    #@trace
    def requestFrameUpdate(self):
        self.updateFrame = True

    #@trace
    def divideClicked(self):
        self.AGCLastMax = None
        self.AGCLastMin = None
        self.setLevelRange()
        if self.ui.btnDivideBackground.isChecked() and not self.ui.btnLockBackground.isChecked():
            self.backgroundFrame = None
        self.requestFrameUpdate()
            
    #@trace
    def showMessage(self, msg):
        self.ui.statusbar.showMessage(str(msg))
        
    def regionWidgetChanged(self, *args):
        self.updateRegion()

        
        
    #@trace
    def updateRegion(self, autoRestart=True):
        self.clearFrameBuffer()
        r = self.roi.parentBounds()
        newRegion = [int(r.left()), int(r.top()), int(r.width()), int(r.height())]
        if self.region != newRegion:
            self.region = newRegion
            self.cam.setParam('region', self.region, autoRestart=autoRestart)
        
    def scaleToImage(self):
        self.gv.scaleToImage(self.imageItem)
            
    #@trace
    def closeEvent(self, ev):
        self.quit()

    #@trace
    def quit(self):
        #self.frameTimer.stop()
        geom = self.geometry()
        uiState = {'window': str(self.saveState().toPercentEncoding()), 'geometry': [geom.x(), geom.y(), geom.width(), geom.height()]}
        getManager().writeConfigFile(uiState, self.stateFile)
        
        
        
        if self.hasQuit:
            return
        try:
            #QtCore.QObject.disconnect(self.recordThread, QtCore.SIGNAL('showMessage'), self.showMessage)
            
            self.recordThread.sigShowMessage.disconnect(self.showMessage)
            #QtCore.QObject.disconnect(self.recordThread, QtCore.SIGNAL('finished()'), self.recordThreadStopped)
            self.recordThread.finished.disconnect(self.recordThreadStopped)
            #QtCore.QObject.disconnect(self.recordThread, QtCore.SIGNAL('recordingFailed'), self.recordingFailed)
            self.recordThread.sigRecordingFailed.disconnect(self.recordingFailed)
        except TypeError:
            pass
        
        try:
            #QtCore.QObject.disconnect(self.cam, QtCore.SIGNAL('newFrame'), self.newFrame)
            self.cam.sigNewFrame.disconnect(self.newFrame)
            #QtCore.QObject.disconnect(self.cam, QtCore.SIGNAL('cameraStopped'), self.cameraStopped)
            self.cam.sigCameraStopped.disconnect(self.cameraStopped)
            #QtCore.QObject.disconnect(self.cam, QtCore.SIGNAL('cameraStarted'), self.cameraStarted)
            self.cam.sigCameraStarted.disconnect(self.cameraStarted)
            #QtCore.QObject.disconnect(self.cam, QtCore.SIGNAL('showMessage'), self.showMessage)
            self.cam.sigShowMessage.disconnect(self.showMessage)
        except TypeError:
            pass
        
        self.hasQuit = True
        if self.cam.isRunning():
            #print "Stopping acquisition thread.."
            self.cam.stop()
            if not self.cam.wait(10000):
                printExc("Timed out while waiting for acq thread exit!")
        if self.recordThread.isRunning():
            #print "Stopping recording thread.."
            self.recordThread.stop()
            #print "  requested stop, waiting for thread -- running=",self.recordThread.isRunning() 
            if not self.recordThread.wait(10000):
                raise Exception("Timed out while waiting for rec. thread exit!")
            #print "  record thread finished."
        del self.recordThread  ## Required due to cyclic reference
        #sip.delete(self)
        self.module.quit(fromUi=True)

    #@trace
    def setMouse(self, qpt=None):
        if qpt is None:
            if not hasattr(self, 'mouse'):
                return
            (x, y) = self.mouse
        else:
            x = qpt.x()
            y = qpt.y()
        self.mouse = [x, y]
        self.xyLabel.setText("X:%0.1fum Y:%0.1fum" % (x * 1e6, y * 1e6))
        
        img = self.imageItem.image
        if img is None:
            return
        pos = self.imageItem.mapFromScene(QtCore.QPointF(x, y))
        try:
            z = img[int(pos.x()), int(pos.y())]
        except IndexError:
            return
    
        if hasattr(z, 'shape') and len(z.shape) > 0:
            z = "Z:(%s, %s, %s)" % (str(z[0]), str(z[1]), str(z[2]))
        else:
            z = "Z:%s" % str(z)
        
        self.vLabel.setText(z)
            

    #@trace
    def cameraStopped(self):
        #printExc("ACQ stopped; stopping record.")
        #print "Signal sender was: ", self.sender()
        self.toggleRecord(False)
        if not self.ui.btnLockBackground.isChecked():
            self.backgroundFrame = None
        self.ui.btnAcquire.setChecked(False)
        self.ui.btnAcquire.setEnabled(True)
        
    #@trace
    def cameraStarted(self):
        self.AGCLastMax = None
        self.AGCLastMin = None
        self.ui.btnAcquire.setChecked(True)
        self.ui.btnAcquire.setEnabled(True)

    #@trace
    def setBinning(self, ind=None, autoRestart=True):
        """Set camera's binning value. If ind is specified, it is the index from binningCombo from which to grab the new binning value."""
        #sys.stdout.write("+")
        self.backgroundFrame = None
        if ind is not None:
            self.binning = int(self.ui.binningCombo.itemText(ind))
        self.cam.setParam('binning', (self.binning, self.binning), autoRestart=autoRestart)
        #self.acquireThread.reset()
        self.clearFrameBuffer()
        self.updateRgnLabel()
        #sys.stdout.write("- ")
        
    def setUiBinning(self, b):
        ind = self.ui.binningCombo.findText(str(b))
        if ind == -1:
            raise Exception("Binning mode %s not in list." % str(b))
        self.ui.binningCombo.setCurrentIndex(ind)
        
    #@trace
    def setExposure(self, e=None, autoRestart=True):
        #print "Set exposure:", e
        if e is not None:
            self.exposure = e
        self.cam.setParam('exposure', self.exposure, autoRestart=autoRestart)
        
    #@trace
    def openCamera(self, ind=0):
        try:
            #self.cam = self.module.cam.getCamera()
            self.bitDepth = self.cam.getParam('bitDepth')
            self.ui.histogram.setRange(QtCore.QRectF(0, 0, 1, 2**self.bitDepth))
            self.setLevelRange()
            self.camSize = self.cam.getParam('sensorSize')
            self.ui.statusbar.showMessage("Opened camera %s" % self.cam, 5000)
            self.scope = self.module.cam.getScopeDevice()
            
            try:
                bins = self.cam.listParams('binning')[0][0]
            except:
                bins = self.cam.listParams('binningX')[0]
            bins.sort()
            bins.reverse()
            for b in bins:
                self.ui.binningCombo.addItem(str(b))
            
            
        except:
            self.ui.statusbar.showMessage("Error opening camera")
            raise
    

    #@trace
    def updateCameraDecorations(self):
        ps = self.cameraScale
        pos = self.cameraCenter
        cs = self.camSize
        if ps is None:
            return
        
        ## move scope group
        m = QtGui.QTransform()
        m.translate(self.scopeCenter[0], self.scopeCenter[1])
        self.scopeItemGroup.setTransform(m)
        
        ## move and scale camera group
        m = QtGui.QTransform()
        m.translate(pos[0], pos[1])
        m.scale(ps[0], ps[1])
        m.translate(-cs[0]*0.5, -cs[1]*0.5)
        self.cameraItemGroup.setTransform(m)
        
        
        
        

    #@trace
    def setRegion(self, rgn=None):
        self.backgroundFrame = None
        if rgn is None:
            rgn = [0, 0, self.camSize[0]-1, self.camSize[1]-1]
        self.roi.setPos([rgn[0], rgn[1]])
        self.roi.setSize([self.camSize[0], self.camSize[1]])
        self.updateRegion()
            
    #@trace
    def updateRgnLabel(self):
        img = self.imageItem.image
        if img is None:
            return
        self.rgnLabel.setText('[%d, %d, %d, %d] %dx%d' % (self.region[0], self.region[1], (img.shape[0]-1)*self.binning, (img.shape[1]-1)*self.binning, self.binning, self.binning))
    
    #@trace
    def setLevelRange(self, rmin=None, rmax=None):
        if rmin is None:
            if self.ui.btnAutoGain.isChecked():
                rmin = 0.0
                rmax = 1.0
            else:
                if self.ui.btnDivideBackground.isChecked():
                    rmin = 0.0
                    rmax = 2.0
                else:
                    rmin = 0
                    rmax = 2**self.bitDepth - 1
        self.levelMin = rmin
        self.levelMax = rmax
        
    #@trace
    def getLevels(self):
        wl = self.levelMin + (self.levelMax-self.levelMin) * self.ui.gradientWidget.tickValue(self.ticks[1])
        bl = self.levelMin + (self.levelMax-self.levelMin) * self.ui.gradientWidget.tickValue(self.ticks[0])
        return (bl, wl)

    #@trace
    def toggleAutoGain(self, b):
        self.setLevelRange()

    #@trace
    def toggleAcquire(self):
        if self.ui.btnAcquire.isChecked():
            try:
                self.cam.setParam('triggerMode', 'Normal', autoRestart=False)
                self.setBinning(autoRestart=False)
                self.setExposure(autoRestart=False)
                self.updateRegion(autoRestart=False)
                self.cam.start()
            except:
                self.ui.btnAcquire.setChecked(False)
                printExc("Error starting camera:")
                
        else:
            #print "ACQ untoggled, stop record"
            self.toggleRecord(False)
            self.cam.stop()
            
    #@trace
    def addPlotFrame(self, frame):
        #sys.stdout.write('+')
        prof = Profiler('CameraWindow.addPlotFrame', disabled=True)
        if self.imageItem.width() is None:
            return
        
        ## Get rid of old frames
        minTime = None
        now = ptime.time()
        #if len(self.frameBuffer) > 0:
            #while len(self.frameBuffer) > 0 and self.frameBuffer[0][1]['time'] < (now-self.ui.spinROITime.value()):
                #self.frameBuffer.pop(0)
        for r in self.ROIs:
            #print " >>", r['times'], now, frame[1]['time'], self.ui.spinROITime.value(), now-self.ui.spinROITime.value()
            while len(r['times']) > 0 and r['times'][0] < (now-self.ui.spinROITime.value()):
                r['times'].pop(0)
                r['vals'].pop(0)
            #print " <<", r['times']
            if len(r['times']) > 0 and (minTime is None or r['times'][0] < minTime):
                minTime = r['times'][0]
        if minTime is None:
            minTime = frame[1]['time']
                
        prof.mark('remove old frames')
            
        ## add new frame
        draw = False
        if self.lastPlotTime is None or now - self.lastPlotTime > 0.05:
            draw = True
            self.lastPlotTime = now
            
        for r in self.ROIs:
            d = r['roi'].getArrayRegion(frame[0], self.imageItem, axes=(0,1))
            prof.mark('get array rgn')
            if d is None:
                continue
            if d.size < 1:
                val = 0
            else:
                val = d.mean()
            r['vals'].append(val)
            r['times'].append(frame[1]['time'])
            prof.mark('append')
            if draw:
                r['plot'].setData(array(r['times'])-minTime, r['vals'])
                prof.mark('draw')
        prof.finish()
    
            
    #@trace
    def newFrame(self, frame):
        #if hasattr(self.acquireThread, 'fps') and self.acquireThread.fps is not None:
        #print "    New frame", frame[1]['id']
        lf = None
        if self.nextFrame is not None:
            lf = self.nextFrame
        elif self.currentFrame is not None:
            lf = self.currentFrame
            
        if lf is not None:
            fps = frame[1]['fps']
            if fps is not None:
                #print self.fps, 1.0/dt
                if self.fps is None:
                    self.fps = fps
                else:
                    self.fps = 1.0 / (0.9/self.fps + 0.1/fps)  ## inversion is necessary because dt varies linearly, but fps varies hyperbolically
                self.fpsLabel.setText('%02.2ffps' % self.fps)
        
        ## Update ROI plots, if any
        if self.ui.checkEnableROIs.isChecked():
            self.addPlotFrame(frame)
            
        ## self.nextFrame gets picked up by drawFrame() at some point
        self.nextFrame = frame


    #@trace
    def drawFrame(self):
        if self.hasQuit:
            return
        #sys.stdout.write('+')
        try:
            
            ## If we last drew a frame < 1/30s ago, return.
            t = ptime.time()
            if (self.lastDrawTime is not None) and (t - self.lastDrawTime < .033333):
                #sys.stdout.write('-')
                return
            ## if there is no new frame and no controls have changed, just exit
            if not self.updateFrame and self.nextFrame is None:
                #sys.stdout.write('-')
                return
            self.updateFrame = False
            
            ## If there are no new frames and no previous frames, then there is nothing to draw.
            if self.currentFrame is None and self.nextFrame is None:
                #sys.stdout.write('-')
                return
            
            ## We will now draw a new frame (even if the frame is unchanged)
            self.lastDrawTime = t
            
            ## Handle the next available frame, if there is one.
            if self.nextFrame is not None:
                self.currentFrame = self.nextFrame
                self.nextFrame = None
                (data, info) = self.currentFrame
                self.currentClipMask = (data >= (2**self.bitDepth * 0.99)) ##mask of pixels that are saturated
                
                #self.ui.levelThermo.setValue(int(data.mean()))
                
                ## If background division is enabled, mix the current frame into the background frame
                if self.ui.btnDivideBackground.isChecked():
                    if self.backgroundFrame is None or self.backgroundFrame.shape != data.shape:
                        self.backgroundFrame = data.astype(float)
                    if not self.ui.btnLockBackground.isChecked():
                        s = 1.0 - 1.0 / (self.ui.spinFilterTime.value()+1.0)
                        self.backgroundFrame *= s
                        self.backgroundFrame += data * (1.0-s)

            (data, info) = self.currentFrame

            
            ## divide the background out of the current frame if needed
            if self.ui.btnDivideBackground.isChecked() and self.backgroundFrame is not None:
                b = self.ui.spinFlattenSize.value()
                if b > 0.0:
                    data = data / scipy.ndimage.gaussian_filter(self.backgroundFrame, (b, b))
                else: 
                    data = data / self.backgroundFrame
            
            ## determine black/white levels from level controls
            (bl, wl) = self.getLevels()
            if self.ui.btnAutoGain.isChecked():
                cw = self.ui.spinAutoGainCenterWeight.value()
                (w,h) = data.shape
                center = data[w/2.-w/6.:w/2.+w/6., h/2.-h/6.:h/2.+h/6.]
                minVal = data.min() * (1.0-cw) + center.min() * cw
                maxVal = data.max() * (1.0-cw) + center.max() * cw
                
                
                if self.AGCLastMax is None:
                    minVal = minVal
                    maxVal = maxVal
                else:
                    s = 1.0 - 1.0 / (self.ui.spinAutoGainSpeed.value()+1.0)
                    minVal = self.AGCLastMin * s + minVal * (1.0-s)
                    maxVal = self.AGCLastMax * s + maxVal * (1.0-s)
                self.AGCLastMax = maxVal
                self.AGCLastMin = minVal
                
                wl = minVal + (maxVal-minVal) * wl
                bl = minVal + (maxVal-minVal) * bl
            
            
            ## Update histogram plot
            #self.updateHistogram(self.currentFrame[0], wl, bl)
            
            ## Translate and scale image based on ROI and binning
            m = QtGui.QTransform()
            m.translate(info['region'][0], info['region'][1])
            m.scale(*info['binning'])
            #m.translate(info['imagePosition'][0], info['imagePosition'][1])
            #m.scale(info['pixelSize'][0], info['pixelSize'][1])
            
            ## update image in viewport
            self.imageItem.updateImage(data, clipMask=self.currentClipMask, white=wl, black=bl)
            self.imageItem.setTransform(m)

            ## Update viewport to correct for scope movement/scaling
            #print info
            newPos = info['centerPosition']
            if newPos != self.cameraCenter:
                #self.emit(QtCore.SIGNAL('cameraPosChanged'))
                self.sigCameraPosChanged.emit()
                diff = [newPos[0] - self.cameraCenter[0], newPos[1] - self.cameraCenter[1]]
                self.gv.translate(diff[0], diff[1])
                #print "translate view:", diff
                self.cameraCenter = newPos
                self.scopeCenter = info['scopePosition']
                self.updateCameraDecorations()
            
            newScale = [info['pixelSize'][0] / info['binning'][0], info['pixelSize'][1] / info['binning'][1]]
            if newScale != self.cameraScale:  ## If scale has changed, re-center on new objective.
                #self.emit(QtCore.SIGNAL('cameraScaleChanged'))
                self.sigCameraScaleChanged.emit()
                self.centerView()
                #diff = [self.cameraScale[0] / newScale[0], self.cameraScale[1] /newScale[1]]
                #self.gv.scale(diff[0], diff[1])
                self.cameraScale = newScale
                self.updateCameraDecorations()
            #print self.cameraCenter, self.scopeCenter


            ## update info for pixel under mouse pointer
            self.setMouse()
            self.updateRgnLabel()

            
            #if self.ui.checkEnableROIs.isChecked():
                #self.ui.plotWidget.replot()


        except:
            printExc('Error while drawing new frames:')
        finally:
            pass
            #QtCore.QTimer.singleShot(1, self.drawFrame)
            ## avoiding possible singleShot-induced crashes

        #sys.stdout.write('!')

    def updateHistogram(self, data, wl, bl):
        now = time.time()
        if now > self.lastHistogramUpdate + 0.2:
            avg = data.mean()
            self.avgLevelLine.setLine(0.0, avg, 1.0, avg)
            h = histogram(data, bins=500)
            self.histogramCurve.setData(y=h[0].astype(float32)/h[0].max(), x=h[1][:-1])
            self.lastHistogramUpdate = now

class RecordThread(QtCore.QThread):
    
    sigShowMessage = QtCore.Signal(object)
    sigRecordingFailed = QtCore.Signal()
    
    def __init__(self, ui, manager):
        QtCore.QThread.__init__(self)
        self.ui = ui
        self.m = manager
        #QtCore.QObject.connect(self.ui.cam, QtCore.SIGNAL('newFrame'), self.newCamFrame)
        self.ui.cam.sigNewFrame.connect(self.newCamFrame)
        
        #QtCore.QObject.connect(ui.ui.btnRecord, QtCore.SIGNAL('toggled(bool)'), self.toggleRecord)
        ui.ui.btnRecord.toggled.connect(self.toggleRecord)
        #QtCore.QObject.connect(ui.ui.btnSnap, QtCore.SIGNAL('clicked()'), self.snapClicked)
        ui.ui.btnSnap.clicked.connect(self.snapClicked)
        self.recording = False
        self.recordStart = False
        self.recordStop = False
        self.takeSnap = False
        self.currentRecord = None
        
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.camLock = Mutex()
        self.newCamFrames = []
        
    def newCamFrame(self, frame=None):
        if frame is None:
            return
        with MutexLocker(self.lock):
            newRec = self.recordStart
            lastRec = self.recordStop
            if self.recordStop:
                self.recording = False
                self.recordStop = False
            if self.recordStart:
                self.recordStart = False
                self.recording = True
            recording = self.recording or lastRec
            takeSnap = self.takeSnap
            self.takeSnap = False
            recFile = self.currentRecord
        if recording or takeSnap:
            with MutexLocker(self.camLock):
                ## remember the record/snap/storageDir states since they might change 
                ## before the write thread gets to this frame
                self.newCamFrames.append({'frame': frame, 'record': recording, 'snap': takeSnap, 'newRec': newRec, 'lastRec': lastRec})
    
    def run(self):
        self.stopThread = False
        
        while True:
            try:
                with MutexLocker(self.camLock):
                    handleCamFrames = self.newCamFrames[:]
                    self.newCamFrames = []
            except:
                printExc('Error in camera recording thread:')
                break
            
            try:
                while len(handleCamFrames) > 0:
                    self.handleCamFrame(handleCamFrames.pop(0))
            except:
                printExc('Error in camera recording thread:')
                self.toggleRecord(False)
                #self.emit(QtCore.SIGNAL('recordingFailed'))
                self.sigRecordingFailed.emit()
                
            time.sleep(10e-3)
            
            #print "  RecordThread run: stop check"
            with MutexLocker(self.lock) as l:
                #print "  RecordThread run:   got lock"
                if self.stopThread:
                    #print "  RecordThread run:   stop requested, exiting loop"
                    break
            #print "  RecordThread run:   unlocked"


    def handleCamFrame(self, frame):
        (data, info) = frame['frame']
        
        if frame['record']:
            if frame['newRec']:
                self.startFrameTime = info['time']
                
            arrayInfo = [
                {'name': 'Time', 'values': array([info['time'] - self.startFrameTime]), 'units': 's'},
                {'name': 'X'},
                {'name': 'Y'}
            ]
            #import random
            #if random.random() < 0.01:
                #raise Exception("TEST")
            data = MetaArray(data[np.newaxis], info=arrayInfo)
            if frame['newRec']:
                self.currentRecord = self.m.getCurrentDir().writeFile(data, 'video', autoIncrement=True, info=info, appendAxis='Time')
                self.currentFrameNum = 0
            else:
                data.write(self.currentRecord.name(), appendAxis='Time')
                s = 1.0/self.currentFrameNum
                
            self.showMessage("Recording %s - %d" % (self.currentRecord.name(), self.currentFrameNum))
            
            self.currentFrameNum += 1
            
            if frame['lastRec']:
                dur = info['time'] - self.startFrameTime
                self.currentRecord.setInfo({'frames': self.currentFrameNum, 'duration': dur, 'averageFPS': ((self.currentFrameNum-1)/dur)})
                self.showMessage('Finished recording %s - %d frames, %02f sec' % (self.currentRecord.name(), self.currentFrameNum, dur)) 
                
            
        
        if frame['snap']:
            fileName = 'image.tif'
            
            fh = self.m.getCurrentDir().writeFile(data, fileName, info, fileType="ImageFile", autoIncrement=True)
            fn = fh.name()
            self.showMessage("Saved image %s" % fn)
            with MutexLocker(self.lock):
                self.takeSnap = False
    
    def showMessage(self, msg):
        #self.emit(QtCore.SIGNAL('showMessage'), msg)
        self.sigShowMessage.emit(msg)
    
    def snapClicked(self):
        with MutexLocker(self.lock):
            self.takeSnap = True

    def toggleRecord(self, b):
        with MutexLocker(self.lock):
            if b:
                self.recordStart = True
            else:
                if self.recording:
                    self.recordStop = True

    def stop(self):
        #QtCore.QObject.disconnect(self.ui.cam, QtCore.SIGNAL('newFrame'), self.newCamFrame)
        self.ui.cam.sigNewFrame.disconnect(self.newCamFrame)
        #print "RecordThread stop.."    
        with MutexLocker(self.lock):
        #print "  RecordThread stop: locked"
            self.stopThread = True
        #print "  RecordThread stop: done"
        
