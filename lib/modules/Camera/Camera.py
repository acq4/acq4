#!/usr/bin/python
# -*- coding: utf-8 -*-

## TODO
# reliable error messaging for missed frames
# Add fast/simple histogram 
# region plots
# decrease displayed framerate gracefully

## workaround for dev libraries
#import sys
#sys.path = ["libs", "../pvcam", "../nidaq", "../cheader"] + sys.path


from CameraTemplate import Ui_MainWindow
#from ROPing import ROPWindow
from lib.util.qtgraph.GraphicsView import *
from lib.util.qtgraph.graphicsItems import *
from lib.util.qtgraph.widgets import ROI
import lib.util.ptime as ptime
from lib.filetypes.ImageFile import *
from PyQt4 import QtGui, QtCore
from PyQt4 import Qwt5 as Qwt
import scipy.ndimage
import time, types, os.path, re, sys
#if '--mock' in sys.argv:
    #sys.path = ['mock'] + sys.path
#import pvcam


class CamROI(ROI):
    def __init__(self, size):
        ROI.__init__(self, pos=[0,0], size=size, maxBounds=QtCore.QRectF(0, 0, size[0], size[1]), scaleSnap=True, translateSnap=True)
        self.addScaleHandle([0, 0], [1, 1])
        self.addScaleHandle([1, 0], [0, 1])
        self.addScaleHandle([0, 1], [1, 0])
        self.addScaleHandle([1, 1], [0, 0])

class PlotROI(ROI):
    def __init__(self, size):
        ROI.__init__(self, pos=[0,0], size=size, scaleSnap=True, translateSnap=True)
        self.addScaleHandle([1, 1], [0, 0])

