import time, types, os.path, re, sys
from PyQt4 import QtGui, QtCore
import acq4.pyqtgraph as pg
from acq4.pyqtgraph import SignalProxy, Point
import acq4.pyqtgraph.dockarea as dockarea
import acq4.util.ptime as ptime
from acq4.util.Mutex import Mutex
import numpy as np
import scipy.ndimage
from acq4.util.debug import *
import acq4.util.debug as debug
from acq4.util.metaarray import *
import acq4.Manager as Manager
from RecordThread import RecordThread
from CameraInterfaceTemplate import Ui_Form as CameraInterfaceTemplate
from acq4.devices.OptomechDevice import DeviceTreeItemGroup

        
class CameraInterface(QtCore.QObject):
    """
    This class provides all the functionality necessary for a camera to display images and controls within the camera module's main window. Each camera that connects to a camera module must implement an instance of this interface.
    
    The interface provides a control GUI via the controlWidget() method and directly manages its own GraphicsItems
    within the camera module's view box.
    """
    
    sigNewFrame = QtCore.Signal(object, object)  # self, frame
    
    def __init__(self, camera, module):
        QtCore.QObject.__init__(self)
        self.module = module
        self.view = module.getView()
        self.hasQuit = False
        self.persistentFrames = []
        self.boundaryItems = {}

        ## setup UI
        self.ui = CameraInterfaceTemplate()
        self.widget = dockarea.DockArea()
        w = QtGui.QWidget()
        self.ui.setupUi(w)

        ## Move control panels into docks
        recDock = dockarea.Dock(name="Recording", widget=self.ui.recordCtrlWidget, size=(100, 10), autoOrientation=False)
        devDock = dockarea.Dock(name="Device Control", widget=self.ui.devCtrlWidget, size=(100, 10), autoOrientation=False)
        dispDock = dockarea.Dock(name="Display Control", widget=self.ui.displayCtrlWidget, size=(100, 600), autoOrientation=False)
        bgDock = dockarea.Dock(name="Background Subtraction", widget=self.ui.bgSubtractWidget, size=(100, 10), autoOrientation=False)
        self.widget.addDock(recDock)
        self.widget.addDock(devDock, 'bottom', recDock)
        self.widget.addDock(dispDock, 'bottom', devDock)
        self.widget.addDock(bgDock, 'bottom', dispDock)
        
        ## format labels
        self.ui.fpsLabel.setFormatStr('{avgValue:.1f} fps')
        self.ui.fpsLabel.setAverageTime(2.0)
        self.ui.displayFpsLabel.setFormatStr('{avgValue:.1f} fps')
        self.ui.displayFpsLabel.setAverageTime(2.0)
        self.ui.displayPercentLabel.setFormatStr('({avgValue:.1f}%)')
        self.ui.displayPercentLabel.setAverageTime(4.0)

        
        ## Camera state variables
        self.cam = camera
        self.roi = None
        self.exposure = 0.001
        self.binning = 1
        self.region = None

        ## Frame handling variables
        self.nextFrame = None
        self.updateFrame = False
        self.currentFrame = None
        self.backgroundFrame = None
        self.blurredBackgroundFrame = None
        self.lastDrawTime = None
        self.bgStartTime = None
        self.bgFrameCount = 0
        self.lastMinMax = None  ## Records most recently measured maximum/minimum image values
        self.autoGainLevels = [0.0, 1.0]
        self.ignoreLevelChange = False



        ## set up item groups
        #self.scopeItemGroup = pg.ItemGroup()   ## translated as scope moves
        self.cameraItemGroup = pg.ItemGroup()  ## translated with scope, scaled with camera objective
        self.imageItemGroup = pg.ItemGroup()   ## translated and scaled as each frame arrives
        self.view.addItem(self.imageItemGroup)
        self.view.addItem(self.cameraItemGroup)
        #self.view.addItem(self.scopeItemGroup)
        #self.scopeItemGroup.setZValue(10)
        self.cameraItemGroup.setZValue(0)
        self.imageItemGroup.setZValue(-2)

        ## video image item
        self.imageItem = pg.ImageItem()
        self.view.addItem(self.imageItem)
        self.imageItem.setParentItem(self.imageItemGroup)
        self.imageItem.setZValue(-10)
        self.ui.histogram.setImageItem(self.imageItem)
        self.ui.histogram.fillHistogram(False)  ## for speed

        ## set up recording thread
        self.recordThread = RecordThread(self)
        self.recordThread.start()
        self.recordThread.sigShowMessage.connect(self.showMessage)
        self.recordThread.finished.connect(self.recordThreadStopped)
        self.recordThread.sigRecordingFinished.connect(self.recordFinished)
        self.recordThread.sigRecordingFailed.connect(self.recordingFailed)

        ## open camera, determine bit depth and sensor area
        self.openCamera()

        ## Initialize values
        self.lastCameraPosition = Point(self.camSize[0]*0.5, self.camSize[1]*0.5)
        self.lastCameraScale = Point(1.0, 1.0)
        self.scopeCenter = [self.camSize[0]*0.5, self.camSize[1]*0.5]
        self.cameraScale = [1, 1]

        ## Camera region-of-interest control
        self.roi = CamROI(self.camSize, parent=self.cameraItemGroup)
        self.roi.sigRegionChangeFinished.connect(self.regionWidgetChanged)
        self.roi.setZValue(-1)
        self.setRegion()

        ## Set up microscope objective borders
        #self.borders = []
        self.borders = CameraItemGroup(self.cam)
        self.module.addItem(self.borders)
        self.borders.setZValue(-1)
        
        self.cam.sigGlobalTransformChanged.connect(self.globalTransformChanged)
        #self.cam.sigGlobalSubdeviceTransformChanged.connect(self.rebuildBoundaryItems)
        #self.cam.sigGlobalSubdeviceChanged.connect(self.rebuildBoundaryItems)
        
        self.globalTransformChanged()
        #self.rebuildBoundaryItems()

        ## Initialize values/connections in Camera Dock
        self.setUiBinning(self.binning)
        self.ui.spinExposure.setValue(self.exposure)
        self.ui.spinExposure.setOpts(dec=True, step=1, minStep=100e-6, siPrefix=True, suffix='s', bounds=[0, 10])

        ## connect UI signals
        self.ui.acquireVideoBtn.clicked.connect(self.toggleAcquire)
        self.ui.recordStackBtn.toggled.connect(self.toggleRecord)
        #Signals from self.ui.btnSnap and self.ui.recordStackBtn are caught by the RecordThread
        self.ui.btnFullFrame.clicked.connect(lambda: self.setRegion())
        #self.ui.scaleToImageBtn.clicked.connect(self.scaleToImage)
        self.proxy1 = SignalProxy(self.ui.binningCombo.currentIndexChanged, slot=self.binningComboChanged)
        self.ui.spinExposure.valueChanged.connect(self.setExposure)  ## note that this signal (from acq4.util.SpinBox) is delayed.

        ## Signals from Camera device
        self.cam.sigNewFrame.connect(self.newFrame)
        self.cam.sigCameraStopped.connect(self.cameraStopped)
        self.cam.sigCameraStarted.connect(self.cameraStarted)
        self.cam.sigShowMessage.connect(self.showMessage)

        ## Connect Background Subtraction Dock
        self.ui.bgBlurSpin.valueChanged.connect(self.updateBackgroundBlur)
        self.ui.collectBgBtn.clicked.connect(self.collectBgClicked)
        self.ui.divideBgBtn.clicked.connect(self.divideClicked)
        self.ui.subtractBgBtn.clicked.connect(self.subtractClicked)
        self.ui.bgBlurSpin.valueChanged.connect(self.requestFrameUpdate)
        
        ## Connect DisplayGain dock
        self.ui.histogram.sigLookupTableChanged.connect(self.levelsChanged)
        self.ui.histogram.sigLevelsChanged.connect(self.levelsChanged)
        self.ui.btnAutoGain.toggled.connect(self.toggleAutoGain)
        self.ui.btnAutoGain.setChecked(True)
        self.ui.zoomLiveBtn.clicked.connect(self.module.centerView)
        self.alpha = 1
        self.ui.alphaSlider.valueChanged.connect(self.alphaChanged)

        ## Check for new frame updates every 16ms
        ## Some checks may be skipped even if there is a new frame waiting to avoid drawing more than
        ## 60fps.
        self.frameTimer = QtCore.QTimer()
        self.frameTimer.timeout.connect(self.drawFrame)
        self.frameTimer.start(32) ## draw frames no faster than 60Hz
        #QtCore.QTimer.singleShot(1, self.drawFrame)
        ## avoiding possible singleShot-induced crashes

        ## Connect Persistent Frames dock
        self.ui.frameToBgBtn.clicked.connect(self.addPersistentFrame)
        #self.ui.clearFramesBtn.clicked.connect(self.clearPersistentFrames)

        
        
    def controlWidget(self):
        return self.widget
        
    def openCamera(self, ind=0):
        try:
            self.bitDepth = self.cam.getParam('bitDepth')
            #self.setLevelRange()
            self.camSize = self.cam.getParam('sensorSize')
            self.showMessage("Opened camera %s" % self.cam, 5000)
            self.scope = self.cam.getScopeDevice()

            try:
                bins = self.cam.listParams('binning')[0][0]
            except:
                bins = self.cam.listParams('binningX')[0]
            bins.sort()
            bins.reverse()
            for b in bins:
                self.ui.binningCombo.addItem(str(b))


        except:
            self.showMessage("Error opening camera")
            raise


    def globalTransformChanged(self, emitter=None, changedDev=None, transform=None):
        ## scope has moved; update viewport and camera outlines.
        ## This is only used when the camera is not running--
        ## if the camera is running, then this is taken care of in drawFrame to
        ## ensure that the image remains stationary on screen.
        if not self.cam.isRunning():
            tr = pg.SRTTransform(self.cam.globalTransform())
            self.updateTransform(tr)
            
    def updateTransform(self, tr):
        ## update view for new transform such that sensor bounds remain stationary on screen.
        pos = tr.getTranslation()
        
        scale = tr.getScale()
        if scale != self.lastCameraScale:
            anchor = self.view.mapViewToDevice(self.lastCameraPosition)
            self.view.scaleBy(scale / self.lastCameraScale)
            anchor2 = self.view.mapDeviceToView(anchor)
            diff = pos - anchor2
            self.lastCameraScale = scale
        else:
            diff = pos - self.lastCameraPosition
            
        self.view.translateBy(diff)
        self.lastCameraPosition = pos
        self.cameraItemGroup.setTransform(tr)
        

    #@trace
    #def updateBorders(self):
        #"""Draw the camera boundaries for each objective"""
        #for b in self.borders:
            #self.view.removeItem(b)
        #self.borders = []

        #scope = self.module.cam.getScopeDevice()
        #if scope is None:
            #return

        #bounds = self.module.cam.getBoundaries()
        #for b in bounds:
            #border = QtGui.QGraphicsRectItem(QtCore.QRectF(0, 0, 1, 1), self.scopeItemGroup)
            #border.scale(b.width(), b.height())
            #border.setPos(b.x(), b.y())
            #border.setAcceptedMouseButtons(QtCore.Qt.NoButton)
            #border.setPen(QtGui.QPen(QtGui.QColor(50,80,80)))
            #border.setZValue(10)
            #self.scopeItemGroup.resetTransform()
            #self.borders.append(border)
        #self.updateCameraDecorations()


    def toggleRecord(self, b):
        if b:
            self.ui.recordStackBtn.setChecked(True)
            self.ui.recordXframesCheck.setEnabled(False)
            self.ui.recordXframesSpin.setEnabled(False)
            #self.ui.framesLabel.setEnabled(False)
        else:
            self.ui.recordStackBtn.setChecked(False)
            self.ui.recordXframesCheck.setEnabled(True)
            self.ui.recordXframesSpin.setEnabled(True)
            #self.ui.framesLabel.setEnabled(True)

    def recordFinished(self):
        self.toggleRecord(False)

    def recordThreadStopped(self):
        self.toggleRecord(False)
        self.ui.recordStackBtn.setEnabled(False)  ## Recording thread has stopped, can't record anymore.
        self.showMessage("Recording thread died! See console for error message.")

    def recordingFailed(self):
        self.toggleRecord(False)
        self.showMessage("Recording failed! See console for error message.")


    def levelsChanged(self):
        if self.ui.btnAutoGain.isChecked() and not self.ignoreLevelChange:
            if self.lastMinMax is None:
                return
            bl, wl = self.getLevels()
            mn, mx = self.lastMinMax
            rng = float(mx-mn)
            if rng == 0:
                return
            newLevels = [(bl-mn) / rng, (wl-mn) / rng]
            #print "autogain:", newLevels
            #import traceback
            #print "\n".join(traceback.format_stack())
            self.autoGainLevels = newLevels
        #self.requestFrameUpdate()
        
    def alphaChanged(self, val):
        self.alpha = val/100.0 ## slider only works in integers and we need a 0 to 1 value


    def requestFrameUpdate(self):
        self.updateFrame = True


    def divideClicked(self):
        self.lastMinMax = None
        self.ui.subtractBgBtn.setChecked(False)

    def subtractClicked(self):
        self.lastMinMax = None
        self.ui.divideBgBtn.setChecked(False)


    def regionWidgetChanged(self, *args):
        self.updateRegion()




    def updateRegion(self, autoRestart=True):
        #self.clearFrameBuffer()
        r = self.roi.parentBounds()
        newRegion = [int(r.left()), int(r.top()), int(r.width()), int(r.height())]
        if self.region != newRegion:
            self.region = newRegion
            self.cam.setParam('region', self.region, autoRestart=autoRestart)


    def quit(self):
        if self.hasQuit:
            return

        try:
            self.recordThread.sigShowMessage.disconnect(self.showMessage)
            self.recordThread.finished.disconnect(self.recordThreadStopped)
            self.recordThread.sigRecordingFailed.disconnect(self.recordingFailed)
            self.recordThread.sigRecordingFinished.disconnect(self.recordFinished)
        except TypeError:
            pass

        try:
            self.cam.sigNewFrame.disconnect(self.newFrame)
            self.cam.sigCameraStopped.disconnect(self.cameraStopped)
            self.cam.sigCameraStarted.disconnect(self.cameraStarted)
            self.cam.sigShowMessage.disconnect(self.showMessage)
        except TypeError:
            pass

        self.hasQuit = True
        if self.cam.isRunning():
            self.cam.stop()
            if not self.cam.wait(10000):
                printExc("Timed out while waiting for acq thread exit!")
        if self.recordThread.isRunning():
            self.recordThread.stop()
            if not self.recordThread.wait(10000):
                raise Exception("Timed out while waiting for rec. thread exit!")
        del self.recordThread  ## Required due to cyclic reference

    def cameraStopped(self):
        self.toggleRecord(False)
        #self.backgroundFrame = None
        self.ui.acquireVideoBtn.setChecked(False)
        self.ui.acquireVideoBtn.setEnabled(True)


    def cameraStarted(self):
        #self.AGCLastMax = None
        #self.AGCLastMin = None
        self.ui.acquireVideoBtn.setChecked(True)
        self.ui.acquireVideoBtn.setEnabled(True)

    def binningComboChanged(self, args):
        self.setBinning(*args)


    def setBinning(self, ind=None, autoRestart=True):
        """Set camera's binning value. If ind is specified, it is the index from binningCombo from which to grab the new binning value."""
        #self.backgroundFrame = None
        if ind is not None:
            self.binning = int(self.ui.binningCombo.itemText(ind))
        self.cam.setParam('binning', (self.binning, self.binning), autoRestart=autoRestart)
        #self.clearFrameBuffer()
        ###self.updateRgnLabel()

    def setUiBinning(self, b):
        ind = self.ui.binningCombo.findText(str(b))
        if ind == -1:
            raise Exception("Binning mode %s not in list." % str(b))
        self.ui.binningCombo.setCurrentIndex(ind)


    def setExposure(self, e=None, autoRestart=True):
        if e is not None:
            self.exposure = e
        self.cam.setParam('exposure', self.exposure, autoRestart=autoRestart)




    def updateCameraDecorations(self):
        ps = self.cameraScale
        pos = self.lastCameraPosition
        cs = self.camSize
        if ps is None:
            return

        ## move scope group
        #m = QtGui.QTransform()
        #m.translate(self.scopeCenter[0], self.scopeCenter[1])
        #self.scopeItemGroup.setTransform(m)

        ## move and scale camera group
        #m = QtGui.QTransform()
        #m.translate(pos[0], pos[1])
        #m.scale(ps[0], ps[1])
        #m.translate(-cs[0]*0.5, -cs[1]*0.5)
        m = self.cam.globalTransform()
        self.cameraItemGroup.setTransform(pg.SRTTransform(m))






    def setRegion(self, rgn=None):
        #self.backgroundFrame = None
        if rgn is None:
            rgn = [0, 0, self.camSize[0]-1, self.camSize[1]-1]
        self.roi.setPos([rgn[0], rgn[1]])
        self.roi.setSize([self.camSize[0], self.camSize[1]])
        #self.updateRegion()


    #def updateRgnLabel(self):
        #img = self.imageItem.image
        #if img is None:
            #return
        #self.rgnLabel.setText('[%d, %d, %d, %d] %dx%d' % (self.region[0], self.region[1], (img.shape[0]-1)*self.binning, (img.shape[1]-1)*self.binning, self.binning, self.binning))


    def getLevels(self):
        return self.ui.histogram.getLevels()


    def toggleAutoGain(self, b):
        if b:
            self.lastAGCMax = None
            self.ui.histogram.vb.setMouseEnabled(x=False, y=False)
            #self.ui.histogram.setLevels(*self.lastMinMax)
        else:
            self.ui.histogram.vb.setMouseEnabled(x=False, y=True)



    def toggleAcquire(self):
        if self.ui.acquireVideoBtn.isChecked():
            try:
                self.cam.setParam('triggerMode', 'Normal', autoRestart=False)
                self.setBinning(autoRestart=False)
                self.setExposure(autoRestart=False)
                self.updateRegion(autoRestart=False)
                self.cam.start()
                Manager.logMsg("Camera started aquisition.", importance=0)
            except:
                self.ui.acquireVideoBtn.setChecked(False)
                printExc("Error starting camera:")
        
        else:
            #print "ACQ untoggled, stop record"
            self.toggleRecord(False)
            self.cam.stop()
            Manager.logMsg("Camera stopped acquisition.", importance=0)

    def newFrame(self, frame):
        
        lf = None
        if self.nextFrame is not None:
            lf = self.nextFrame
        elif self.currentFrame is not None:
            lf = self.currentFrame
        
        if lf is not None:
            fps = frame.info()['fps']
            if fps is not None:
                self.ui.fpsLabel.setValue(fps)
        
        ## Update ROI plots, if any
        #if self.ui.checkEnableROIs.isChecked():
            #self.addPlotFrame(frame)
        
        ## self.nextFrame gets picked up by drawFrame() at some point
        if self.nextFrame is not None:
            self.ui.displayPercentLabel.setValue(0.)
        else:
            self.ui.displayPercentLabel.setValue(100.)
        
        self.nextFrame = frame
        
        ## stop collecting bg frames if we are in static mode and time is up
        if self.ui.collectBgBtn.isChecked() and not self.ui.contAvgBgCheck.isChecked():
            timeLeft = self.ui.bgTimeSpin.value() - (ptime.time()-self.bgStartTime)
            if timeLeft > 0:
                self.ui.collectBgBtn.setText("Collecting... (%d)" % int(timeLeft+1))
            else:
                self.ui.collectBgBtn.setChecked(False)
                self.ui.collectBgBtn.setText("Collect Background")
        
        if self.ui.collectBgBtn.isChecked():
            if self.ui.contAvgBgCheck.isChecked():
                x = 1.0 - 1.0 / (self.ui.bgTimeSpin.value()+1.0)
            else:
                x = float(self.bgFrameCount)/(self.bgFrameCount + 1)
                self.bgFrameCount += 1
            
            if self.backgroundFrame == None or self.backgroundFrame.shape != frame.data().shape:
                self.backgroundFrame = frame.data().astype(float)
            else:
                self.backgroundFrame = x * self.backgroundFrame + (1-x)*frame.data().astype(float)
        
        self.sigNewFrame.emit(self, frame)
    
    
    def collectBgClicked(self, checked):
        if checked:
            if not self.ui.contAvgBgCheck.isChecked():
                self.backgroundFrame = None ## reset background frame
                self.bgFrameCount = 0
                self.bgStartTime = ptime.time()
            self.ui.collectBgBtn.setText("Collecting...")
        else:
            self.ui.collectBgBtn.setText("Collect Background")

    def updateBackgroundBlur(self):
        b = self.ui.bgBlurSpin.value()
        if b > 0.0:
            self.blurredBackgroundFrame = scipy.ndimage.gaussian_filter(self.backgroundFrame, (b, b))
        else:
            self.blurredBackgroundFrame = self.backgroundFrame

    def getBackgroundFrame(self):
        if self.backgroundFrame is None:
            return None
        self.updateBackgroundBlur()
        return self.blurredBackgroundFrame


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
            
            prof = debug.Profiler('CameraWindow.drawFrame', disabled=True)
            prof.mark()
            ## We will now draw a new frame (even if the frame is unchanged)
            if self.lastDrawTime is not None:
                fps = 1.0 / (t - self.lastDrawTime)
                self.ui.displayFpsLabel.setValue(fps)
            self.lastDrawTime = t
            prof.mark()
            
            ## Handle the next available frame, if there is one.
            if self.nextFrame is not None:
                self.currentFrame = self.nextFrame
                self.nextFrame = None
            
            data = self.currentFrame.data()
            info = self.currentFrame.info()
            prof.mark()
            
            
            ## divide the background out of the current frame if needed
            if self.ui.divideBgBtn.isChecked():
                bg = self.getBackgroundFrame()
                if bg is not None and bg.shape == data.shape:
                    data = data / bg
            elif self.ui.subtractBgBtn.isChecked():
                bg = self.getBackgroundFrame()
                if bg is not None and bg.shape == data.shape:
                    data = data - bg
            prof.mark()
            
            ## Set new levels if auto gain is enabled
            if self.ui.btnAutoGain.isChecked():
                cw = self.ui.spinAutoGainCenterWeight.value()
                (w,h) = data.shape
                center = data[w/2.-w/6.:w/2.+w/6., h/2.-h/6.:h/2.+h/6.]
                minVal = data.min() * (1.0-cw) + center.min() * cw
                maxVal = data.max() * (1.0-cw) + center.max() * cw

                ## If there is inf/nan in the image, strip it out before computing min/max
                if any([np.isnan(minVal), np.isinf(minVal),  np.isnan(minVal), np.isinf(minVal)]):
                    nanMask = np.isnan(data)
                    infMask = np.isinf(data)
                    valid = data[~nanMask * ~infMask]
                    minVal = valid.min() * (1.0-cw) + center.min() * cw
                    maxVal = valid.max() * (1.0-cw) + center.max() * cw
                
                ## Smooth min/max range to avoid noise
                if self.lastMinMax is None:
                    minVal = minVal
                    maxVal = maxVal
                else:
                    s = 1.0 - 1.0 / (self.ui.spinAutoGainSpeed.value()+1.0)
                    minVal = self.lastMinMax[0] * s + minVal * (1.0-s)
                    maxVal = self.lastMinMax[1] * s + maxVal * (1.0-s)
                
                self.lastMinMax = [minVal, maxVal]
                
                ## and convert fraction of previous range into new levels
                bl = self.autoGainLevels[0] * (maxVal-minVal) + minVal
                wl = self.autoGainLevels[1] * (maxVal-minVal) + minVal
                
                self.ignoreLevelChange = True
                try:
                    self.ui.histogram.setLevels(bl, wl)
                    self.ui.histogram.setHistogramRange(minVal, maxVal, padding=0.05)
                finally:
                    self.ignoreLevelChange = False
            prof.mark()
            
            ## update image in viewport
            self.imageItem.updateImage(data)#, levels=[bl, wl])
            self.imageItem.setOpacity(self.alpha)
            self.imageItem.setTransform(self.currentFrame.frameTransform().as2D())
            prof.mark()
            
            ## Update viewport to correct for scope movement/scaling
            tr = pg.SRTTransform(self.currentFrame.cameraTransform())
            self.updateTransform(tr)

            self.imageItemGroup.setTransform(tr)
            prof.mark()
            
            prof.mark()
            prof.finish()
        
        
        except:
            printExc('Error while drawing new frames:')
        finally:
            pass

    def showMessage(self, msg, delay=2000):
        self.module.showMessage(msg, delay)


    def addPersistentFrame(self):
        """Make a copy of the current camera frame and store it in the background"""
        #px = self.imageItem.getPixmap()
        #if px is None:
        if self.currentFrame is None:
            return
        #im = QtGui.QGraphicsPixmapItem(px.copy())
        data = self.currentFrame.data()
        im = pg.ImageItem(data, levels=self.ui.histogram.getLevels(), lut=self.ui.histogram.getLookupTable(img=data), removable=True)
        im.sigRemoveRequested.connect(self.removePersistentFrame)
        #im.setCacheMode(im.NoCache)
        if len(self.persistentFrames) == 0:
            z = -10000
        else:
            z = self.persistentFrames[-1].zValue() + 1

        #img = self.currentFrame.data()
        #info = self.currentFrame.info()
        #s = info['pixelSize']
        #p = info['imagePosition']
        self.persistentFrames.append(im)
        self.module.addItem(im, z=z)
        im.setTransform(self.currentFrame.globalTransform().as2D())

    def removePersistentFrame(self, fr):
        self.persistentFrames.remove(fr)
        self.module.removeItem(fr)
        fr.sigRemoveRequested.disconnect(self.removePersistentFrame)
        
    def getImageItem(self):
        return self.imageItem

    def boundingRect(self):
        """
        Return bounding rect of this imaging device in global coordinates
        """
        return self.cam.getBoundary().boundingRect()

    #def rebuildBoundaryItems(self):
        #"""Create the tree of graphics items needed to display camera boundaries"""
        #for dev, items in self.boundaryItems.iteritems():
            #for item in items:
                #scene = item.scene()
                #if scene is not None:
                    #scene.removeItem(item)
        #self.boundaryItems = {}  ## device: [items]
        
        #devices = self.cam.parentDevices()
        #parentItems = [None]
        #for dev in devices[::-1]:
            #newItems = []
            #for parent in parentItems:
                #subdevs = dev.listSubdevices()
                #if len(subdevs) > 0:
                    #groups = []
                    #for subdev in subdevs:
                        #group = QtGui.QGraphicsItemGroup()
                        #group.setTransform(pg.SRTTransform(dev.deviceTransform(subdev)))
                        #groups.append(group)
                #else:
                    #group = QtGui.QGraphicsItemGroup()
                    #group.setTransform(pg.SRTTransform(dev.deviceTransform()))
                    #groups = [group]
                
                #if dev is self.cam:
                    #bound = QtGui.QGraphicsPathItem(self.cam.getBoundary(globalCoords=False))
                    #bound.setParentItem(groups[0])
                    #bound.setPen(pg.mkPen(40, 150, 150))
                
                #if parent is None:
                    #for group in groups:
                        #self.module.addItem(group)
                #else:
                    #for group in groups:
                        #group.setParentItem(parent)
                #newItems.extend(groups)
            #parentItems = newItems
            #self.boundaryItems[dev] = newItems
            
class CameraItemGroup(DeviceTreeItemGroup):
    def __init__(self, camera, includeSubdevices=True):
        DeviceTreeItemGroup.__init__(self, device=camera, includeSubdevices=includeSubdevices)
        
    def makeGroup(self, dev, subdev):
        grp = DeviceTreeItemGroup.makeGroup(self, dev, subdev)
        if dev is self.device:
            bound = QtGui.QGraphicsPathItem(self.device.getBoundary(globalCoords=False))
            bound.setParentItem(grp)
            bound.setPen(pg.mkPen(40, 150, 150))
        return grp
        
        
class CamROI(pg.ROI):
    """Used for specifying the ROI for a camera to acquire from"""
    def __init__(self, size, parent=None):
        pg.ROI.__init__(self, pos=[0,0], size=size, maxBounds=QtCore.QRectF(0, 0, size[0], size[1]), scaleSnap=True, translateSnap=True, parent=parent)
        self.addScaleHandle([0, 0], [1, 1])
        self.addScaleHandle([1, 0], [0, 1])
        self.addScaleHandle([0, 1], [1, 0])
        self.addScaleHandle([1, 1], [0, 0])
