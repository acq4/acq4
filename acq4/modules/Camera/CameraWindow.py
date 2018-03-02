# -*- coding: utf-8 -*-
from __future__ import print_function

import time, types, os.path, re, sys, weakref
from collections import OrderedDict
import numpy as np
from acq4.util import Qt
from acq4.LogWindow import LogButton
from acq4.util.StatusBar import StatusBar
import acq4.pyqtgraph as pg
import acq4.pyqtgraph.dockarea as dockarea
import acq4.Manager as Manager
from acq4.util.debug import Profiler
from acq4.util.Thread import Thread
from acq4.util.Mutex import Mutex
from .sequencerTemplate import Ui_Form as SequencerTemplate
from acq4.util.metaarray import MetaArray
from acq4.pyqtgraph import ptime


class CameraWindow(Qt.QMainWindow):
    
    sigInterfaceAdded = Qt.Signal(object, object)
    sigInterfaceRemoved = Qt.Signal(object, object)

    def __init__(self, module):
        self.hasQuit = False
        self.module = module # handle to the rest of the application
        
        self.interfaces = OrderedDict()  # owner: widget
        self.docks = OrderedDict()       # owner: dock
        
        # Start building UI
        Qt.QMainWindow.__init__(self)
        self.setWindowTitle('Camera')
        self.cw = dockarea.DockArea()
        self.setCentralWidget(self.cw)
        self.gv = pg.GraphicsView()
        self.gvDock = dockarea.Dock(name="View", widget=self.gv, hideTitle=True, size=(600,600))
        self.cw.addDock(self.gvDock)
        
        # set up ViewBox
        self.view = pg.ViewBox()
        self.view.enableAutoRange(x=False, y=False)
        self.view.setAspectLocked(True)
        self.gv.setCentralItem(self.view)
        
        # And a plot area for displaying depth-related information
        self.depthPlot = pg.PlotWidget(labels={'left': ('Depth', 'm')})
        self.depthPlot.setYRange(0, 1e-3)
        self.depthPlot.setXRange(-1, 1)
        self.depthPlot.hideAxis('bottom')
        self.depthPlot.setMouseEnabled(x=False)
        self.depthDock = pg.dockarea.Dock(name='Depth', widget=self.depthPlot)
        self.cw.addDock(self.depthDock, 'right')
        self.depthDock.hide()

        # Add a group that will track to the center of the view
        # self.trackedGroup = pg.GroupItem()
        # self.view.addItem(self.trackedGroup)

        # search for all devices that provide a cameraModuleInterface() method
        man = Manager.getManager()
        devices = [man.getDevice(dev) for dev in man.listDevices()]
        ifaces = OrderedDict([(dev.name(), dev.cameraModuleInterface(self)) for dev in devices if hasattr(dev, 'cameraModuleInterface')])
        
        # add each device's control panel in ots own dock
        haveDevs = False
        for dev, iface in ifaces.items():
            if iface is not None:
                haveDevs = True
                self.addInterface(dev, iface)
        
        # Add explanatory label if no devices were found
        if not haveDevs:
            label = Qt.QLabel("No imaging devices available")
            label.setAlignment(Qt.Qt.AlignHCenter | Qt.Qt.AlignVCenter)
            dock = dockarea.Dock(name="nocamera", widget=label, size=(100, 500), hideTitle=True)
            self.cw.addDock(dock, 'left', self.gvDock)

        # Add a dock with ROI buttons and plot
        self.roiWidget = ROIPlotter(self)
        self.roiDock = dockarea.Dock(name='ROI Plot', widget=self.roiWidget, size=(400, 10))
        self.cw.addDock(self.roiDock, 'bottom', self.gvDock)

        # Add timelapse / z stack / mosaic controls
        self.sequencerWidget = ImageSequencer(self)
        self.sequencerDock = dockarea.Dock(name='Image Sequencer', widget=self.sequencerWidget, size=(200, 10))
        self.cw.addDock(self.sequencerDock, 'right', self.roiDock)
        
        #grid = pg.GridItem()
        #self.view.addItem(grid)
        
        #Scale bar
        self.scaleBar = pg.ScaleBar(100e-6, offset=(-20,-20))
        self.scaleBar.setParentItem(self.view)
        
        ## Set up status bar labels
        self.recLabel = Qt.QLabel()
        self.rgnLabel = Qt.QLabel()
        self.xyLabel = Qt.QLabel()
        self.tLabel = Qt.QLabel()
        self.vLabel = Qt.QLabel()
        self.vLabel.setFixedWidth(50)
        self.setStatusBar(StatusBar())
        font = self.xyLabel.font()
        font.setPointSize(8)
        labels = [self.recLabel, self.xyLabel, self.rgnLabel, self.tLabel, self.vLabel]
        for label in labels:
            label.setFont(font)
            self.statusBar().insertPermanentWidget(0, label)

        # Load previous window state
        self.stateFile = os.path.join('modules', self.module.name + '_ui.cfg')
        uiState = module.manager.readConfigFile(self.stateFile)
        if 'geometry' in uiState:
            geom = Qt.QRect(*uiState['geometry'])
            self.setGeometry(geom)
        if 'window' in uiState:
            ws = Qt.QByteArray.fromPercentEncoding(uiState['window'])
            self.restoreState(ws)
        if 'docks' in uiState:
            self.cw.restoreState(uiState['docks'], missing='ignore')
        
        # done with UI
        self.show()
        self.centerView()
        
        self.gv.scene().sigMouseMoved.connect(self.updateMouse)
        
    def addInterface(self, name, iface):
        """Display a new user interface in the camera module.
        """
        assert name not in self.interfaces

        self.interfaces[name] = iface
        widget = iface.controlWidget()
        if widget is not None:
            dock = dockarea.Dock(name=name, widget=iface.controlWidget(), size=(10, 500))
            if len(self.docks) == 0:
                dock.hideTitleBar()
                self.cw.addDock(dock, 'left', self.gvDock)
            else:
                list(self.docks.values())[0].showTitleBar()
                self.cw.addDock(dock, 'below', list(self.docks.values())[0])
            self.docks[name] = dock
        else:
            self.docks[name] = None
        if hasattr(iface, 'sigNewFrame'):
            iface.sigNewFrame.connect(self.newFrame)
        if hasattr(iface, 'sigTransformChanged'):
            iface.sigTransformChanged.connect(self.ifaceTransformChanged)

        self.sigInterfaceAdded.emit(name, iface)

    def removeInterface(self, name):
        self.interfaces[name].quit()

    def _removeInterface(self, iface):
        print("======== remove", iface)
        print(self.interfaces)
        name = None
        if isinstance(iface, CameraModuleInterface):
            for k,v in self.interfaces.items():
                if v is iface:
                    name = k
                    break
        elif isinstance(iface, str):
            name = iface
        else:
            raise TypeError("string or CameraModuleInterface argument required.")

        if name is None:
            raise ValueError("Interface %s not found." % iface)
        iface = self.interfaces.pop(name)
        if hasattr(iface, 'sigNewFrame'):
            pg.disconnect(iface.sigNewFrame, self.newFrame)
        if hasattr(iface, 'sigTransformChanged'):
            pg.disconnect(iface.sigTransformChanged, self.ifaceTransformChanged)
        dock = self.docks.pop(name, None)
        if dock is not None:
            dock.close()

        self.sigInterfaceRemoved.emit(name, iface)

    def getView(self):
        return self.view

    def getDepthView(self):
        self.depthDock.show()
        return self.depthPlot

    def centerView(self):
        if len(self.interfaces) == 0:
            return
        bounds = None
        for iface in self.interfaces.values():
            br = iface.boundingRect()
            if br is None:
                continue
            if bounds is None:
                bounds = br
            else:
                bounds |= br
        if bounds is not None:
            self.setRange(bounds)
        
    def autoRange(self, item=None):
        self.view.autoRange(item=item)
    
    def setRange(self, *args, **kargs):
        self.view.setRange(*args, **kargs)

    def addItem(self, item, pos=(0,0), scale=(1,1), z=None):
        """Adds an item into the scene. The item is placed in the global coordinate system;
        it will stay fixed on the subject even if the scope moves or changes objective."""
        
        self.view.addItem(item)
        
        if pos is None:
            pos = self.view.viewRect().center()
        item.setPos(pg.Point(pos))
        item.scale(scale[0], scale[1])
        if z is not None:
            item.setZValue(z)
    
    def removeItem(self, item):
        self.view.removeItem(item)

    def showMessage(self, msg, delay=2000):
        self.statusBar().showMessage(str(msg), delay)
        
    def closeEvent(self, ev):
        self.quit()

    def quit(self):
        geom = self.geometry()
        uiState = {
            'window': str(self.saveState().toPercentEncoding()), 
            'geometry': [geom.x(), geom.y(), geom.width(), geom.height()],
            'docks': self.cw.saveState()
        }
        Manager.getManager().writeConfigFile(uiState, self.stateFile)
        
        for iface in self.interfaces.values():
            iface.quit()
        
        self.module.quit(fromUi=True)

    def updateMouse(self, pos=None):
        if pos is None:
            if not hasattr(self, 'mouse'):
                return
            pos = self.mouse
        else:
            pos = self.view.mapSceneToView(pos)
        self.mouse = pos
        self.xyLabel.setText("X:%0.1fum Y:%0.1fum" % (pos.x() * 1e6, pos.y() * 1e6))

    def newFrame(self, iface, frame):
        # New frame has arrived from an imaging device; 
        # update ROI plots
        self.roiWidget.newFrame(iface, frame)
    
    def ifaceTransformChanged(self, iface):
        # imaging device moved; update viewport and tracked group.
        # This is only used when the camera is not running--
        # if the camera is running, then this is taken care of in drawFrame to
        # ensure that the image remains stationary on screen.
        prof = Profiler()
        if not self.cam.isRunning():
            tr = pg.SRTTransform(self.cam.globalTransform())
            self.updateTransform(tr)
            
    def updateTransform(self, tr):
        # update view for new transform such that sensor bounds remain stationary on screen.
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
    