class PVCamera(QtGui.QMainWindow):
    def __init__(self, module):
        self.module = module ## handle to the rest of the application
        
        self.roi = None
        self.exposure = 0.001
        self.binning = 1
        self.region = None
        #self.acquireThread = AcquireThread(self)
        self.acquireThread = self.module.cam.acqThread
        self.acquireThread.setParam('binning', self.binning)
        self.acquireThread.setParam('exposure', self.exposure)
        
        self.frameBuffer = []
        self.lastPlotTime = None
        self.ROIs = []
        self.plotCurves = []
        #self.ropWindow = ROPWindow(self)
        
        self.nextFrame = None
        self.currentFrame = None
        self.currentClipMask = None
        self.backgroundFrame = None
        self.lastDrawTime = None
        
        QtGui.QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        
        ## Create device configuration dock 
        dw = self.module.cam.deviceInterface()
        dock = QtGui.QDockWidget(self)
        dock.setFeatures(dock.DockWidgetMovable|dock.DockWidgetFloatable|dock.DockWidgetVerticalTitleBar)
        dock.setWidget(dw)
        self.addDockWidget(QtCore.Qt.TopDockWidgetArea, dock)
        
        
        self.recordThread = RecordThread(self, self.module.manager)
        self.recordThread.start()
        
        ## Set up camera graphicsView
        l = QtGui.QVBoxLayout(self.ui.graphicsWidget)
        l.setMargin(0)
        self.gv = GraphicsView(self.ui.graphicsWidget)
        l.addWidget(self.gv)

        self.ui.plotWidget.setCanvasBackground(QtGui.QColor(0,0,0))
        self.ui.plotWidget.enableAxis(Qwt.QwtPlot.xBottom, False)
        self.ui.plotWidget.replot()


        ## Set up plot graphicsView
        #l2 = QtGui.QVBoxLayout(self.ui.plotWidget)
        #l2.setMargin(0)
        #self.pgv = GraphicsView(self.ui.plotWidget)
        #l2.addWidget(self.pgv)

        self.setCentralWidget(self.ui.centralwidget)
        self.scene = QtGui.QGraphicsScene(self)
        #self.plotScene = QtGui.QGraphicsScene(self)
        #self.grid = Grid()
        #self.scene.addItem(self.grid)
        #self.grid.setZValue(-1)
        self.imageItem = ImageItem()
        self.scene.addItem(self.imageItem)
        #self.regionBox = self.scene.addRect(0,0,1,1, QtGui.QPen(QtGui.QColor(80,80,50))) 
        self.gv.setScene(self.scene)
        self.gv.setAspectLocked(True)
        self.gv.invertY()
        self.AGCLastMax = None
        
        #self.plotScene.addItem(QtGui.QGraphicsRectItem(-1, -1, 2, 2))
        #self.grid = Grid(self.pgv)
        #self.plotScene.addItem(self.grid)
        #self.grid.setZValue(-1)
        #self.pgv.setScene(self.plotScene)
        #self.pgv.setRange(QtCore.QRectF(0, 0, 100, 3000))
        
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
        
        self.ui.spinBinning.setValue(self.binning)
        self.ui.spinExposure.setValue(self.exposure)
        self.border = self.scene.addRect(0, 0,self.camSize[0], self.camSize[1], QtGui.QPen(QtGui.QColor(50,80,80))) 
        
        bw = self.camSize[0]*0.125
        bh = self.camSize[1]*0.125
        self.centerBox = self.scene.addRect(self.camSize[0]*0.5-bw*0.5, self.camSize[1]*0.5-bh*0.5, bw, bh, QtGui.QPen(QtGui.QColor(80,80,50)))
        self.centerBox.setZValue(50)
        
        self.gv.setRange(QtCore.QRect(0, 0, self.camSize[0], self.camSize[1]), lockAspect=True)
        
        QtCore.QObject.connect(self.ui.btnAcquire, QtCore.SIGNAL('clicked()'), self.toggleAcquire)
        QtCore.QObject.connect(self.ui.btnRecord, QtCore.SIGNAL('toggled(bool)'), self.toggleRecord)
        #QtCore.QObject.connect(self.ui.btnROPing, QtCore.SIGNAL('toggled(bool)'), self.toggleROPing)
        QtCore.QObject.connect(self.ui.btnAutoGain, QtCore.SIGNAL('toggled(bool)'), self.toggleAutoGain)
        QtCore.QObject.connect(self.ui.btnFullFrame, QtCore.SIGNAL('clicked()'), self.setRegion)
        QtCore.QObject.connect(self.ui.spinBinning, QtCore.SIGNAL('valueChanged(int)'), self.setBinning)
        QtCore.QObject.connect(self.ui.spinExposure, QtCore.SIGNAL('valueChanged(double)'), self.setExposure)
        #QtCore.QObject.connect(self.recordThread, QtCore.SIGNAL('storageDirChanged'), self.updateStorageDir)
        #QtCore.QObject.connect(self.recordThread, QtCore.SIGNAL('recordStatusChanged'), self.updateRecordStatus)
        QtCore.QObject.connect(self.recordThread, QtCore.SIGNAL('showMessage'), self.showMessage)
        QtCore.QObject.connect(self.acquireThread, QtCore.SIGNAL('newFrame'), self.newFrame)
        QtCore.QObject.connect(self.acquireThread, QtCore.SIGNAL('finished()'), self.acqThreadStopped)
        QtCore.QObject.connect(self.acquireThread, QtCore.SIGNAL('started()'), self.acqThreadStarted)
        QtCore.QObject.connect(self.acquireThread, QtCore.SIGNAL('showMessage'), self.showMessage)
        QtCore.QObject.connect(self.gv, QtCore.SIGNAL("sceneMouseMoved(PyQt_PyObject)"), self.setMouse)
        #QtCore.QObject.connect(self.ui.comboTransferMode, QtCore.SIGNAL('currentIndexChanged(int)'), self.setTransferMode)
        #QtCore.QObject.connect(self.ui.comboShutterMode, QtCore.SIGNAL('currentIndexChanged(int)'), self.setShutterMode)
        QtCore.QObject.connect(self.ui.btnDivideBackground, QtCore.SIGNAL('clicked()'), self.divideClicked)
        
        QtCore.QObject.connect(self.ui.btnAddROI, QtCore.SIGNAL('clicked()'), self.addROI)
        QtCore.QObject.connect(self.ui.checkEnableROIs, QtCore.SIGNAL('valueChanged(bool)'), self.enableROIsChanged)
        QtCore.QObject.connect(self.ui.spinROITime, QtCore.SIGNAL('valueChanged(double)'), self.setROITime)
        QtCore.QObject.connect(self.ui.sliderWhiteLevel, QtCore.SIGNAL('valueChanged(int)'), self.requestFrameUpdate)
        QtCore.QObject.connect(self.ui.sliderBlackLevel, QtCore.SIGNAL('valueChanged(int)'), self.requestFrameUpdate)
        QtCore.QObject.connect(self.ui.spinFlattenSize, QtCore.SIGNAL('valueChanged(int)'), self.requestFrameUpdate)
        
        
        
        self.ui.btnAutoGain.setChecked(True)
        
        ## Check for new frame updates every 1ms
        ## Some checks may be skipped even if there is a new frame waiting to avoid drawing more than 
        ## 60fps.
        self.frameTimer = QtCore.QTimer()
        QtCore.QObject.connect(self.frameTimer, QtCore.SIGNAL('timeout()'), self.updateFrame)
        self.frameTimer.start(1)

    def addROI(self):
        roi = PlotROI(10)
        roi.setZValue(20)
        self.scene.addItem(roi)
        #plot = Plot(array([]))
        #self.plotScene.addItem(plot)
        plot = Qwt.QwtPlotCurve('roi%d'%len(self.ROIs))
        plot.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
        plot.attach(self.ui.plotWidget)
        self.ROIs.append({'roi': roi, 'plot': plot, 'vals': [], 'times': []})
        
    def clearFrameBuffer(self):
        self.frameBuffer = []
        for r in self.ROIs:
            r['vals'] = []
            r['times'] = []

    def enableROIsChanged(self, b):
        pass
    
    def setROITime(self, val):
        pass

    def toggleRecord(self, b):
        if b:
            #self.ui.txtStorageDir.setEnabled(False)
            #self.ui.btnSelectDir.setEnabled(False)
            self.ui.btnRecord.setChecked(True)
        else:
            #self.ui.txtStorageDir.setEnabled(True)
            #self.ui.btnSelectDir.setEnabled(True)
            self.ui.btnRecord.setChecked(False)

    #def toggleROPing(self, b):
    #  if b:
    #    self.ropWindow.show()
    #  else:
    #    self.ropWindow.hide()

    #def updateRecordStatus(self, ready):
        #if ready:
            #self.ui.btnRecord.setEnabled(True)
            #self.ui.btnSnap.setEnabled(True)
        #else:
            #self.ui.btnRecord.setEnabled(False)
            #self.ui.btnSnap.setEnabled(False)
            
    def requestFrameUpdate(self):
        self.updateFrame = True

    def divideClicked(self):
        self.AGCLastMax = None
        self.AGCLastMin = None
        self.setLevelRange()
        if self.ui.btnDivideBackground.isChecked() and not self.ui.btnLockBackground.isChecked():
            self.backgroundFrame = None
        self.requestFrameUpdate()
            
    #def updateStorageDir(self, newDir):
        #self.ui.txtStorageDir.setText(newDir)

    def showMessage(self, msg):
        self.ui.statusbar.showMessage(str(msg))
        
    def updateRegion(self, *args):
        self.clearFrameBuffer()
        r = self.roi.sceneBounds()
        newRegion = [int(r.left()), int(r.top()), int(r.right())-1, int(r.bottom())-1]
        if self.region != newRegion:
            self.region = newRegion
            self.acquireThread.setParam('region', self.region)
            #self.acquireThread.reset()
        
        
    def closeEvent(self, ev):
        #self.ropWindow.stop()
        if self.acquireThread.isRunning():
            print "Stopping acquisition thread.."
            self.acquireThread.stop()
            self.acquireThread.wait()
        if self.recordThread.isRunning():
            print "Stopping recording thread.."
            self.recordThread.stop()
            self.recordThread.wait()
        #print "Exiting."

        
    #def setTransferMode(self, mode):
        #acq = self.acquireThread.isRunning()
        #if acq:
            #self.acquireThread.stop()
            #self.acquireThread.wait()
        #self.cam.setTransferMode(mode)
        #self.ui.comboTransferMode.setCurrentIndex(self.cam.getTransferMode())
        #if acq:
            #self.acquireThread.start()
        
    #def setShutterMode(self, mode):
        #acq = self.acquireThread.isRunning()
        #if acq:
            #self.acquireThread.stop()
            #self.acquireThread.wait()
        #self.cam.setShutterMode(mode)
        #self.ui.comboShutterMode.setCurrentIndex(self.cam.getShutterMode())
        #if acq:
            #self.acquireThread.start()

    def setMouse(self, qpt=None):
        if qpt is None:
            if not hasattr(self, 'mouse'):
                return
            (x, y) = self.mouse
        else:
            x = qpt.x() / self.binning
            y = qpt.y() / self.binning
        self.mouse = [x, y]
        img = self.imageItem.image
        if img is None:
            return
        if y >= 0 and x >= 0 and y < img.shape[1] and x < img.shape[0]:
            z = img[int(x), int(y)]
        
            if hasattr(z, 'shape') and len(z.shape) > 0:
                z = "Z:(%s, %s, %s)" % (str(z[0]), str(z[1]), str(z[2]))
            else:
                z = "Z:%s" % str(z)
        
            self.xyLabel.setText("X:%0.2f Y:%0.2f" % (x, y))
            self.vLabel.setText(z)
            

    def acqThreadStopped(self):
        self.toggleRecord(False)
        if not self.ui.btnLockBackground.isChecked():
            self.backgroundFrame = None
        self.ui.btnAcquire.setChecked(False)
        self.ui.btnAcquire.setEnabled(True)
        
    def acqThreadStarted(self):
        self.AGCLastMax = None
        self.AGCLastMin = None
        self.ui.btnAcquire.setChecked(True)
        self.ui.btnAcquire.setEnabled(True)

    def setBinning(self, b):
        self.backgroundFrame = None
        self.binning = b
        self.acquireThread.setParam('binning', self.binning)
        #self.acquireThread.reset()
        self.clearFrameBuffer()
        self.updateRgnLabel()
        
    def setExposure(self, e):
        self.exposure = e
        self.acquireThread.setParam('exposure', self.exposure)
        #self.acquireThread.reset()
        
    def openCamera(self, ind=0):
        try:
            #cams = pvcam.PVCam.listCameras()
            #self.cam = pvcam.PVCam.getCamera(cams[ind])
            self.cam = self.module.cam.getCamera()
            
            self.bitDepth = self.cam.getBitDepth()
            self.setLevelRange()
            self.camSize = self.cam.getSize()
            self.roi = CamROI(self.camSize)
            self.roi.connect(QtCore.SIGNAL('regionChangeFinished'), self.updateRegion)
            self.scene.addItem(self.roi)
            #self.ui.spinRegionS2.setMaximum(self.camSize[0]-1)
            #self.ui.spinRegionP2.setMaximum(self.camSize[1]-1)
            #self.ui.spinRegionS2.setMinimum(1)
            #self.ui.spinRegionP2.setMinimum(1)
            self.setRegion()
            self.ui.statusbar.showMessage("Opened camera %s" % self.cam, 5000)
            #tmodes = self.cam.listTransferModes()
            #tmode = self.cam.getTransferMode()
            #self.ui.comboTransferMode.addItems(tmodes)
            #self.ui.comboTransferMode.setCurrentIndex(tmode)
            #smodes = self.cam.listShutterModes()
            #smode = self.cam.getShutterMode()
            #self.ui.comboShutterMode.addItems(smodes)
            #self.ui.comboShutterMode.setCurrentIndex(smode)
        except:
            self.ui.statusbar.showMessage("Error opening camera")
            raise
    

    def setRegion(self, rgn=None):
        self.backgroundFrame = None
        if rgn is None:
            rgn = [0, 0, self.camSize[0]-1, self.camSize[1]-1]
        #self.ui.spinRegionS1.setValue(rgn[0])
        #self.ui.spinRegionP1.setValue(rgn[1])
        #self.ui.spinRegionS2.setValue(rgn[2])
        #self.ui.spinRegionP2.setValue(rgn[3])
        self.roi.setPos([rgn[0], rgn[1]])
        self.roi.setSize([self.camSize[0], self.camSize[1]])
        self.updateRegion()
            
    def updateRgnLabel(self):
        img = self.imageItem.image
        if img is None:
            return
        self.rgnLabel.setText('[%d, %d, %d, %d] %dx%d' % (self.region[0], self.region[1], (img.shape[0]-1)*self.binning, (img.shape[1]-1)*self.binning, self.binning, self.binning))
    
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
        self.ui.labelLevelMax.setText(str(self.levelMax))
        self.ui.labelLevelMid.setText(str((self.levelMax+self.levelMin) * 0.5)[:4])
        self.ui.labelLevelMin.setText(str(self.levelMin))
        self.ui.sliderAvgLevel.setMaximum(2**self.bitDepth - 1)
        #self.updateFrame = True
        
    def getLevels(self):
        w = self.ui.sliderWhiteLevel
        b = self.ui.sliderBlackLevel
        wl = self.levelMin + (self.levelMax-self.levelMin) * (float(w.value())-float(w.minimum())) / (float(w.maximum())-float(w.minimum()))
        bl = self.levelMin + (self.levelMax-self.levelMin) * (float(b.value())-float(b.minimum())) / (float(b.maximum())-float(b.minimum()))
        return (bl, wl)
        

    def toggleAutoGain(self, b):
        self.setLevelRange()

    def toggleAcquire(self):
        if self.ui.btnAcquire.isChecked():
            self.acquireThread.setParam('mode', 'Normal')
            self.acquireThread.start()
        else:
            self.toggleRecord(False)
            self.acquireThread.stop()
            
    def addPlotFrame(self, frame):
        ## Get rid of old frames
        minTime = None
        if len(self.frameBuffer) > 0:
            now = ptime.time()
            while self.frameBuffer[0][1]['time'] < (now-self.ui.spinROITime.value()):
                self.frameBuffer.pop(0)
            for r in self.ROIs:
                if len(r['times']) < 1:
                    continue
                while r['times'][0] < (now-self.ui.spinROITime.value()):
                    r['times'].pop(0)
                    r['vals'].pop(0)
                if minTime is None or r['times'][0] < minTime:
                    minTime = r['times'][0]
        if minTime is None:
            minTime = frame[1]['time']
                
        ## add new frame
        draw = False
        if self.lastPlotTime is None or now - lastPlotTime > 0.05:
            draw = True
        self.frameBuffer.append(frame)
        if len(self.frameBuffer) < 2: 
            return
        for r in self.ROIs:
            d = r['roi'].getArrayRegion(frame[0], self.imageItem, axes=(0,1))
            if d is None:
                continue
            if d.size < 1:
                val = 0
            else:
                val = d.mean()
            r['vals'].append(val)
            r['times'].append(frame[1]['time'])
            if draw:
                #r['plot'].updateData(array(r['vals']))
                r['plot'].setData(array(r['times'])-minTime, r['vals'])
            
        self.ui.plotWidget.replot()
    
            
    def newFrame(self, frame):
        self.nextFrame = frame
        
    def updateFrame(self):
        try:
            
            ## If we last drew a frame < 1/60s ago, return.
            t = ptime.time()
            if (self.lastDrawTime is not None) and (t - self.lastDrawTime < .016666):
                return
            
            ## if there is no new frame and no controls have changed, just exit
            if not self.updateFrame and self.nextFrame is None:
                return
            self.updateFrame = False
            
            ## If there are no new frames and no previous frames, then there is nothing to draw.
            if self.currentFrame is None and self.nextFrame is None:
                return
            
            ## We will now draw a new frame (even if the frame is unchanged)
            self.lastDrawTime = t
            
            
            ## Handle the next available frame, if there is one.
            if self.nextFrame is not None:
                self.currentFrame = self.nextFrame
                self.nextFrame = None
                (data, info) = self.currentFrame
                self.currentClipMask = (data >= (2**self.bitDepth * 0.99)) 
                self.ui.sliderAvgLevel.setValue(int(data.mean()))
                
                ## If background division is enabled, mix the current frame into the background frame
                if self.ui.btnDivideBackground.isChecked():
                    if self.backgroundFrame is None:
                        self.backgroundFrame = data.astype(float)
                    if not self.ui.btnLockBackground.isChecked():
                        s = 1.0 - 1.0 / (self.ui.spinFilterTime.value()+1.0)
                        self.backgroundFrame *= s
                        self.backgroundFrame += data * (1.0-s)

            (data, info) = self.currentFrame
            
            ## Update ROI plots, if any
            if self.ui.checkEnableROIs.isChecked():
                self.addPlotFrame(self.currentFrame)
            
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
                
            ## Translate and scale image based on ROI and binning
            m = QtGui.QTransform()
            #m.translate(self.region[0], self.region[1])
            m.translate(info['region'][0], info['region'][1])
            #m.scale(self.binning, self.binning)
            m.scale(info['binning'], info['binning'])
            
            ## update image in viewport
            #self.imageItem.setLevels(white=wl, black=bl)
            self.imageItem.updateImage(data, clipMask=self.currentClipMask, white=wl, black=bl)
            self.imageItem.setTransform(m)
            
            ## update info for pixel under mouse pointer
            self.setMouse()
            if hasattr(self.acquireThread, 'fps') and self.acquireThread.fps is not None:
                self.fpsLabel.setText('%02.2ffps' % self.acquireThread.fps)
            self.updateRgnLabel()
        except:
            #print "Exception in QtCam::newFrame: %s (line %d)" % (str(sys.exc_info()[1]), sys.exc_info()[2].tb_lineno)
            sys.excepthook(*sys.exc_info())

