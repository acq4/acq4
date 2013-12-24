# -*- coding: utf-8 -*-

import time, types, os.path, re, sys
from PyQt4 import QtGui, QtCore
#from CameraTemplate import Ui_Form
from acq4.LogWindow import LogButton
from acq4.util.StatusBar import StatusBar
import acq4.pyqtgraph as pg
import acq4.pyqtgraph.dockarea as dockarea
import acq4.Manager as Manager
from acq4.util.debug import Profiler
import numpy as np



        
        
class CameraWindow(QtGui.QMainWindow):
    
    #sigCameraPosChanged = QtCore.Signal()
    #sigCameraScaleChanged = QtCore.Signal()
    
    def __init__(self, module):
        self.hasQuit = False
        self.module = module ## handle to the rest of the application

        ## ROI state variables
        self.lastPlotTime = None
        self.ROIs = []
        self.plotCurves = []
        
        ## Start building UI
        QtGui.QMainWindow.__init__(self)
        self.cw = dockarea.DockArea()
        self.setCentralWidget(self.cw)
        self.gv = pg.GraphicsView()
        self.gvDock = dockarea.Dock(name="View", widget=self.gv, hideTitle=True, size=(600,600))
        self.cw.addDock(self.gvDock)
        
        ## Load previous window state
        self.stateFile = os.path.join('modules', self.module.name + '_ui.cfg')
        uiState = module.manager.readConfigFile(self.stateFile)
        if 'geometry' in uiState:
            geom = QtCore.QRect(*uiState['geometry'])
            self.setGeometry(geom)
        if 'window' in uiState:
            ws = QtCore.QByteArray.fromPercentEncoding(uiState['window'])
            self.restoreState(ws)
        self.show()
        
        ## set up ViewBox
        self.view = pg.ViewBox()
        self.view.setAspectLocked(True)
        self.gv.setCentralItem(self.view)
        
        ## build camera control panels
        man = Manager.getManager()
        camNames = man.listInterfaces('camera')
        self.cameras = []
        self.cameraDocks = []
        for name in camNames:
            camera = man.getInterface('camera', name)
            iface = camera.cameraModuleInterface(self)
            self.cameras.append(iface)
            dock = dockarea.Dock(name=name, widget=iface.controlWidget(), size=(10, 500), hideTitle=(len(camNames)==1))
            if len(self.cameraDocks) == 0:
                self.cw.addDock(dock, 'left', self.gvDock)
            else:
                self.cw.addDock(dock, 'below', self.cameraDocks[0])
            self.cameraDocks.append(dock)
            iface.sigNewFrame.connect(self.newFrame)
            
        ## ROI plot ctrls
        self.roiWidget = QtGui.QWidget()
        self.roiLayout = QtGui.QGridLayout()
        self.roiLayout.setSpacing(0)
        self.roiLayout.setContentsMargins(0,0,0,0)
        self.roiWidget.setLayout(self.roiLayout)
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
        self.roiDock = dockarea.Dock(name='ROI Plot', widget=self.roiWidget, size=(600, 10))
        self.cw.addDock(self.roiDock, 'bottom', self.gvDock)
        
        
        #grid = pg.GridItem()
        #self.view.addItem(grid)
        
        ##Scale bar
        self.scaleBar = pg.ScaleBar(100e-6, offset=(-20,-20))
        self.scaleBar.setParentItem(self.view)
        
        ### Set up status bar labels
        self.recLabel = QtGui.QLabel()
        #self.fpsLabel = pg.ValueLabel(averageTime=2.0, formatStr='{avgValue:.1f} fps')
        #self.displayFpsLabel = pg.ValueLabel(averageTime=2.0, formatStr='(displaying {avgValue:.1f} fps')
        #self.displayPercentLabel = pg.ValueLabel(averageTime=4.0, formatStr='{avgValue:.1f}%)')
        self.rgnLabel = QtGui.QLabel()
        self.xyLabel = QtGui.QLabel()
        self.tLabel = QtGui.QLabel()
        self.vLabel = QtGui.QLabel()
        
        #self.fpsLabel.setFixedWidth(50)
        #self.displayFpsLabel.setFixedWidth(100)
        #self.displayFpsLabel.setFixedWidth(100)
        self.vLabel.setFixedWidth(50)
        
        #self.logBtn = LogButton('Log')
        self.setStatusBar(StatusBar())
        font = self.xyLabel.font()
        font.setPointSize(8)
        labels = [self.recLabel, self.xyLabel, self.rgnLabel, self.tLabel, self.vLabel]
        for label in labels:
            label.setFont(font)
            self.statusBar().insertPermanentWidget(0, label)
        
        ## done with UI
        self.show()
        #self.autoRange()
        self.centerView()
        
        
        self.gv.scene().sigMouseMoved.connect(self.updateMouse)
        
        ## Connect ROI dock
        self.rectBtn.clicked.connect(self.addROI)
        #self.ui.btnClearROIs.clicked.connect(self.clearROIs)
        #self.roiPlotCheck.stateChanged.connect(self.enableROIsChanged)
        self.roiTimeSpin.valueChanged.connect(self.setROITime)
        

    def getView(self):
        return self.view

    def centerView(self):
        bounds = None
        for cam in self.cameras:
            if bounds is None:
                bounds = cam.boundingRect()
            else:
                bounds |= cam.boundingRect()
        self.setRange(bounds)
        
    def autoRange(self, item=None):
        self.view.autoRange(item=item)
    
    def setRange(self, *args, **kargs):
        self.view.setRange(*args, **kargs)

    def addItem(self, item, pos=(0,0), scale=(1,1), z=0):
        """Adds an item into the scene. The item is placed in the global coordinate system;
        it will (should) stay fixed on the subject even if the scope moves or changes objective."""
        
        self.view.addItem(item)
        
        if pos is None:
            pos = self.view.viewRect().center()
        item.setPos(pg.Point(pos))
        item.scale(scale[0], scale[1])
        item.setZValue(z)
    
    def removeItem(self, item):
        self.view.removeItem(item)
    

    def clearPersistentFrames(self):
        for i in self.persistentFrames:
            self.view.removeItem(i)
        self.persistentFrames = []


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
        

    def clearFrameBuffer(self):
        for r in self.ROIs:
            r['vals'] = []
            r['times'] = []


    def setROITime(self, val):
        pass

    def showMessage(self, msg, delay=2000):
        self.statusBar().showMessage(str(msg), delay)
        
    def closeEvent(self, ev):
        self.quit()


    def quit(self):
        geom = self.geometry()
        uiState = {'window': str(self.saveState().toPercentEncoding()), 'geometry': [geom.x(), geom.y(), geom.width(), geom.height()]}
        Manager.getManager().writeConfigFile(uiState, self.stateFile)
        
        for cam in self.cameras:
            cam.quit()
        
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
        
        #img = self.imageItem.image
        #if img is None:
            #return
        #pos = self.imageItem.mapFromView(pos)
        #if pos.x() < 0 or pos.y() < 0:
            #z = ""
        #else:
            #try:
                #z = img[int(pos.x()), int(pos.y())]
                #if hasattr(z, 'shape') and len(z.shape) > 0:
                    #z = "Z:(%s, %s, %s)" % (str(z[0]), str(z[1]), str(z[2]))
                #else:
                    #z = "Z:%s" % str(z)
            #except IndexError:
                #z = ""
        
        #self.vLabel.setText(z)
    

    def newFrame(self, iface, frame):
        #sys.stdout.write('+')
        if not self.roiPlotCheck.isChecked():
            return
        imageItem = iface.getImageItem()
        
        prof = Profiler('CameraWindow.addPlotFrame', disabled=True)
        if imageItem.width() is None:
            return
        
        ## Get rid of old frames
        minTime = None
        now = pg.time()
        #if len(self.frameBuffer) > 0:
            #while len(self.frameBuffer) > 0 and self.frameBuffer[0][1]['time'] < (now-self.ui.spinROITime.value()):
                #self.frameBuffer.pop(0)
        for r in self.ROIs:
            #print " >>", r['times'], now, frame[1]['time'], self.ui.spinROITime.value(), now-self.ui.spinROITime.value()
            while len(r['times']) > 0 and r['times'][0] < (now-self.roiTimeSpin.value()):
                r['times'].pop(0)
                r['vals'].pop(0)
            #print " <<", r['times']
            if len(r['times']) > 0 and (minTime is None or r['times'][0] < minTime):
                minTime = r['times'][0]
        if minTime is None:
            minTime = frame.info()['time']
                
        prof.mark('remove old frames')
            
        ## add new frame
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
    
    

class PlotROI(pg.ROI):
    def __init__(self, pos, size):
        pg.ROI.__init__(self, pos, size=size, removable=True)
        self.addScaleHandle([1, 1], [0, 0])

