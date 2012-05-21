# -*- coding: utf-8 -*-

import time, types, os.path, re, sys
from PyQt4 import QtGui, QtCore
#from CameraTemplate import Ui_MainWindow
from lib.LogWindow import LogButton
from StatusBar import StatusBar
import pyqtgraph as pg
import pyqtgraph.dockarea as dockarea
import lib.Manager as Manager

class PlotROI(pg.ROI):
    def __init__(self, pos, size):
        pg.ROI.__init__(self, pos, size=size)
        self.addScaleHandle([1, 1], [0, 0])


        
        
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
        
        self.persistentFrames = []
        
        
        ## Start building UI
        QtGui.QMainWindow.__init__(self)
        self.cw = dockarea.DockArea()
        self.setCentralWidget(self.cw)
        self.gv = pg.GraphicsView()
        
        ## set up ViewBox
        #self.ui.graphicsView.useOpenGL(True)  ## a bit buggy, but we need the speed.
        self.view = pg.ViewBox()
        self.view.setAspectLocked(True)
        #self.view.invertY()
        self.gv.setCentralItem(self.view)


        man = Manager.getManager()
        camNames = man.listInterfaces('camera')
        self.cameras = []
        for name in camNames:
            camera = man.getInterface('camera', name))
            self.cameras.append(camera.makeCameraModuleInterface())
            
        
        
        ## Load previous window state
        self.stateFile = os.path.join('modules', self.module.name + '_ui.cfg')
        uiState = module.manager.readConfigFile(self.stateFile)
        if 'geometry' in uiState:
            geom = QtCore.QRect(*uiState['geometry'])
            self.setGeometry(geom)
        if 'window' in uiState:
            ws = QtCore.QByteArray.fromPercentEncoding(uiState['window'])
            self.restoreState(ws)
        
        #grid = pg.GridItem()
        #self.view.addItem(grid)
        
        ## Scale bar
        self.scaleBar = pg.ScaleBar(100e-6)
        self.view.addItem(self.scaleBar)
        
        ### Set up status bar labels
        self.recLabel = QtGui.QLabel()
        self.fpsLabel = pg.ValueLabel(averageTime=2.0, formatStr='{avgValue:.1f} fps')
        self.displayFpsLabel = pg.ValueLabel(averageTime=2.0, formatStr='(displaying {avgValue:.1f} fps')
        self.displayPercentLabel = pg.ValueLabel(averageTime=4.0, formatStr='{avgValue:.1f}%)')
        self.rgnLabel = QtGui.QLabel()
        self.xyLabel = QtGui.QLabel()
        self.tLabel = QtGui.QLabel()
        self.vLabel = QtGui.QLabel()
        
        self.fpsLabel.setFixedWidth(50)
        self.displayFpsLabel.setFixedWidth(100)
        self.displayFpsLabel.setFixedWidth(100)
        self.vLabel.setFixedWidth(50)
        
        #self.logBtn = LogButton('Log')
        self.setStatusBar(StatusBar())
        font = self.xyLabel.font()
        font.setPointSize(8)
        labels = [self.recLabel, self.xyLabel, self.rgnLabel, self.tLabel, self.vLabel, self.displayPercentLabel, self.displayFpsLabel, self.fpsLabel]
        for label in labels:
            label.setFont(font)
            self.statusBar().insertPermanentWidget(0, label)
        
        ## done with UI
        self.show()
        self.centerView()
        
        ## Connect ROI dock
        self.ui.btnAddROI.clicked.connect(self.addROI)
        self.ui.btnClearROIs.clicked.connect(self.clearROIs)
        self.ui.checkEnableROIs.stateChanged.connect(self.enableROIsChanged)
        self.ui.spinROITime.valueChanged.connect(self.setROITime)
        
        ## Connect Persistent Frames dock
        self.ui.addFrameBtn.clicked.connect(self.addPersistentFrame)
        self.ui.clearFramesBtn.clicked.connect(self.clearPersistentFrames)



    def centerView(self):
        
        #center = self.cam.getPosition(justScope=True)
        #bounds = self.cam.getBoundary().adjusted(center[0], center[1], center[0], center[1])
        bounds = self.cam.getBoundary().boundingRect()
        self.view.setRange(bounds)
        #self.updateCameraDecorations()
        

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
        
        img = self.currentFrame.data()
        info = self.currentFrame.info()
        #s = info['pixelSize']
        #p = info['imagePosition']
        self.persistentFrames.append(im)
        self.addItem(im, z=z)
        im.setTransform(self.currentFrame.globalTransform().as2D())
        

    def addItem(self, item, pos=(0,0), scale=(1,1), z=0):
        """Adds an item into the scene. The image will be automatically scaled and translated when the scope moves."""
        
        self.view.addItem(item)
        
        if pos is None:
            pos = self.lastCameraPosition
        item.setPos(QtCore.QPointF(pos[0], pos[1]))
        item.scale(scale[0], scale[1])
        item.setZValue(z)
    
    def removeItem(self, item):
        self.view.removeItem(item)
    

    def  clearPersistentFrames(self):
        for i in self.persistentFrames:
            self.view.removeItem(i)
        self.persistentFrames = []


    def addROI(self):
        pen = pg.mkPen(pg.intColor(len(self.ROIs)))
        center = self.view.viewRect().center()
        size = [x*50 for x in self.view.viewPixelSize()]
        roi = PlotROI(center, size)
        roi.setZValue(40000)
        roi.setPen(pen)
        self.view.addItem(roi)
        plot = self.ui.plotWidget.plot(pen=pen)
        self.ROIs.append({'roi': roi, 'plot': plot, 'vals': [], 'times': []})
        
    def clearROIs(self):
        for r in self.ROIs:
            self.view.removeItem(r['roi'])
            self.ui.plotWidget.removeItem(r['plot'])
        self.ROIs = []
        

    def clearFrameBuffer(self):
        for r in self.ROIs:
            r['vals'] = []
            r['times'] = []


    def enableROIsChanged(self, b):
        pass
    

    def setROITime(self, val):
        pass

    def showMessage(self, msg):
        self.statusBar().showMessage(str(msg))
        
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
        
        img = self.imageItem.image
        if img is None:
            return
        pos = self.imageItem.mapFromView(pos)
        if pos.x() < 0 or pos.y() < 0:
            z = ""
        else:
            try:
                z = img[int(pos.x()), int(pos.y())]
                if hasattr(z, 'shape') and len(z.shape) > 0:
                    z = "Z:(%s, %s, %s)" % (str(z[0]), str(z[1]), str(z[2]))
                else:
                    z = "Z:%s" % str(z)
            except IndexError:
                z = ""
        
        self.vLabel.setText(z)
    

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
            minTime = frame.info()['time']
                
        prof.mark('remove old frames')
            
        ## add new frame
        draw = False
        if self.lastPlotTime is None or now - self.lastPlotTime > 0.05:
            draw = True
            self.lastPlotTime = now
            
        for r in self.ROIs:
            d = r['roi'].getArrayRegion(frame.data(), self.imageItem, axes=(0,1))
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
    