#class AcquireThread(QtCore.QThread):
    #def __init__(self, ui):
        #QtCore.QThread.__init__(self)
        #self.ui = ui
        #self.stopThread = False
        #self.lock = QtCore.QMutex()
        #self.acqBuffer = None
        #self.frameId = 0
        #self.bufferTime = 5.0
        #self.ringSize = 20
        #time.clock()  ## On windows, this is needed to start the clock
    
    #def run(self):
        #binning = self.ui.binning
        #exposure = self.ui.exposure
        #region = self.ui.region
        #lastFrame = None
        #lastFrameTime = None
        #self.lock.lock()
        #self.stopThread = False
        #self.lock.unlock()
        #self.fps = None
        
        #try:
            #self.acqBuffer = self.ui.cam.start(frames=self.ringSize, binning=binning, exposure=exposure, region=region)
            #lastFrameTime = time.clock()  # Use time.time() on Linux
            
            #while True:
                #frame = self.ui.cam.lastFrame()
                #now = time.clock()
                
                ### If a new frame is available, process it and inform other threads
                #if frame is not None and frame != lastFrame:
                    
                    #if lastFrame is not None and frame - lastFrame > 1:
                        #print "Dropped frames between %d and %d" % (lastFrame, frame)
                        #self.emit(QtCore.SIGNAL("showMessage"), "Acquisition thread dropped frame!")
                    #lastFrame = frame
                    
                    ### compute FPS
                    #dt = now - lastFrameTime
                    #if dt > 0.:
                        #if self.fps is None:
                            #self.fps = 1.0/dt
                        #else:
                            #self.fps = self.fps * 0.9 + 0.1 / dt
                    
                    ### Build meta-info for this frame
                    ### Use lastFrameTime because the current frame _began_ exposing when the previous frame arrived.
                    #info = {'id': self.frameId, 'time': lastFrameTime, 'binning': binning, 'exposure': exposure, 'region': region, 'fps': self.fps}
                    
                    #lastFrameTime = now
                    
                    ### Inform that new frame is ready
                    #self.emit(QtCore.SIGNAL("newFrame"), (self.acqBuffer[frame].copy(), info))
                    #self.frameId += 1
                #time.sleep(10e-6)
                
                #self.lock.lock()
                #if self.stopThread and frame is not None:
                    #self.lock.unlock()
                    #break
                #self.lock.unlock()
            #self.ui.cam.stop()
        #except:
            #try:
                #self.ui.cam.stop()
            #except:
                #pass
            #self.emit(QtCore.SIGNAL("showMessage"), "ERROR Starting acquisition: %s" % str(sys.exc_info()[1]))
        
    #def stop(self):
        #l = QtCore.QMutexLocker(self.lock)
        #self.stopThread = True

    #def reset(self):
        #if self.isRunning():
            #self.stop()
            #self.wait()
            #self.start()