class CameraModuleInterface(Qt.QObject):
    """ Base class used to plug new interfaces into the camera module.

    """
    sigNewFrame = Qt.Signal(object, object)  # (self, frame)

    # indicates this is an interface to an imaging device. 
    canImage = True

    def __init__(self, dev, mod):
        Qt.QObject.__init__(self)
        self.mod = weakref.ref(mod)
        self.dev = weakref.ref(dev)
        self._hasQuit = False

    def getDevice(self):
        return self.dev()

    def graphicsItems(self):
        """Return a list of all graphics items displayed by this interface.
        """
        raise NotImplementedError()

    def controlWidget(self):
        """Return a widget to be docked in the camera module window.

        May return None.
        """
        return None

    def boundingRect(self):
        """Return the bounding rectangle of all graphics items.
        """
        raise NotImplementedError()

    def getImageItem(self):
        """Return the ImageItem used to display imaging data from this device.

        May return None.
        """
        return None

    def takeImage(self, closeShutter=None):
        """Request the imaging device to acquire a single frame.

        The optional closeShutter argument is used to tell laser scanning devices whether
        to close their shutter after imaging. Cameras can simply ignore this option.
        """
        # Note: this is a bit kludgy. 
        # Would be nice to have a more natural way of handling this..
        raise NotImplementedError(str(self))

    def quit(self):
        """Called when the interface is removed from the camera module or when
        the camera module is about to quit.
        """
        if self._hasQuit:
            return
        self._hasQuit = True
        for item in self.graphicsItems():
            scene = item.scene()
            if scene is not None:
                scene.removeItem(item)
        self.mod().window()._removeInterface(self)




