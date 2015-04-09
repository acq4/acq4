# -*- coding: utf-8 -*-

import time, types, os.path, re, sys
from collections import OrderedDict
from PyQt4 import QtGui, QtCore
from acq4.LogWindow import LogButton
from acq4.util.StatusBar import StatusBar
import acq4.pyqtgraph as pg
import acq4.pyqtgraph.dockarea as dockarea
import acq4.Manager as Manager
from acq4.util.debug import Profiler
import numpy as np


class CameraWindow(QtGui.QMainWindow):
    
    def __init__(self, module):
        self.hasQuit = False
        self.module = module # handle to the rest of the application
        
        self.interfaces = OrderedDict()  # owner: widget
        self.docks = OrderedDict()       # owner: dock
        
        # Start building UI
        QtGui.QMainWindow.__init__(self)
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
            label = QtGui.QLabel("No imaging devices available")
            label.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
            dock = dockarea.Dock(name="nocamera", widget=label, size=(100, 500), hideTitle=True)
            self.cw.addDock(dock, 'left', self.gvDock)

        # Add a dock with ROI buttons and plot
        self.roiWidget = ROIPlotter(self)
        self.roiDock = dockarea.Dock(name='ROI Plot', widget=self.roiWidget, size=(600, 10))
        self.cw.addDock(self.roiDock, 'bottom', self.gvDock)
        
        #grid = pg.GridItem()
        #self.view.addItem(grid)
        
        #Scale bar
        self.scaleBar = pg.ScaleBar(100e-6, offset=(-20,-20))
        self.scaleBar.setParentItem(self.view)
        
        ## Set up status bar labels
        self.recLabel = QtGui.QLabel()
        self.rgnLabel = QtGui.QLabel()
        self.xyLabel = QtGui.QLabel()
        self.tLabel = QtGui.QLabel()
        self.vLabel = QtGui.QLabel()
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
            geom = QtCore.QRect(*uiState['geometry'])
            self.setGeometry(geom)
        if 'window' in uiState:
            ws = QtCore.QByteArray.fromPercentEncoding(uiState['window'])
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
        self.interfaces[name] = iface
        dock = dockarea.Dock(name=name, widget=iface.controlWidget(), size=(10, 500))
        if len(self.docks) == 0:
            dock.hideTitleBar()
            self.cw.addDock(dock, 'left', self.gvDock)
        else:
            list(self.docks.values())[0].showTitleBar()
            self.cw.addDock(dock, 'below', list(self.docks.values())[0])
        self.docks[name] = dock
        if hasattr(iface, 'sigNewFrame'):
            iface.sigNewFrame.connect(self.newFrame)
        if hasattr(iface, 'sigTransformChanged'):
            iface.sigTransformChanged.connect(self.ifaceTransformChanged)

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
            pg.QtGui.QApplication.processEvents()
            anchor2 = self.view.mapDeviceToView(anchor)
            diff = pos - anchor2
            self.lastCameraScale = scale
        else:
            diff = pos - self.lastCameraPosition
            
        self.view.translateBy(diff)
        self.lastCameraPosition = pos
        self.cameraItemGroup.setTransform(tr)
    

class CameraModuleInterface(QtCore.QObject):
    """ Base class used to plug new interfaces into the camera module.

    """
    sigNewFrame = QtCore.Signal(object, object)  # (self, frame)

    def __init__(self, mod):
        QtCore.QObject.__init__(self)
        self.mod = mod

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

    def quit(self):
        """Called when the interface is removed from the camera module or when
        the camera module is about to quit.
        """
        for item in self.graphicsItems():
            scene = item.scene()
            if scene is not None:
                scene.removeItem(item)





class PlotROI(pg.ROI):
    def __init__(self, pos, size):
        pg.ROI.__init__(self, pos, size=size, removable=True)
        self.addScaleHandle([1, 1], [0, 0])


class ROIPlotter(QtGui.QWidget):
    # ROI plot ctrls
    def __init__(self, mod):
        QtGui.QWidget.__init__(self)
        self.mod = mod
        self.view = mod.view

        # ROI state variables
        self.lastPlotTime = None
        self.ROIs = []
        self.plotCurves = []

        # Set up UI
        self.roiLayout = QtGui.QGridLayout()
        self.roiLayout.setSpacing(0)
        self.roiLayout.setContentsMargins(0,0,0,0)
        self.setLayout(self.roiLayout)
        rectPath = QtGui.QPainterPath()
        rectPath.addRect(0, 0, 1, 1)
        self.rectBtn = pg.PathButton(path=rectPath)
        ellPath = QtGui.QPainterPath()
        ellPath.addEllipse(0, 0, 1, 1)
        self.ellipseBtn = pg.PathButton(path=ellPath)
        polyPath = QtGui.QPainterPath()
        polyPath.moveTo(0,0)
        polyPath.lineTo(2,3)
        polyPath.lineTo(3,1)
        polyPath.lineTo(5,0)
        polyPath.lineTo(2, -2)
        polyPath.lineTo(0,0)
        self.polygonBtn = pg.PathButton(path=polyPath)
        polyPath = QtGui.QPainterPath()
        polyPath.moveTo(0,0)
        polyPath.lineTo(2,3)
        polyPath.lineTo(3,1)
        polyPath.lineTo(5,0)
        self.polylineBtn = pg.PathButton(path=polyPath)
        self.roiLayout.addWidget(self.rectBtn, 0, 0)
        self.roiLayout.addWidget(self.ellipseBtn, 0, 1)
        self.roiLayout.addWidget(self.polygonBtn, 1, 0)
        self.roiLayout.addWidget(self.polylineBtn, 1, 1)
        self.roiTimeSpin = pg.SpinBox(value=5.0, suffix='s', siPrefix=True, dec=True, step=0.5, bounds=(0,None))
        self.roiLayout.addWidget(self.roiTimeSpin, 2, 0, 1, 2)
        self.roiPlotCheck = QtGui.QCheckBox('Plot')
        self.roiLayout.addWidget(self.roiPlotCheck, 3, 0, 1, 2)
        
        self.roiPlot = pg.PlotWidget()
        self.roiLayout.addWidget(self.roiPlot, 0, 2, self.roiLayout.rowCount(), 1)

        self.rectBtn.clicked.connect(self.addROI)

    def addROI(self):
        pen = pg.mkPen(pg.intColor(len(self.ROIs)))
        center = self.view.viewRect().center()
        #print 'camerawindow.py: addROI:: ', self.view.viewPixelSize()
        size = [x*50 for x in self.view.viewPixelSize()]
        roi = PlotROI(center, size)
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


