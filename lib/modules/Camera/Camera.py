#!/usr/bin/python
# -*- coding: utf-8 -*-

## TODO
# reliable error messaging for missed frames
# Add fast/simple histogram 


from CameraTemplate import Ui_MainWindow
from lib.util.qtgraph.GraphicsView import *
from lib.util.qtgraph.graphicsItems import *
from lib.util.qtgraph.widgets import ROI
import lib.util.ptime as ptime
from lib.filetypes.ImageFile import *
from PyQt4 import QtGui, QtCore
from PyQt4 import Qwt5 as Qwt
import scipy.ndimage
import time, types, os.path, re, sys

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
        self.acquireThread = self.module.cam.acqThread
        self.acquireThread.setParam('binning', self.binning)
        self.acquireThread.setParam('exposure', self.exposure)
        
        self.frameBuffer = []
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
        
        ## Set up level thermo and scale widgets
        self.scaleEngine = Qwt.QwtLinearScaleEngine()
        self.ui.levelThermo.setScalePosition(Qwt.QwtThermo.NoScale)
        self.ui.levelScale.setAlignment(Qwt.QwtScaleDraw.LeftScale)
        self.ui.levelScale.setColorBarEnabled(True)
        self.ui.levelScale.setColorBarWidth(10)
        
        
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
        self.ui.plotWidget.plot()

        self.setCentralWidget(self.ui.centralwidget)
        self.scene = QtGui.QGraphicsScene(self)
        self.imageItem = ImageItem()
        self.scene.addItem(self.imageItem)
        self.gv.setScene(self.scene)
        self.gv.setAspectLocked(True)
        self.gv.invertY()
        self.AGCLastMax = None
        
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
        QtCore.QObject.connect(self.ui.btnAutoGain, QtCore.SIGNAL('toggled(bool)'), self.toggleAutoGain)
        QtCore.QObject.connect(self.ui.btnFullFrame, QtCore.SIGNAL('clicked()'), self.setRegion)
        QtCore.QObject.connect(self.ui.spinBinning, QtCore.SIGNAL('valueChanged(int)'), self.setBinning)
        QtCore.QObject.connect(self.ui.spinExposure, QtCore.SIGNAL('valueChanged(double)'), self.setExposure)
        QtCore.QObject.connect(self.recordThread, QtCore.SIGNAL('showMessage'), self.showMessage)
        QtCore.QObject.connect(self.acquireThread, QtCore.SIGNAL('newFrame'), self.newFrame)
        QtCore.QObject.connect(self.acquireThread, QtCore.SIGNAL('finished()'), self.acqThreadStopped)
        QtCore.QObject.connect(self.acquireThread, QtCore.SIGNAL('started()'), self.acqThreadStarted)
        QtCore.QObject.connect(self.acquireThread, QtCore.SIGNAL('showMessage'), self.showMessage)
        QtCore.QObject.connect(self.gv, QtCore.SIGNAL("sceneMouseMoved(PyQt_PyObject)"), self.setMouse)
        QtCore.QObject.connect(self.ui.btnDivideBackground, QtCore.SIGNAL('clicked()'), self.divideClicked)
        
        QtCore.QObject.connect(self.ui.btnAddROI, QtCore.SIGNAL('clicked()'), self.addROI)
        QtCore.QObject.connect(self.ui.checkEnableROIs, QtCore.SIGNAL('valueChanged(bool)'), self.enableROIsChanged)
        QtCore.QObject.connect(self.ui.spinROITime, QtCore.SIGNAL('valueChanged(double)'), self.setROITime)
        QtCore.QObject.connect(self.ui.sliderWhiteLevel, QtCore.SIGNAL('valueChanged(int)'), self.levelsChanged)
        QtCore.QObject.connect(self.ui.sliderBlackLevel, QtCore.SIGNAL('valueChanged(int)'), self.levelsChanged)
        QtCore.QObject.connect(self.ui.spinFlattenSize, QtCore.SIGNAL('valueChanged(int)'), self.requestFrameUpdate)
        
        
        
        self.ui.btnAutoGain.setChecked(True)
        
        ## Check for new frame updates every 1ms
        ## Some checks may be skipped even if there is a new frame waiting to avoid drawing more than 
        ## 60fps.
        self.frameTimer = QtCore.QTimer()
        QtCore.QObject.connect(self.frameTimer, QtCore.SIGNAL('timeout()'), self.drawFrame)
        self.frameTimer.start(1)

    def addROI(self):
        roi = PlotROI(10)
        roi.setZValue(20)
        self.scene.addItem(roi)
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
            self.ui.btnRecord.setChecked(True)
        else:
            self.ui.btnRecord.setChecked(False)

    def levelsChanged(self):
        self.updateColorScale()
        self.requestFrameUpdate()

    def requestFrameUpdate(self):
        self.updateFrame = True

    def divideClicked(self):
        self.AGCLastMax = None
        self.AGCLastMin = None
        self.setLevelRange()
        if self.ui.btnDivideBackground.isChecked() and not self.ui.btnLockBackground.isChecked():
            self.backgroundFrame = None
        self.requestFrameUpdate()
            
    def showMessage(self, msg):
        self.ui.statusbar.showMessage(str(msg))
        
    def updateRegion(self, *args):
        self.clearFrameBuffer()
        r = self.roi.sceneBounds()
        newRegion = [int(r.left()), int(r.top()), int(r.right())-1, int(r.bottom())-1]
        if self.region != newRegion:
            self.region = newRegion
            self.acquireThread.setParam('region', self.region)
        
        
    def closeEvent(self, ev):
        if self.acquireThread.isRunning():
            print "Stopping acquisition thread.."
            self.acquireThread.stop()
            self.acquireThread.wait()
        if self.recordThread.isRunning():
            print "Stopping recording thread.."
            self.recordThread.stop()
            self.recordThread.wait()

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
        
    def openCamera(self, ind=0):
        try:
            self.cam = self.module.cam.getCamera()
            
            self.bitDepth = self.cam.getBitDepth()
            self.setLevelRange()
            self.camSize = self.cam.getSize()
            self.roi = CamROI(self.camSize)
            self.roi.connect(QtCore.SIGNAL('regionChangeFinished'), self.updateRegion)
            self.scene.addItem(self.roi)
            self.setRegion()
            self.ui.statusbar.showMessage("Opened camera %s" % self.cam, 5000)
        except:
            self.ui.statusbar.showMessage("Error opening camera")
            raise
    

    def setRegion(self, rgn=None):
        self.backgroundFrame = None
        if rgn is None:
            rgn = [0, 0, self.camSize[0]-1, self.camSize[1]-1]
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
        
        self.ui.levelScale.setScaleDiv(self.scaleEngine.transformation(), self.scaleEngine.divideScale(self.levelMin, self.levelMax, 8, 5))
        self.updateColorScale()
        
        self.ui.levelThermo.setMaxValue(2**self.bitDepth - 1)
        self.ui.levelThermo.setAlarmLevel(self.ui.levelThermo.maxValue() * 0.9)
        
    def updateColorScale(self):
        (w, b) = self.getLevels()
        self.ui.levelScale.setColorMap(Qwt.QwtDoubleInterval(b, w), Qwt.QwtLinearColorMap(QtCore.Qt.black, QtCore.Qt.white))
                
        
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
            
        self.ui.plotWidget.plot()
    
            
    def newFrame(self, frame):
        #if hasattr(self.acquireThread, 'fps') and self.acquireThread.fps is not None:
        if self.nextFrame is not None:
            dt = frame[1]['time'] - self.nextFrame[1]['time']
            if self.fps is None:
                self.fps = 1.0/dt
            else:
                self.fps = self.fps * 0.9 + 0.1 / dt
            self.fpsLabel.setText('%02.2ffps' % self.fps)
        self.nextFrame = frame
        
    def drawFrame(self):
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
                
                self.ui.levelThermo.setValue(int(data.mean()))
                
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
            m.translate(info['region'][0], info['region'][1])
            m.scale(info['binning'], info['binning'])
            
            ## update image in viewport
            self.imageItem.updateImage(data, clipMask=self.currentClipMask, white=wl, black=bl)
            self.imageItem.setTransform(m)
            
            ## update info for pixel under mouse pointer
            self.setMouse()
            self.updateRgnLabel()
        except:
            #print "Exception in QtCam::newFrame: %s (line %d)" % (str(sys.exc_info()[1]), sys.exc_info()[2].tb_lineno)
            sys.excepthook(*sys.exc_info())