class PlotROI(pg.ROI):
    def __init__(self, pos, size):
        pg.ROI.__init__(self, pos, size=size, removable=True)
        self.addScaleHandle([1, 1], [0, 0])


class ROIPlotter(Qt.QWidget):
    # ROI plot ctrls
    def __init__(self, mod):
        Qt.QWidget.__init__(self)
        self.mod = weakref.ref(mod)
        self.view = mod.view

        # ROI state variables
        self.lastPlotTime = None
        self.ROIs = []
        self.plotCurves = []

        # Set up UI
        self.roiLayout = Qt.QGridLayout()
        self.roiLayout.setSpacing(0)
        self.roiLayout.setContentsMargins(0,0,0,0)
        self.setLayout(self.roiLayout)

        # rect
        rectPath = Qt.QPainterPath()
        rectPath.addRect(0, 0, 1, 1)
        self.rectBtn = pg.PathButton(path=rectPath)

        # ellipse
        ellPath = Qt.QPainterPath()
        ellPath.addEllipse(0, 0, 1, 1)
        self.ellipseBtn = pg.PathButton(path=ellPath)

        # polygon
        polyPath = Qt.QPainterPath()
        polyPath.moveTo(0,0)
        polyPath.lineTo(2,3)
        polyPath.lineTo(3,1)
        polyPath.lineTo(5,0)
        polyPath.lineTo(2, -2)
        polyPath.lineTo(0,0)
        self.polygonBtn = pg.PathButton(path=polyPath)

        # ruler
        polyPath = Qt.QPainterPath()
        polyPath.moveTo(0, 0)
        polyPath.lineTo(3, -2)
        polyPath.moveTo(0, 0)
        polyPath.lineTo(3, 0)
        polyPath.moveTo(1, 0)
        polyPath.arcTo(-1, -1, 2, 2, 0, 33.69)
        for i in range(5):
            x = i * 3./4.
            y = x * -2./3.
            polyPath.moveTo(x, y)
            polyPath.lineTo(x-0.2, y-0.3)
        self.rulerBtn = pg.PathButton(path=polyPath)

        self.roiLayout.addWidget(self.rectBtn, 0, 0)
        self.roiLayout.addWidget(self.ellipseBtn, 0, 1)
        self.roiLayout.addWidget(self.polygonBtn, 1, 0)
        self.roiLayout.addWidget(self.rulerBtn, 1, 1)
        self.roiTimeSpin = pg.SpinBox(value=5.0, suffix='s', siPrefix=True, dec=True, step=0.5, bounds=(0,None))
        self.roiLayout.addWidget(self.roiTimeSpin, 2, 0, 1, 2)
        self.roiPlotCheck = Qt.QCheckBox('Plot')
        self.roiLayout.addWidget(self.roiPlotCheck, 3, 0, 1, 2)
        
        self.roiPlot = pg.PlotWidget()
        self.roiLayout.addWidget(self.roiPlot, 0, 2, self.roiLayout.rowCount(), 1)

        self.rectBtn.clicked.connect(lambda: self.addROI('rect'))
        self.ellipseBtn.clicked.connect(lambda: self.addROI('ellipse'))
        self.polygonBtn.clicked.connect(lambda: self.addROI('polygon'))
        self.rulerBtn.clicked.connect(lambda: self.addROI('ruler'))

    def addROI(self, roiType):
        pen = pg.mkPen(pg.intColor(len(self.ROIs)))
        center = self.view.viewRect().center()
        #print 'camerawindow.py: addROI:: ', self.view.viewPixelSize()
        size = [x*50 for x in self.view.viewPixelSize()]
        if roiType == 'rect':
            roi = PlotROI(center, size)
        elif roiType == 'ellipse':
            roi = pg.EllipseROI(center, size, removable=True)
        elif roiType == 'polygon':
            pts = [center, center+pg.Point(0, size[1]), center+pg.Point(size[0], 0)]
            roi = pg.PolyLineROI(pts, closed=True, removable=True)
        elif roiType == 'ruler':
            pts = [center, center+pg.Point(size[0], size[1])]
            roi = pg.graphicsItems.ROI.RulerROI(pts, removable=True)
        else:
            raise ValueError("Invalid ROI type %s" % roiType)

        roi.setZValue(40000)
        roi.setPen(pen)
        self.view.addItem(roi)
        plot = self.roiPlot.plot(pen=pen)
        self.ROIs.append({'roi': roi, 'plot': plot, 'vals': [], 'times': []})
        roi.sigRemoveRequested.connect(self.removeROI)

    def removeROI(self, roi):
        self.view.removeItem(roi)
        roi.sigRemoveRequested.disconnect(self.removeROI)
        for i, r in enumerate(self.ROIs):
            if r['roi'] is roi:
                self.roiPlot.removeItem(r['plot'])
                self.ROIs.remove(r)
                break
        
    def clearROIs(self):
        for r in self.ROIs:
            self.view.removeItem(r['roi'])
            self.roiPlot.removeItem(r['plot'])
        self.ROIs = []

    def newFrame(self, iface, frame):
        """New frame has arrived; update ROI plot if needed.
        """
        if not self.roiPlotCheck.isChecked():
            return
        imageItem = iface.getImageItem()
        
        prof = Profiler('CameraWindow.addPlotFrame', disabled=True)
        if imageItem.width() is None:
            return
        
        # Get rid of old frames
        minTime = None
        now = pg.time()
        for r in self.ROIs:
            while len(r['times']) > 0 and r['times'][0] < (now-self.roiTimeSpin.value()):
                r['times'].pop(0)
                r['vals'].pop(0)
            if len(r['times']) > 0 and (minTime is None or r['times'][0] < minTime):
                minTime = r['times'][0]
        if minTime is None:
            minTime = frame.info()['time']
                
        prof.mark('remove old frames')
            
        # add new frame
        draw = False
        if self.lastPlotTime is None or now - self.lastPlotTime > 0.05:
            draw = True
            self.lastPlotTime = now
            
        for r in self.ROIs:
            if isinstance(r['roi'], pg.graphicsItems.ROI.RulerROI):
                continue
            d = r['roi'].getArrayRegion(frame.data(), imageItem, axes=(0,1))
            prof.mark('get array rgn')
            if d is None:
                continue
            if d.size < 1:
                val = 0
            else:
                val = d.mean()
            r['vals'].append(val)
            r['times'].append(frame.info()['time'])
            prof.mark('append')
            if draw:
                r['plot'].setData(np.array(r['times'])-minTime, r['vals'])
                prof.mark('draw')
        prof.finish()