class RecordThread(QtCore.QThread):
    def __init__(self, ui, manager):
        QtCore.QThread.__init__(self)
        self.ui = ui
        self.m = manager
        #self.dialog = QtGui.QFileDialog()
        #self.dialog.setFileMode(QtGui.QFileDialog.DirectoryOnly)
        QtCore.QObject.connect(self.ui.acquireThread, QtCore.SIGNAL('newFrame'), self.newCamFrame)
        #QtCore.QObject.connect(self.ui.ropWindow.acquireThread, QtCore.SIGNAL('newFrame'), self.newDaqFrame)
        
        QtCore.QObject.connect(ui.ui.btnRecord, QtCore.SIGNAL('toggled(bool)'), self.toggleRecord)
        QtCore.QObject.connect(ui.ui.btnSnap, QtCore.SIGNAL('clicked()'), self.snapClicked)
        #QtCore.QObject.connect(ui.ui.btnSelectDir, QtCore.SIGNAL('clicked()'), self.showFileDialog)
        #QtCore.QObject.connect(ui.ui.txtStorageDir, QtCore.SIGNAL('textEdited(const QString)'), self.selectDir)
        #QtCore.QObject.connect(self.dialog, QtCore.SIGNAL('filesSelected(const QStringList)'), self.selectDir)
        self.recording = False
        self.takeSnap = False
        #self.currentRecord = 0
        #self.nextRecord = 0
        self.currentDir = None
        self.currentCamFrame = 0
        #self.currentDaqFrame = 0
        #self.storageDir = None
        
        self.lock = QtCore.QMutex(QtCore.QMutex.Recursive)
        #self.daqLock = QtCore.QMutex()
        self.camLock = QtCore.QMutex()
        #self.newDaqFrames = []
        self.newCamFrames = []
        
    #def newDaqFrame(self, frame):
    #  l = QtCore.QMutexLocker(self.lock)
    #  recording = self.recording
    #  l.unlock()
    #  if recording:
    #    dlock = QtCore.QMutexLocker(self.daqLock)
    #    self.newDaqFrames.append(frame)
        
    def newCamFrame(self, frame):
        l = QtCore.QMutexLocker(self.lock)
        recording = self.recording
        takeSnap = self.takeSnap
        l.unlock()
        if recording or takeSnap:
            cLock = QtCore.QMutexLocker(self.camLock)
            self.newCamFrames.append(frame)
    
    
    def run(self):
        self.stopThread = False
        
        while True:
            #dlock = QtCore.QMutexLocker(self.daqLock)
            #handleDaqFrames = self.newDaqFrames[:]
            #self.newDaqFrames = []
            #dlock.unlock()
            try:
                cLock = QtCore.QMutexLocker(self.camLock)
                handleCamFrames = self.newCamFrames[:]
                self.newCamFrames = []
            except:
                sys.excepthook(*sys.exc_info())
                break
            finally:
                cLock.unlock()
            
            #while len(handleDaqFrames) > 0:
            #  self.handleDaqFrame(handleDaqFrames.pop(0))
            
            try:
                while len(handleCamFrames) > 0:
                    self.handleCamFrame(handleCamFrames.pop(0))
            except:
                sys.excepthook(*sys.exc_info())
                break
                
            time.sleep(10e-3)
            
            l = QtCore.QMutexLocker(self.lock)
            if self.stopThread:
                break
            l.unlock()


    def handleCamFrame(self, frame):
        l = QtCore.QMutexLocker(self.lock)
        recording = self.recording
        takeSnap = self.takeSnap
        #storageDir = self.storageDir
        l.unlock()
        
        if not (recording or takeSnap):
            return
        
        (data, info) = frame
        
        if recording:
            fileName = 'camFrame_%05d_%f.tif' % (self.currentCamFrame, info['time'])
            #fileName = os.path.join(self.currentDir(), fileName)
            self.showMessage("Recording %s - %d" % (self.currentDir.name(), self.currentCamFrame))
            self.currentDir.writeFile(ImageFile(data), fileName, info)
            #infoFile = os.path.join(self.currentDir(), '.info')
            #if self.currentCamFrame == 0:
                #fd = open(infoFile, 'a')
                #fd.write("info['camera'] = " + str(info) + "\n")
                #fd.close()
            self.currentCamFrame += 1
        
        if takeSnap:
            fileName = 'image.tif'
            #fileName = os.path.join(storageDir, fileName)
            fn = self.m.getCurrentDir().writeFile(ImageFile(data), fileName, info, autoIncrement=True)
            self.showMessage("Saved image %s" % fn)
            #self.nextRecord += 1
            
            #infoFile = os.path.join(storageDir, '.info')
            #fd = open(infoFile, 'a')
            #fd.write("info['%s'] = " % os.path.split(fileName)[1])
            #fd.write(str(info) + "\n")
            #fd.close()
            
            l = QtCore.QMutexLocker(self.lock)
            self.takeSnap = False

        #img = Image.fromarray(data.transpose())
        #img.save(fileName)


    #def handleDaqFrame(self, frame):
    #  l = QtCore.QMutexLocker(self.lock)
    #  recording = self.recording
    #  storageDir = self.storageDir
    #  l.unlock()
    #  
    #  if storageDir is None or not recording:
    #    return
    #  
    #  (data, info) = frame
    #  fileName = 'daqFrame_%05d_%f.dat' % (self.currentDaqFrame, info['time'])
    #  fileName = os.path.join(self.currentDir(), fileName)
    #  info['dtype'] = data.dtype
    #  info['shape'] = data.shape
    #  self.writeDaqFile(data, fileName)
    #  infoFile = os.path.join(self.currentDir(), '.info')
    #  if self.currentDaqFrame == 0:
    #    fd = open(infoFile, 'a')
    #    fd.write("info['daq'] = " + str(info) + "\n")
    #    fd.close()
    #  self.currentDaqFrame += 1
        

    
    def showMessage(self, msg):
        self.emit(QtCore.SIGNAL('showMessage'), msg)
    
    def snapClicked(self):
        l = QtCore.QMutexLocker(self.lock)
        self.takeSnap = True

    def toggleRecord(self, b):
        l = QtCore.QMutexLocker(self.lock)
        try:
            if b:
                self.currentDir = self.m.getCurrentDir().mkdir('record', autoIncrement=True)
                self.currentCamFrame = 0
        #   self.currentDaqFrame = 0
                #self.currentRecord = self.nextRecord
                #self.nextRecord += 1
                self.recording = True
                #os.mkdir(self.currentDir())
            else:
                if self.recording:
                    self.recording = False
                    self.showMessage('Finished recording %s' % self.currentDir.name()) 
        finally:
            l.unlock()

    #def currentDir(self):
        ##l = QtCore.QMutexLocker(self.lock)
        ##storageDir = self.storageDir
        ##l.unlock()
        #baseDir = self.m.getCurrentDir()
        #return baseDir.getDir('record_%03d' % self.currentRecord, create=True)
        ##return os.path.normpath(os.path.join(storageDir, 'record_%03d' % self.currentRecord))

        ## How do we differentiate between record images and snap images?
    #def writeFile(self, data, fileName):
        #origName = fileName
        #ind = 0
        #while os.path.isfile(fileName):
            #parts = os.path.splitext(origName)
            #fileName = parts[0] + '_%d'%ind + parts[1]
            #ind += 1
        #img = Image.fromarray(data.transpose())
        #img.save(fileName)

    #def writeDaqFile(self, data, fileName):
    #  origName = fileName
    #  ind = 0
    #  while os.path.isfile(fileName):
    #    parts = os.path.splitext(origName)
    #    fileName = parts[0] + '_%d'%ind + parts[1]
    #    ind += 1
    #  data.tofile(fileName)

    #def showFileDialog(self):
        #self.dialog.show()

    #def selectDir(self, dirName=None):
        #if dirName is None:
            #dirName = QtGui.QFileDialog.getExistingDirectory()
        #elif type(dirName) is QtCore.QStringList:
            #dirName = str(dirName[0])
        #elif type(dirName) is QtCore.QString:
            #dirName = str(dirName)
        #if dirName is None:
            #return
        #if os.path.isdir(dirName):
            #l = QtCore.QMutexLocker(self.lock)
            #self.storageDir = dirName
            #self.nextRecord = 0
            #self.emit(QtCore.SIGNAL("recordStatusChanged"), True)
            #self.emit(QtCore.SIGNAL("storageDirChanged"), self.storageDir)
            #for f in os.listdir(dirName):
                #m = re.match(r'\D+_(\d+).*', f)
                #if m is not None:
                    #num = int(m.groups()[0]) + 1
                    #self.nextRecord = max(self.nextRecord, num)
            #self.showMessage("Next record number is %d" % self.nextRecord) 
        #else:
            #self.emit(QtCore.SIGNAL("recordStatusChanged"), False)
            #self.showMessage("Storage directory is invalid")

    def stop(self):
        l = QtCore.QMutexLocker(self.lock)
        self.stopThread = True
        l.unlock()


#def main():
    #global app, qc
    #app = QtGui.QApplication(sys.argv)
    #qc = QtCam()
    #app.exec_()
    
    
#main()
