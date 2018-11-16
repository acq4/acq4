from __future__ import print_function
import time, types, os.path, re, sys
from acq4.util import Qt
import acq4.pyqtgraph as pg
from acq4.pyqtgraph import SignalProxy, Point
import acq4.pyqtgraph.dockarea as dockarea
import acq4.util.ptime as ptime
from acq4.util.Mutex import Mutex
import numpy as np
import scipy.ndimage
from acq4.util.debug import printExc, Profiler
from acq4.util.metaarray import *
import acq4.Manager as Manager
from .CameraInterfaceTemplate import Ui_Form as CameraInterfaceTemplate
from acq4.devices.OptomechDevice import DeviceTreeItemGroup
from acq4.util.imaging import ImagingCtrl
from acq4.modules.Camera import CameraModuleInterface


class CameraInterface(CameraModuleInterface):
    """
    This class provides all the functionality necessary for a camera to display 
    images and controls within the camera module's main window. Each camera that 
    connects to a camera module must implement an instance of this interface.
    
    The interface provides a control GUI via the controlWidget() method and 
    directly manages its own GraphicsItems within the camera module's view box.
    """
    
    sigNewFrame = Qt.Signal(object, object)  # self, frame
    
    def __init__(self, camera, module):
        CameraModuleInterface.__init__(self, camera, module)

        self.module = module
        self.view = module.getView()
        self.hasQuit = False
        self.boundaryItems = {}

        ## setup UI
        self.ui = CameraInterfaceTemplate()
        self.widget = dockarea.DockArea()
        w = Qt.QWidget()
        self.ui.setupUi(w)

        # takes care of displaying image data, 
        # contrast & background subtraction user interfaces
        self.imagingCtrl = ImagingCtrl()
        self.frameDisplay = self.imagingCtrl.frameDisplay

        ## Move control panels into docks
        recDock = dockarea.Dock(name="Recording", widget=self.imagingCtrl, size=(100, 10), autoOrientation=False)
        devDock = dockarea.Dock(name="Device Control", widget=self.ui.devCtrlWidget, size=(100, 10), autoOrientation=False)
        dispDock = dockarea.Dock(name="Display Control", widget=self.frameDisplay.contrastWidget(), size=(100, 600), autoOrientation=False)
        bgDock = dockarea.Dock(name="Background Subtraction", widget=self.frameDisplay.backgroundWidget(), size=(100, 10), autoOrientation=False)
        self.widget.addDock(recDock)
        self.widget.addDock(devDock, 'bottom', recDock)
        self.widget.addDock(dispDock, 'bottom', devDock)
        self.widget.addDock(bgDock, 'bottom', dispDock)
        
        ## Camera state variables
        self.cam = camera
        self.roi = None
        self.exposure = 0.001
        self.binning = 1
        self.region = None

        ## set up item groups
        self.cameraItemGroup = pg.ItemGroup()  ## translated with scope, scaled with camera objective
        self.imageItemGroup = pg.ItemGroup()   ## translated and scaled as each frame arrives
        self.view.addItem(self.imageItemGroup)
        self.view.addItem(self.cameraItemGroup)
        self.cameraItemGroup.setZValue(0)
        self.imageItemGroup.setZValue(-2)

        ## video image item
        self.imageItem = self.frameDisplay.imageItem()
        self.view.addItem(self.imageItem)
        self.imageItem.setParentItem(self.imageItemGroup)
        self.imageItem.setZValue(-10)

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
        self.borders = CameraItemGroup(self.cam)
        self.module.addItem(self.borders)
        self.borders.setZValue(-1)
        
        self.cam.sigGlobalTransformChanged.connect(self.globalTransformChanged)
        
        self.globalTransformChanged()

        # initially set binning and exposure from camera state
        self.exposure = self.cam.getParam('exposure')
        self.binning = self.cam.getParam('binning')[0]
        ## Initialize values/connections in Camera Dock
        self.setUiBinning(self.binning)
        self.ui.spinExposure.setValue(self.exposure)
        self.ui.spinExposure.setOpts(dec=True, step=1, minStep=100e-6, siPrefix=True, suffix='s', bounds=[0, 10])

        #Signals from self.ui.btnSnap and self.ui.recordStackBtn are caught by the RecordThread
        self.ui.btnFullFrame.clicked.connect(lambda: self.setRegion())
        self.binningComboProxy = SignalProxy(self.ui.binningCombo.currentIndexChanged, slot=self.binningComboChanged)
        self.ui.spinExposure.valueChanged.connect(self.setExposure)  ## note that this signal (from acq4.util.SpinBox) is delayed.

        ## Signals from Camera device
        self.cam.sigNewFrame.connect(self.newFrame)
        self.cam.sigCameraStopped.connect(self.cameraStopped)
        self.cam.sigCameraStarted.connect(self.cameraStarted)
        self.cam.sigShowMessage.connect(self.showMessage)
        self.cam.sigParamsChanged.connect(self.cameraParamsChanged)

        self.frameDisplay.imageUpdated.connect(self.imageUpdated)
        self.imagingCtrl.sigStartVideoClicked.connect(self.startAcquireClicked)
        self.imagingCtrl.sigStopVideoClicked.connect(self.stopAcquireClicked)
        self.imagingCtrl.ui.acquireFrameBtn.setEnabled(False)

        # Hotkey signals
        for action, key in self.cam.camConfig.get('hotkeys', {}).items():
            if action not in ['snap', 'start']:
                raise ValueError("Unknown hotkey action %r" % action)
            
            dev = Manager.getManager().getDevice(key['device'])
            dev.addKeyCallback(key['key'], self.hotkeyPressed, (action,))
    
    def newFrame(self, frame):
        self.imagingCtrl.newFrame(frame)
        self.sigNewFrame.emit(self, frame)

    def controlWidget(self):
        return self.widget
        
    def openCamera(self, ind=0):
        try:
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

    def imageUpdated(self, frame):
        ## New image is displayed; update image transform
        self.imageItem.setTransform(frame.frameTransform().as2D())
        
        ## Update viewport to correct for scope movement/scaling
        tr = pg.SRTTransform(frame.deviceTransform())
        self.updateTransform(tr)

        self.imageItemGroup.setTransform(tr)
            
    def updateTransform(self, tr):
        ## update view for new transform such that sensor bounds remain stationary on screen.
        pos = tr.getTranslation()
        
        scale = tr.getScale()
        if scale != self.lastCameraScale:
            anchor = self.view.mapViewToDevice(self.lastCameraPosition)
            self.view.scaleBy(scale / self.lastCameraScale)
            Qt.QApplication.processEvents()
            anchor2 = self.view.mapDeviceToView(anchor)
            diff = pos - anchor2
            self.lastCameraScale = scale
        else:
            diff = pos - self.lastCameraPosition
            
        self.view.translateBy(diff)
        self.lastCameraPosition = pos
        self.cameraItemGroup.setTransform(tr)

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
        self.imagingCtrl.quit()

        if self.hasQuit:
            return

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

    def hotkeyPressed(self, device, keys, action):
        callback = {
            'snap': self.imagingCtrl.saveFrameClicked,
            'start': self.imagingCtrl.acquireVideoClicked,
        }.get(action)
        
        callback()

    def cameraStopped(self):
        self.imagingCtrl.acquisitionStopped()

    def cameraStarted(self):
        self.imagingCtrl.acquisitionStarted()

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

    def setUiBinning(self, b, updateCamera=True):
        ind = self.ui.binningCombo.findText(str(b))
        if ind == -1:
            raise Exception("Binning mode %s not in list." % str(b))

        if updateCamera:
            self.ui.binningCombo.setCurrentIndex(ind)
        else:
            with self.binningComboProxy.block():
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

        m = self.cam.globalTransform()
        self.cameraItemGroup.setTransform(pg.SRTTransform(m))

    def setRegion(self, rgn=None):
        if rgn is None:
            rgn = [0, 0, self.camSize[0]-1, self.camSize[1]-1]
        self.roi.setPos([rgn[0], rgn[1]])
        self.roi.setSize([self.camSize[0], self.camSize[1]])

    def cameraParamsChanged(self, changes):
        # camera parameters changed; update ui to match
        if 'exposure' in changes:
            with pg.SignalBlock(self.ui.spinExposure.valueChanged, self.setExposure):
                self.ui.spinExposure.setValue(changes['exposure'])

        if 'binningX' in changes:
            self.setUiBinning(changes['binningX'], updateCamera=False)
        elif 'binning' in changes:
            self.setUiBinning(changes['binning'][0], updateCamera=False)
        
        if 'region' in changes:
            with pg.SignalBlock(self.roi.sigRegionChangeFinished, self.regionWidgetChanged):
                rgn = changes['region']
                self.roi.setPos([rgn[0], rgn[1]])
                self.roi.setSize([rgn[2], rgn[3]])
        if 'regionX' in changes or 'regionY' in changes:
            with pg.SignalBlock(self.roi.sigRegionChangeFinished, self.regionWidgetChanged):
                x = changes.get('regionX', self.roi.pos().x())
                y = changes.get('regionY', self.roi.pos().y())
                self.roi.setPos([x, y])
        if 'regionW' in changes or 'regionH' in changes:
            with pg.SignalBlock(self.roi.sigRegionChangeFinished, self.regionWidgetChanged):
                w = changes.get('regionW', self.roi.state['size'][0])
                h = changes.get('regionH', self.roi.state['size'][1])
                self.roi.setSize([w, h])

    def startAcquireClicked(self, mode):
        """User clicked the acquire video button.
        """
        try:
            self.cam.setParam('triggerMode', 'Normal', autoRestart=False)
            self.setBinning(autoRestart=False)
            self.setExposure(autoRestart=False)
            self.updateRegion(autoRestart=False)
            self.cam.start()
            Manager.logMsg("Camera started aquisition.", importance=0)
        except:
            self.imagingCtrl.acquisitionStopped()
            printExc("Error starting camera:")

    def stopAcquireClicked(self):
        self.cam.stop()
        Manager.logMsg("Camera stopped acquisition.", importance=0)

    def showMessage(self, msg, delay=2000):
        self.module.showMessage(msg, delay)

    def getImageItem(self):
        return self.imageItem

    def boundingRect(self):
        """
        Return bounding rect of this imaging device in global coordinates
        """
        return self.cam.getBoundary().boundingRect()

    def takeImage(self, closeShutter=None):
        # closeShutter is used for laser scanning devices; we can ignore it here.
        return self.getDevice().acquireFrames(1, stack=False)

            
class CameraItemGroup(DeviceTreeItemGroup):
    def __init__(self, camera, includeSubdevices=True):
        DeviceTreeItemGroup.__init__(self, device=camera, includeSubdevices=includeSubdevices)
        
    def makeGroup(self, dev, subdev):
        grp = DeviceTreeItemGroup.makeGroup(self, dev, subdev)
        if dev is self.device:
            bound = Qt.QGraphicsPathItem(self.device.getBoundary(globalCoords=False))
            bound.setParentItem(grp)
            bound.setPen(pg.mkPen(40, 150, 150))
        return grp
        
        
class CamROI(pg.ROI):
    """Used for specifying the ROI for a camera to acquire from"""
    def __init__(self, size, parent=None):
        pg.ROI.__init__(self, pos=[0,0], size=size, maxBounds=Qt.QRectF(0, 0, size[0], size[1]), scaleSnap=True, translateSnap=True, parent=parent)
        self.addScaleHandle([0, 0], [1, 1])
        self.addScaleHandle([1, 0], [0, 1])
        self.addScaleHandle([0, 1], [1, 0])
        self.addScaleHandle([1, 1], [0, 0])