class ImageSequencer(Qt.QWidget):
    """GUI for acquiring z-stacks, timelapse, and mosaic.
    """
    def __init__(self, mod):
        self.mod = weakref.ref(mod)
        Qt.QWidget.__init__(self)

        self.imager = None

        self.ui = SequencerTemplate()
        self.ui.setupUi(self)

        self.ui.zStartSpin.setOpts(value=100e-6, suffix='m', siPrefix=True, step=10e-6, decimals=6)
        self.ui.zEndSpin.setOpts(value=50e-6, suffix='m', siPrefix=True, step=10e-6, decimals=6)
        self.ui.zSpacingSpin.setOpts(min=1e-9, value=1e-6, suffix='m', siPrefix=True, dec=True, minStep=1e-9, step=0.5)
        self.ui.intervalSpin.setOpts(min=0, value=1, suffix='s', siPrefix=True, dec=True, minStep=1e-3, step=1)

        self.updateDeviceList()
        self.ui.statusLabel.setText("[ stopped ]")

        self.thread = SequencerThread()

        self.state = pg.WidgetGroup(self)
        self.state.sigChanged.connect(self.stateChanged)
        mod.sigInterfaceAdded.connect(self.updateDeviceList)
        mod.sigInterfaceRemoved.connect(self.updateDeviceList)
        self.thread.finished.connect(self.threadStopped)
        self.thread.sigMessage.connect(self.threadMessage)
        self.ui.startBtn.clicked.connect(self.startClicked)
        self.ui.pauseBtn.clicked.connect(self.pauseClicked)
        self.ui.setStartBtn.clicked.connect(self.setStartClicked)
        self.ui.setEndBtn.clicked.connect(self.setEndClicked)

    def updateDeviceList(self):
        items = ['Select device..']
        self.ui.deviceCombo.clear()
        for k,v in self.mod().interfaces.items():
            if v.canImage:
                items.append(k)
        self.ui.deviceCombo.setItems(items)

    def selectedImager(self):
        if self.ui.deviceCombo.currentIndex() < 1:
            return None
        else:
            name = self.ui.deviceCombo.currentText()
            return self.mod().interfaces[name]

    def stateChanged(self, name, value):
        if name == 'deviceCombo':
            if self.imager is not None:
                pg.disconnect(self.imager.sigNewFrame, self.newFrame)
            imager = self.selectedImager()
            if imager is not None:
                imager.sigNewFrame.connect(self.newFrame)
            self.imager = imager
        self.updateStatus()

    def makeProtocol(self):
        """Build a description of everything that needs to be done during the sequence.
        """
        prot = {
            'imager': self.selectedImager(),
            'zStack': self.ui.zStackGroup.isChecked(),
            'timelapse': self.ui.timelapseGroup.isChecked(),
        }
        if prot['zStack']:
            start = self.ui.zStartSpin.value()
            end = self.ui.zEndSpin.value()
            spacing = self.ui.zSpacingSpin.value()
            if end < start:
                prot['zStackValues'] = list(np.arange(start, end, -spacing))
            else:
                prot['zStackValues'] = list(np.arange(start, end, spacing))
        else:
            prot['zStackValues'] = [None]

        if prot['timelapse']:
            prot['timelapseCount'] = self.ui.iterationsSpin.value()
            prot['timelapseInterval'] = self.ui.intervalSpin.value()
        else:
            prot['timelapseCount'] = 1
            prot['timelapseInterval'] = 0

        return prot

    def startClicked(self, b):
        if b:
            self.start()
        else:
            self.stop()

    def pauseClicked(self, b):
        self.thread.pause(b)

    def start(self):
        try:
            if self.selectedImager() is None:
                raise Exception("No imaging device selected.")
            prot = self.makeProtocol()
            self.currentProtocol = prot
            dh = Manager.getManager().getCurrentDir().getDir('ImageSequence', create=True, autoIncrement=True)
            dhinfo = prot.copy()
            del dhinfo['imager']
            dh.setInfo(dhinfo)
            prot['storageDir'] = dh
            self.ui.startBtn.setText('Stop')
            self.ui.zStackGroup.setEnabled(False)
            self.ui.timelapseGroup.setEnabled(False)
            self.ui.deviceCombo.setEnabled(False)
            self.thread.start(prot)
        except Exception:
            self.threadStopped()
            raise

    def stop(self):
        self.thread.stop()

    def threadStopped(self):
        self.ui.startBtn.setText('Start')
        self.ui.startBtn.setChecked(False)
        self.ui.zStackGroup.setEnabled(True)
        self.ui.timelapseGroup.setEnabled(True)
        self.ui.deviceCombo.setEnabled(True)
        self.updateStatus()

    def threadMessage(self, message):
        self.ui.statusLabel.setText(message)

    def updateStatus(self):
        prot = self.makeProtocol()
        if prot['timelapse']:
            itermsg = 'iter=0/%d' % prot['timelapseCount']
        else:
            itermsg = 'iter=0'

        if prot['zStack']:
            depthmsg = 'depth=0/%d' % (len(prot['zStackValues']))
        else:
            depthmsg = ''

        msg = '[ stopped  %s %s ]' % (itermsg, depthmsg)
        self.ui.statusLabel.setText(msg)

    def newFrame(self, iface, frame):
        self.thread.newFrame(frame)

    def setStartClicked(self):
        dev = self.selectedImager()
        if dev is None:
            raise Exception("Must select an imaging device first.")
        dev = dev.getDevice()
        self.ui.zStartSpin.setValue(dev.getFocusDepth())

    def setEndClicked(self):
        dev = self.selectedImager()
        if dev is None:
            raise Exception("Must select an imaging device first.")
        dev = dev.getDevice()
        self.ui.zEndSpin.setValue(dev.getFocusDepth())