class RecordThread(QtCore.QThread):
    def __init__(self, ui, manager):
        QtCore.QThread.__init__(self)
        self.ui = ui
        self.m = manager
        QtCore.QObject.connect(self.ui.acquireThread, QtCore.SIGNAL('newFrame'), self.newCamFrame)
        
        QtCore.QObject.connect(ui.ui.btnRecord, QtCore.SIGNAL('toggled(bool)'), self.toggleRecord)
        QtCore.QObject.connect(ui.ui.btnSnap, QtCore.SIGNAL('clicked()'), self.snapClicked)
        self.recording = False
        self.recordStart = False
        self.recordStop = False
        self.takeSnap = False
        self.currentRecord = None
        
        self.lock = QtCore.QMutex(QtCore.QMutex.Recursive)
        self.camLock = QtCore.QMutex()
        self.newCamFrames = []
        
    def newCamFrame(self, frame):
        l = QtCore.QMutexLocker(self.lock)
        try:
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
        finally:
            l.unlock()
        if recording or takeSnap:
            cLock = QtCore.QMutexLocker(self.camLock)
            ## remember the record/snap/storageDir states since they might change 
            ## before the write thread gets to this frame
            self.newCamFrames.append({'frame': frame, 'record': recording, 'snap': takeSnap, 'newRec': newRec, 'lastRec': lastRec})
    
    def run(self):
        self.stopThread = False
        
        while True:
            try:
                cLock = QtCore.QMutexLocker(self.camLock)
                handleCamFrames = self.newCamFrames[:]
                self.newCamFrames = []
            except:
                sys.excepthook(*sys.exc_info())
                break
            finally:
                cLock.unlock()
            
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
        (data, info) = frame['frame']
        
        if frame['record']:
            if frame['newRec']:
                self.startFrameTime = info['time']
                
            arrayInfo = [
                {'name': 'Time', 'values': array([info['time'] - self.startFrameTime]), 'units': 's'},
                {'name': 'X'},
                {'name': 'Y'}
            ]
            data = MetaArray(data[newaxis], info=arrayInfo)
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
            
            fh = self.m.getCurrentDir().writeFile(ImageFile(data), fileName, info, autoIncrement=True)
            fn = fh.name()
            self.showMessage("Saved image %s" % fn)
            l = QtCore.QMutexLocker(self.lock)
            self.takeSnap = False
    
    def showMessage(self, msg):
        self.emit(QtCore.SIGNAL('showMessage'), msg)
    
    def snapClicked(self):
        l = QtCore.QMutexLocker(self.lock)
        self.takeSnap = True

    def toggleRecord(self, b):
        l = QtCore.QMutexLocker(self.lock)
        try:
            if b:
                self.recordStart = True
            else:
                if self.recording:
                    self.recordStop = True
        finally:
            l.unlock()

    def stop(self):
        l = QtCore.QMutexLocker(self.lock)
        self.stopThread = True
        l.unlock()