class SequencerThread(Thread):

    sigMessage = Qt.Signal(object)  # message

    def __init__(self):
        Thread.__init__(self)
        self.prot = None
        self._stop = False
        self._frame = None
        self._paused = False
        self.lock = Mutex(recursive=True)

    def start(self, protocol):
        if self.isRunning():
            raise Exception("Sequence is already running.")
        self.prot = protocol
        self._stop = False
        self.sigMessage.emit('[ running.. ]')
        Thread.start(self)

    def stop(self):
        with self.lock:
            self._stop = True

    def pause(self, p):
        with self.lock:
            self._paused = p

    def newFrame(self, frame):
        with self.lock:
            self._frame = frame

    def run(self):
        try:
            self.runSequence()
        except Exception as e:
            if e.message == 'stopped':
                return
            raise

    def runSequence(self):
        prot = self.prot
        maxIter = prot['timelapseCount']
        interval = prot['timelapseInterval']
        dev = self.prot['imager'].getDevice()

        depths = prot['zStackValues']
        iter = 0
        while True:
            start = time.time()

            running = dev.isRunning()
            dev.stop()
            self.holdImagerFocus(True)
            self.openShutter(True)   # don't toggle shutter between stack frames
            try:
                for depthIndex in range(len(depths)):
                    # Focus motor is unreliable; ask a few times if needed.
                    for i in range(5):
                        try:
                            self.setFocusDepth(depthIndex, depths)
                            break
                        except RuntimeError:
                            if i == 4:
                                print("Did not reach focus after 5 iterations (%g != %g)" % (self.prot['imager'].getDevice().getFocusDepth(), depths[depthIndex]))

                    frame = self.getFrame()
                    self.recordFrame(frame, iter, depthIndex)

                    self.sendStatusMessage(iter, maxIter, depthIndex, depths)

                    # check for stop / pause
                    self.sleep(until=0)

            finally:
                self.openShutter(False)
                self.holdImagerFocus(False)
                if running:
                    dev.start()

            iter += 1
            if maxIter == 0 or iter >= maxIter:
                break

            self.sleep(until=start+interval)

    def sendStatusMessage(self, iter, maxIter, depthIndex, depths):
        if maxIter == 0:
            itermsg = 'iter=%d' % (iter+1)
        else:
            itermsg = 'iter=%d/%s' % (iter+1, maxIter)

        if depthIndex is None:
            depthmsg = ''
        else:
            depthstr = pg.siFormat(depths[depthIndex], suffix='m')
            depthmsg = 'depth=%s %d/%d' % (depthstr, depthIndex+1, len(depths))

        self.sigMessage.emit('[ running  %s  %s ]' % (itermsg, depthmsg))

    def setFocusDepth(self, depthIndex, depths):
        imager = self.prot['imager'].getDevice()
        depth = depths[depthIndex]
        if depth is None:
            return

        dz = depth - imager.getFocusDepth()

        # Avoid hysteresis:
        if depths[0] > depths[-1] and dz > 0:
            # stack goes downward
            imager.setFocusDepth(depth + 20e-6).wait()
        elif depths[0] < depths[-1] and dz < 0:
            # stack goes upward
            imager.setFocusDepth(depth - 20e-6).wait()

        imager.setFocusDepth(depth).wait()

    def holdImagerFocus(self, hold):
        """Tell the focus controller to lock or unlock.
        """
        idev = self.prot['imager'].getDevice()
        fdev = idev.getFocusDevice()
        if fdev is None:
            raise Exception("Device %s is not connected to a focus controller." % idev)
        if hasattr(fdev, 'setHolding'):
            fdev.setHolding(hold)

    def openShutter(self, open):
        idev = self.prot['imager'].getDevice()
        if hasattr(idev, 'openShutter'):
            idev.openShutter(open)

    def getFrame(self):
        # request next frame
        imager = self.prot['imager']
        with self.lock:
            # clear out any previously received frames
            self._frame = None

        frame = imager.takeImage(closeShutter=False)   # we'll handle the shutter elsewhere

        if frame is None:
            # wait for frame to arrive by signal
            # (camera and LSM imagers behave differently here; this behavior needs to be made consistent)
            self.sleep(until='frame')
            with self.lock:
                frame = self._frame
                self._frame = None
        return frame

    def recordFrame(self, frame, iter, depthIndex):
        # Handle new frame
        dh = self.prot['storageDir']
        name = 'image_%03d' % iter

        if self.prot['zStack']:
            # start or append focus stack
            arrayInfo = [
                {'name': 'Depth', 'values': [self.prot['zStackValues'][depthIndex]]},
                {'name': 'X'},
                {'name': 'Y'}
            ]
            data = MetaArray(frame.getImage()[np.newaxis, ...], info=arrayInfo)
            if depthIndex == 0:
                self.currentDepthStack = dh.writeFile(data, name, info=frame.info(), appendAxis='Depth')
            else:
                data.write(self.currentDepthStack.name(), appendAxis='Depth')

        else:
            # record single-frame image
            arrayInfo = [
                {'name': 'X'},
                {'name': 'Y'}
            ]
            data = MetaArray(frame.getImage(), info=arrayInfo)
            dh.writeFile(data, name, info=frame.info())

    def sleep(self, until):
        # Wait until some event occurs
        # check for pause / stop while waiting
        while True:
            with self.lock:
                if self._stop:
                    raise Exception("stopped")
                paused = self._paused
                frame = self._frame
            if paused:
                wait = 0.1
            else:
                if until == 'frame':
                    if frame is not None:
                        return
                    wait = 0.1
                else:
                    now = ptime.time()
                    wait = until - now
                    if wait <= 0:
                        return
            time.sleep(min(0.1, wait))

