# -*- coding: utf-8 -*-
#
# Imager.py: A module for Acq4
# This module is meant to act as a "camera" using laser scanning
# to obtain images and store them in the same format as used by the
# Camera Module. Images are obtained by scanning a laser (usually
# Ti:Sapphire, but it could be something else), using the existing
# mirror calibrations, over a sample. The light is detected with
# a photomultiplier, amplified/filtered, and sampled with the A/D.
# 
# The Module offers the ability to select the region to be scanned
# using the existing camera image and an ROI, adjustment of the scan
# rate, pixel size (within reason), overscan, scanning mode (bidirectional
# versus sawtooth/flyback sweeps), and the ability to take videos
# single images, and timed images. 
# the image position is coordinated with the entire system, so that 
# later reconstructions can be performed against either the Camera or
# the laser scanned image. 
#
# 2012-2013 Paul B. Manis, Ph.D. and Luke Campagnola
# UNC Chapel Hill
# Distributed under MIT/X11 license. See license.txt for more infomation.
#
import time
import pprint
from PyQt4 import QtGui, QtCore
import numpy as np
from collections import OrderedDict

from acq4.modules.Module import Module
# from acq4.pyqtgraph import ImageView
import acq4.pyqtgraph as pg
import acq4.pyqtgraph.dockarea
from acq4.Manager import getManager
import acq4.Manager
import acq4.util.InterfaceCombo as InterfaceCombo
import acq4.pyqtgraph.parametertree as PT
import acq4.util.metaarray as MA
from acq4.devices.Microscope import Microscope
from acq4.util.Mutex import Mutex
from acq4.devices.Scanner.scan_program import ScanProgram
from acq4.devices.Scanner.scan_program.rect import RectScan
from acq4.util import imaging
from .imagerTemplate import Ui_Form


# Create some useful configurations for the user.
VideoModes = OrderedDict([
    ('256x1', {
        'Average': 1,
        'Downsample': 1,
        'Image Width': 256,
        'Image Height': 256,
        'Blank Screen': False,
        'Bidirectional': True,
    }),
    ('128x2', {
        'Average': 1,
        'Downsample': 2,
        'Image Width': 128 ,
        'Image Height': 128,
        'Blank Screen': False,
        'Bidirectional': True,
    }),
    ('64x2', {
        'Downsample': 2,
        'Image Width': 64,
        'Image Height': 64,
        'Blank Screen': False,
        'Bidirectional': True,
    }),
])

FrameModes = OrderedDict([
    ('512x10', {
        'Average': 1,
        'Downsample': 10,
        'Image Width': 512,
        'Image Height': 512,
        'Blank Screen': True,
        'Bidirectional' : True,
    }),
    ('4x1024x2', {
        'Average': 4,
        'Downsample': 2,
        'Image Width': 1024,
        'Image Height': 1024,
        'Blank Screen': True,
        'Bidirectional': True,
    }),
])



class ImagerWindow(QtGui.QMainWindow):
    """
    Create the window we will use for the Imager Module.
    This is only done this way so that we can catch the window
    close event (with "X").
    """
    def __init__(self, module):
        self.hasQuit = False
        self.module = module ## handle to the rest of the module class
   
        ## Create the main window
        win = QtGui.QMainWindow.__init__(self)
        return win
    
    def closeEvent(self, ev):
        self.module.quit()


# class ImagerView(pg.ImageView):
#     """
#     Subclass ImageView so that we can display the ROI differently.
#     This one just catches the Roi data.
    
#     10/2/2013 pbm
#     """
#     def __init__(self):
#         pg.ImageView.__init__(self)
#         self.resetFrameCount()
        
#     def resetFrameCount(self):
#         self.ImagerFrameCount = 0
#         self.ImagerFrameArray = np.zeros(0)
#         self.ImagerFrameData = np.zeros(0)

#     def setImage(self, *args, **kargs):
#         pg.ImageView.setImage(self, *args, **kargs)
#         self.newFrameROI()

#     def roiChanged(self):
#         self.newFrameROI()
    
#     def newFrameROI(self):
#         """
#         override ROI display information
#         """
#         if self.image is None:
#             return           
#         image = self.getProcessedImage()
#         if image.ndim == 2:
#             axes = (0, 1)
#         elif image.ndim == 3:
#             axes = (1, 2)
#         else:
#             return
#         data, coords = self.roi.getArrayRegion(image.view(np.ndarray), self.imageItem, axes, returnMappedCoords=True)
#         if data is not None:
#             while data.ndim > 1:
#                 data = data.mean(axis=1)
#             self.ImagerFrameCount += 1

#             self.ImagerFrameArray = np.append(self.ImagerFrameArray, self.ImagerFrameCount)
#             self.ImagerFrameData = np.append(self.ImagerFrameData, data.mean())
#             self.roiCurve.setData(x = self.ImagerFrameArray, y = self.ImagerFrameData)


class Black(QtGui.QWidget):
    """ make a black rectangle to fill screen when "blanking" 

    Also draws a Cancel button that emits sigCancelClicked when clicked."""

    sigCancelClicked = QtCore.Signal()

    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.cancelRect = None
        self.cancelPressed = False

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        brush = pg.mkBrush(0.0)
        p.fillRect(self.rect(), brush)

        center = self.rect().center()
        r = QtCore.QPoint(70, 30)
        self.cancelRect = QtCore.QRect(center-r, center+r)
        p.setPen(pg.mkPen(150, 0, 0))
        f = p.font()
        f.setPointSize(18)
        p.setFont(f)
        if self.cancelPressed:
            p.fillRect(self.cancelRect, pg.mkBrush(80, 0, 0))
        p.drawRect(self.cancelRect)
        p.drawText(self.cancelRect, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter, "Cancel")
        p.end()

    def mousePressEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton and self.cancelRect.contains(ev.pos()):
            ev.accept()
            self.cancelPressed = True
            self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            if self.cancelRect.contains(ev.pos()) and self.cancelPressed:
                self.sigCancelClicked.emit()
            self.cancelPressed = False
            self.update()

     

class ScreenBlanker(QtCore.QObject):
    """
    Perform the blanking on ALL screens that we can detect.
    This is so that extraneous light does not leak into the 
    detector during acquisition.
    """
    sigCancelClicked = QtCore.Signal()

    def __init__(self, blank=True):
        QtCore.QObject.__init__(self)
        self.blank = blank
        self.cancelled = False

    def __enter__(self):
        self.cancelled = False
        self.widgets = []
        if not self.blank:
            return self

        d = QtGui.QApplication.desktop()
        for i in range(d.screenCount()): # look for all screens
            w = Black()
            w.sigCancelClicked.connect(self.cancelClicked)
            self.widgets.append(w)
            sg = d.screenGeometry(i) # get the screen size
            w.move(sg.x(), sg.y()) # put the widget there
            w.showFullScreen() # duh
        QtGui.QApplication.processEvents() # make it so
        return self
        
    def __exit__(self, *args):
        for w in self.widgets:
            w.hide() # just take them away
            w.sigCancelClicked.disconnect(self.cancelClicked)
        self.widgets = []

    def cancelClicked(self):
        """Called when a cancel button is clicked.
        """
        self.cancelled = True
        self.sigCancelClicked.emit()

        
class RegionCtrl(pg.ROI):
    """
    Create an ROI "Region Control" with handles, with specified size
    and color. 
    Note: Setting the ROI position here is advised, but it seems
    that when adding the ROI to the camera window with the Qt call
    window().addItem, the position is lost, and will have to be
    reset in the ROI.
    """
    def __init__(self, pos, size, roiColor = 'r'):
        pg.ROI.__init__(self, pos, size=size, pen=roiColor)
        self.addScaleHandle([0,0], [1,1])
        self.addScaleHandle([1,1], [0,0])
        self.addScaleHandle([0,1], [1,0])
        self.addScaleHandle([1,0], [0,1])
        self.setZValue(1200)

class TileControl(pg.ROI):
    """
    Create an ROI for the Tile Regions. Note that the color is RED, 
    """    
    def __init__(self, pos, size, roiColor = 'r'):
        pg.ROI.__init__(self, pos, size=size, pen=roiColor)
        self.addScaleHandle([0,0], [1,1])
        self.addScaleHandle([1,1], [0,0])
        self.setZValue(1400)
    


class Imager(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config) 
        self.win = ImagerWindow(self) # make the main window - mostly to catch window close event...
        self.win.show()
        self.win.setWindowTitle('Multiphoton Imager V 1.01')
        self.win.resize(500, 900) # make the window big enough to use on a large monitor...

        self.w1 = QtGui.QSplitter() # divide l, r
        self.w1.setOrientation(QtCore.Qt.Horizontal)
        self.win.setCentralWidget(self.w1) # w1 is the "main window" splitter

        self.dockarea = pg.dockarea.DockArea()
        self.w1.addWidget(self.dockarea)

        # acquisition control
        # self.w2s = QtGui.QSplitter()
        # self.w2s.setOrientation(QtCore.Qt.Vertical)
        self.w2s = QtGui.QWidget()
        self.w2sl = QtGui.QVBoxLayout()
        self.w2s.setLayout(self.w2sl)
        self.w2sl.setContentsMargins(0, 0, 0, 0)
        self.w2sl.setSpacing(0)
        self.ctrlWidget = QtGui.QWidget()
        # self.w2s.addWidget(self.ctrlWidget)
        self.ui = Ui_Form()
        self.ui.setupUi(self.ctrlWidget)  # put the ui on the top 
        self.w2sl.addWidget(self.ctrlWidget)

        # create the parameter tree for controlling device behavior
        self.tree = PT.ParameterTree()
        # self.w2s.addWidget(self.tree) # put the parameters on the bottom
        # self.w2s.setSizes([1,1,900]) # Ui top widget has multiple splitters itself - force small space..
        self.w2sl.addWidget(self.tree)

        # takes care of displaying image data, 
        # contrast & background subtraction user interfaces
        self.imagingCtrl = imaging.ImagingCtrl()
        self.frameDisplay = self.imagingCtrl.frameDisplay
        self.imageItem = self.frameDisplay.imageItem()

        # create docks for imaging, contrast, and background subtraction
        recDock = pg.dockarea.Dock(name="Acquisition Control", widget=self.imagingCtrl, size=(250, 10), autoOrientation=False)
        scanDock = pg.dockarea.Dock(name="Device Control", widget=self.w2s, size=(250, 800), autoOrientation=False)
        dispDock = pg.dockarea.Dock(name="Display Control", widget=self.frameDisplay.contrastWidget(), size=(250, 800), autoOrientation=False)
        bgDock = pg.dockarea.Dock(name="Background Subtraction", widget=self.frameDisplay.backgroundWidget(), size=(250, 10), autoOrientation=False)
        self.dockarea.addDock(recDock)
        self.dockarea.addDock(dispDock, 'right', recDock)
        self.dockarea.addDock(scanDock, 'bottom', recDock)
        self.dockarea.addDock(bgDock, 'bottom', dispDock)


        # TODO: resurrect this for situations when the camera module can't be used
        # self.view = ImagerView()
        # self.w1.addWidget(self.view)   # add the view to the right of w1     

        self.videoRunning = False
        self.abort = False
        self.storedROI = None
        # self.currentStack = None
        # self.currentStackLength = 0
        self.currentRoi = None
        self.ignoreRoiChange = False
        self.tileRoi = None
        self.tileRoiVisible = False
        self.tilexPos = 0.
        self.tileyPos = 0.
        self.tileWidth = 2e-4
        self.tileHeight = 2e-4
        self.stopFlag = False
        self.lastFrame = None

        self.dwellTime = 0. # "pixel dwell time" computed from scan time and points.
        self.fieldSize = 63.0*120e-6 # field size for 63x, will be scaled for others

        self.scanProtocol = None  # cached scan protocol computed by generateScanProtocol
        
        self.objectiveROImap = {} # this is a dict that we will populate with the name
        # of the objective and the associated ROI object .
        # That way, each objective has a scan region appopriate for it's magnification.

        # we assume that you are not going to change the current camera or scope while running
        # ... not just yet anyway.
        # if this is to be allowed on a system, the change must be signaled to this class,
        # and we need to pick up the device in a routine that handles the change.
        try:
            self.cameraModule = self.manager.getModule(config['cameraModule'])
        except:
            self.manager.loadDefinedModule(config['cameraModule'])
            pg.QtGui.QApplication.processEvents()
            self.cameraModule = self.manager.getModule(config['cameraModule'])
        self.laserDev = self.manager.getDevice(config['laser'])
        self.scannerDev = self.manager.getDevice(config['scanner'])
        
        self.cameraModule.window().addItem(self.imageItem)

        # find first scope device that is parent of scanner
        dev = self.scannerDev
        while dev is not None and not isinstance(dev, Microscope):
            dev = dev.parentDevice()
        self.scopeDev = dev
        if dev is not None:
            self.scopeDev.sigObjectiveChanged.connect(self.objectiveUpdate)
            self.scopeDev.sigGlobalTransformChanged.connect(self.transformChanged)
        
        # config may specify a single detector device (dev, channel) or a list of devices 
        # to select from [(dev1, channel1), ...]
        self.detectors = config.get('detectors', [config.get('detector')])
        
        self.attenuatorDev = self.manager.getDevice(config['attenuator'][0])
        self.attenuatorChannel = config['attenuator'][1]
        
        self.laserMonitor = QtCore.QTimer()
        self.laserMonitor.timeout.connect(self.updateLaserInfo)
        self.laserMonitor.start(3000)
        
        # self.ui.hide_check.stateChanged.connect(self.hideOverlayImage)
        # self.ui.alphaSlider.valueChanged.connect(self.imageAlphaAdjust)        

        # self.ui.snap_Button.clicked.connect(self.PMT_SnapClicked)
        # self.ui.snap_Standard_Button.clicked.connect(self.PMT_Snap_std)
        # self.ui.snap_High_Button.clicked.connect(self.PMT_Snap_high)
        
        # self.ui.video_button.clicked.connect(self.toggleVideo)
        # self.ui.video_std_button.clicked.connect(self.toggleVideo_std)
        # self.ui.video_fast_button.clicked.connect(self.toggleVideo_fast)
        # self.ui.record_button.toggled.connect(self.recordToggled)

        self.frameDisplay.imageUpdated.connect(self.imageUpdated)
        self.imagingCtrl.sigAcquireFrameClicked.connect(self.acquireFrameClicked)
        self.imagingCtrl.sigStartVideoClicked.connect(self.startVideoClicked)
        self.imagingCtrl.sigStopVideoClicked.connect(self.stopVideoClicked)

        # Add custom imaging modes
        for mode in FrameModes:
            self.imagingCtrl.addFrameButton(mode)
        for mode in VideoModes:
            self.imagingCtrl.addVideoButton(mode)

        # Connect other UI controls
        self.ui.run_button.clicked.connect(self.PMT_Run)
        self.ui.stop_button.clicked.connect(self.PMT_Stop)
        self.ui.set_TilesButton.clicked.connect(self.setTilesROI)
        
        #self.ui.cameraSnapBtn.clicked.connect(self.cameraSnap)
        self.ui.restoreROI.clicked.connect(self.restoreROI)
        self.ui.saveROI.clicked.connect(self.saveROI)
        self.ui.Align_to_Camera.clicked.connect(self.reAlign)

        self.scanProgram = ScanProgram()
        self.scanProgram.addComponent('rect')

        self.param = PT.Parameter(name = 'param', children=[
            # dict(name="Preset", type='list', value='video-fast', 
            #      values=['StandardDef', 'HighDef', 'video-std', 'video-fast', 
            #              'video-ultra']),
            dict(name='Scan Control', type='group', children=[
                dict(name='Pockels', type='float', value=0.03, suffix='V', step=0.005, limits=[0, 1.5], siPrefix=True),
                dict(name='Sample Rate', type='int', value=1.0e6, suffix='Hz', dec=True, minStep=100., step=0.5, limits=[10e3, 50e6], siPrefix=True),
                dict(name='Downsample', type='int', value=1, limits=[1,None]),
                dict(name='Average', type='int', value=1, limits=[1,100]),
                dict(name='Blank Screen', type='bool', value=True),
                dict(name='Image Width', type='int', value=500, readonly=False, limits=[1, None]),
                dict(name='Image Height', type='int', value=500, readonly=False, limits=[1, None]),
                dict(name='Bidirectional', type='bool', value=True),
                dict(name='Overscan', type='float', value=50e-6, suffix='s', siPrefix=True, limits=[0, None], step=10e-6),
                dict(name='Photodetector', type='list', values=self.detectors),
                dict(name='Follow Stage', type='bool', value=True),
            ]),
            dict(name='Scan Properties', type='group', children=[
                dict(name='Frame Time', type='float', value=50e-3, suffix='s', siPrefix=True, readonly=True, dec=True, step=0.5, minStep=100e-6),
                dict(name='Pixel Size', type='float', value=1e-6, suffix='m', siPrefix=True, readonly=True),
                dict(name='Scan Speed', type='float', value=0.00, suffix='m/s', siPrefix=True, readonly=True),
                dict(name='Exposure per Frame', type='float', value=0.00, suffix='s/um^2', siPrefix=True, readonly=True),
                dict(name='Total Exposure', type='float', value=0.00, suffix='s/um^2', siPrefix=True, readonly=True),
                dict(name='Wavelength', type='float', value=700, suffix='nm', readonly=True),
                dict(name='Power', type='float', value=0.00, suffix='W', readonly=True),
                dict(name='Objective', type='str', value='Unknown', readonly=True),
            ]),
            dict(name='Image Control', type='group', children=[
                dict(name='Decomb', type='float', value=20e-6, suffix='s', siPrefix=True, bounds=[0, 1e-3], step=1e-6, decimals=5, children=[
                    dict(name='Auto', type='action'),
                    dict(name='Subpixel', type='bool', value=False),
                    ]),
                dict(name='Camera Module', type='interface', interfaceTypes=['cameraModule']),
            ]),
            # dict(name='Scope Device', type='interface', interfaceTypes=['microscope']),
            # dict(name='Scanner Device', type='interface', interfaceTypes=['scanner']),
            # dict(name='Laser Device', type='interface', interfaceTypes=['laser']),
            dict(name="Tiles", type="bool", value=False, children=[
                dict(name='Stage', type='interface', interfaceTypes='stage'),
                dict(name="X0", type="float", value=-100., suffix='um', dec=True, minStep=1, step=1, limits=[-2.5e3,2.5e3], siPrefix=True),
                dict(name="X1", type="float", value=100., suffix='um', dec=True, minStep=1, step=1, limits=[-2.5e3,2.5e3], siPrefix=True),
                dict(name="Y0", type="float", value=-100., suffix='um', dec=True, minStep=1, step=1, limits=[-2.5e3,2.5e3], siPrefix=True),
                dict(name="Y1", type="float", value=100., suffix='um', dec=True, minStep=1, step=1, limits=[-2.5e3,2.5e3], siPrefix=True),
                dict(name="StepSize", type="float", value=100, suffix='um', dec=True, minStep=1e-5, step=0.5, limits=[1e-5,1e3], siPrefix=True),
                
            ]),
            dict(name="Z-Stack", type="bool", value=False, children=[
                dict(name='Stage', type='interface', interfaceTypes='stage'),
                dict(name="Step Size", type="float", value=5e-6, suffix='m', dec=True, minStep=1e-7, step=0.5, limits=[1e-9,1], siPrefix=True),
                dict(name="Steps", type='int', value=10, step=1, limits=[1,None]),
                dict(name="Depth", type="float", value=0, readonly=True, suffix='m', siPrefix=True)
            ]),
            dict(name="Timed", type="bool", value=False, children=[
                dict(name="Interval", type="float", value=5.0, suffix='s', dec=True, minStep=0.1, step=0.5, limits=[0.1,30], siPrefix=True),
                dict(name="N Intervals", type='int', value=10, step=1, limits=[1,None]),
                dict(name="Duration", type="float", value=0, readonly=True, suffix='s', siPrefix = True),
                dict(name="Current Frame", type='int', value = 0, readonly=True),
            ]),
            dict(name='Show PMT V', type='bool', value=False),
            dict(name='Show Mirror V', type='bool', value=False),
        ])
        self.tree.setParameters(self.param, showTop=False)

        # insert an ROI into the camera image that corresponds to our scan area                
        self.objectiveUpdate() # force update of objective information and create appropriate ROI
        # check the devices...        
        self.updateParams() # also force update now to make sure all parameters are synchronized
        self.param.child('Scan Control').sigTreeStateChanged.connect(self.updateParams)
        self.param.child('Image Control').sigTreeStateChanged.connect(self.updateDecomb)
        self.param.child('Image Control', 'Decomb', 'Auto').sigActivated.connect(self.autoDecomb)

        self.manager.sigAbortAll.connect(self.abortTask)

    def quit(self):
        self.abortTask()
        if self.imageItem is not None and self.imageItem.scene() is not None:
            self.imageItem.scene().removeItem(self.imageItem)
        self.imageItem = None
        for obj,item in self.objectiveROImap.items(): # remove the ROI's for all objectives.
            try:
                if item.scene() is not None:
                    item.scene().removeItem(item)
            except:
                pass
        if self.tileRoi is not None:
            if self.tileRoi.scene() is not None:
                self.tileRoi.scene().removeItem(self.tileRoi)
            self.tileRoi = None
        self.imagingCtrl.quit()
        Module.quit(self)

    def abortTask(self):
        """Immediately stop all acquisition and close any shutters in use.
        """
        self.abort = True
        if self.laserDev is not None and self.laserDev.hasShutter:
            self.laserDev.closeShutter()


    def objectiveUpdate(self, reset=False):
        """ Update the objective information and the associated ROI
        Used to report that the objective has changed in the parameter tree,
        and then reposition the ROI that drives the image region.
        """
        # if self.img is not None:# clear the image ovelay if it exists
        #     self.cameraModule.window().removeItem(self.img)
        #     self.img = None
        self.param['Scan Properties', 'Objective'] = self.scopeDev.currentObjective.name()
        if reset:
            self.clearROIMap()
        if self.param['Scan Properties', 'Objective'] not in self.objectiveROImap: # add the objective and an ROI
            # print "create roi:",  self.param['Objective']
            self.objectiveROImap[self.param['Scan Properties', 'Objective']] = self.createROI()
        for obj, roi in self.objectiveROImap.items():
            if obj == self.param['Scan Properties', 'Objective']:
                self.currentRoi = roi
                roi.show()
                self.roiChanged() # do this now as well so that the parameter tree is correct. 
            else:
                roi.hide()
                # self.hideROI(self.objectiveROImap[obj])

    def clearROIMap(self):
        for k in self.objectiveROImap.keys():
            roi = self.objectiveROImap[k]
            if roi.scene() is not None:
                roi.scene().removeItem(roi)
        self.objectiveROImap = {}
    
    def transformChanged(self):
        """
        Report that the tranform has changed, which might include the objective, or
        perhaps the stage position, etc. This needs to be obtained to re-align
        the scanner ROI
        """
        globalTr = self.scannerDev.globalTransform()
        pt1 = globalTr.map(self.currentRoi.scannerCoords[0])
        pt2 = globalTr.map(self.currentRoi.scannerCoords[1])
        diff = pt2 - pt1
        self.currentRoi.setPos(pt1)
        self.currentRoi.setSize(diff)
        
    def getObjectiveColor(self, objective):
        """
        for the current objective, parse a color or use a default. This is a kludge. 
        """
        color = QtGui.QColor("red")
        id = objective.key()[1]
        if id == u'63x0.9':
            color = QtGui.QColor("darkBlue")
        elif id == u'40x0.8':
            color = QtGui.QColor("blue")
        elif id == u'40x0.75':
            color = QtGui.QColor("blue")
        elif id == u'5x0.25':
            color = QtGui.QColor("red")
        elif id == u'4x0.1':
            color = QtGui.QColor("darkRed")
        else:
            color = QtGui.QColor("lightGray")
        return(color)
            
    def createROI(self, roiColor='r'):
        # the initial ROI will be nearly as big as the field, and centered.
        cpos = self.scannerDev.mapToGlobal((0,0)) # get center position in scanner coordinates
        csize = self.scannerDev.mapToGlobal((self.fieldSize, self.fieldSize))
        objScale = self.scannerDev.parentDevice().getObjective().scale().x()
        height = width = self.fieldSize*objScale
        
        csize = pg.Point(width, height)
        cpos = cpos - csize/2.
        
        roiColor = self.getObjectiveColor(self.scopeDev.currentObjective) # pick up an objective color...
        roi = RegionCtrl(cpos, csize, roiColor) # Note that the position actually gets over ridden by the camera additem below..
        roi.setZValue(10000)
        self.cameraModule.window().addItem(roi)
        roi.setPos(cpos)
        roi.sigRegionChangeFinished.connect(self.roiChanged)
        return roi
    
    # def hideROI(self, roi):
    #     """ just make the current roi invisible... 
    #     although we probalby also want to hide the associated image if it is present...
    #     """
    #     roi.hide()
    #     self.hideOverlayImage()
    
    def restoreROI(self):
        
        if self.storedROI is not None:
            (width, height, x, y) = self.storedROI
            self.currentRoi.setSize([width, height])
            self.currentRoi.setPos([x, y])
            self.roiChanged()
        else:
            cpos = self.cameraModule.ui.view.viewRect().center() # center position, stage coordinates
            csize = pg.Point([x*400 for x in self.cameraModule.ui.view.viewPixelSize()])
            width  = csize[0]*2 # width is x in M
            height = csize[1]*2
            csize = pg.Point(width, height)
            cpos = cpos - csize/2.
            self.currentRoi.setSize([width, height])
            self.currentRoi.setPos(cpos)
            
    def saveROI(self):
        state = self.currentRoi.getState()
        (width, height) = state['size']
        x, y = state['pos']
        self.storedROI = [width, height, x, y]
        
    def roiChanged(self):
        """ read the ROI rectangle width and height and repost
        in the parameter tree """
        if self.ignoreRoiChange:
            return

        roi = self.currentRoi
        state = roi.getState()
        w, h = state['size']
        rparam = self.scanProgram.components[0].ctrlParameter()
        rparam.system.p0 = pg.Point(roi.mapToView(pg.Point(0,h)))  # top-left
        rparam.system.p1 = pg.Point(roi.mapToView(pg.Point(w,h)))  # rop-right
        param = self.param.child('Scan Control')
        rows = param['Image Width'] * h / w
        with param.treeChangeBlocker():
            param['Image Height'] = rows
        # rparam.system.p2 = pg.Point(roi.mapToView(pg.Point(0,0)))  # bottom-left
        # rparam['imageRows', 'fixed'] = False  # need to let this float to accomodate new roi shape

        # with self.param.treeChangeBlocker():
            # self.param['Image Height'] = rparam.system.imageRows

        #print 'roiChanged state: ', state
        # self.width, self.height = state['size']
        # self.ui.width.setText('%8.1f' % (self.width*1e6)) # express in microns
        # self.ui.height.setText('%8.1f' % (self.height*1e6))
        # self.xPos, self.yPos = state['pos']
        # self.ui.xpos.setText('%8.3f' % (self.xPos*1e3)) # in mm # param['Xpos'] = x
        # self.ui.ypos.setText('%8.3f' % (self.yPos*1e3)) # in mm # param['Ypos'] = y
        # self.pixelSize = self.width/self.param['Image Width']
        # self.ui.pixelSize.setText('%8.3f' % (self.pixelSize*1e6)) # in microns
        
        # record position of ROI in Scanner's local coordinate system
        # we can use this later to allow the ROI to track stage movement
        tr = self.scannerDev.inverseGlobalTransform() # maps from global to device local
        pt1 = pg.Point(*state['pos'])
        pt2 = pt1 + pg.Point(*state['size'])
        self.currentRoi.scannerCoords = [
            tr.map(pt1),
            tr.map(pt2),
            ]

    def reAlign(self):
        self.objectiveUpdate(reset=True) # try this... 
        self.roiChanged()

    def setTilesROI(self, roiColor = 'r'):
       # the initial ROI will be larger than the current field and centered.
        if self.tileRoi is not None and self.tileRoiVisible:
            self.hideROI(self.tileRoi)
            self.tileRoiVisible = False
            if self.tileRoi is not None:
                return
           
            
        state = self.currentRoi.getState()
        width, height = state['size']
        x, y = state['pos']
        #self.camdev.getBoundary().boundingRect()
        #width = brect.width()
        #height = brect.height()
        #x = brect.x()
        #y = brect.y()
        
        csize= [width*3.0,  height*3.0]
        cpos = [x, y]
        self.tileRoi = RegionCtrl(cpos, csize, [255., 0., 0.]) # Note that the position actually gets overridden by the camera additem below..
        self.tileRoi.setZValue(11000)
        self.cameraModule.window().addItem(self.tileRoi)
        self.tileRoi.setPos(cpos)
        self.tileRoi.sigRegionChangeFinished.connect(self.tileROIChanged)
        self.tileRoiVisible = True
        return self.tileRoi
        
    def tileROIChanged(self):
        """ read the TILE ROI rectangle width and height and repost
        in the parameter tree """
        state = self.tileRoi.getState()
        self.tileWidth, self.tileHeight = state['size']
        self.tilexPos, self.tileyPos = state['pos']
        x0, y0 =  self.tileRoi.pos()
        x0 = x0 - self.xPos # align against currrent 2p Image lower left corner
        y0 = y0 - self.yPos
        self.param['Tiles', 'X0'] = x0 * 1e6
        self.param['Tiles', 'Y0'] = y0 * 1e6
        self.param['Tiles', 'X1'] = self.tileWidth * 1e6
        self.param['Tiles', 'Y1'] = self.tileHeight * 1e6
        # record position of ROI in Scanner's local coordinate system
        # we can use this later to allow the ROI to track stage movement
        tr = self.scannerDev.inverseGlobalTransform() # maps from global to device local
        pt1 = pg.Point(self.tilexPos, self.tileyPos)
        pt2 = pg.Point(self.tilexPos+self.tileWidth, self.tileyPos+self.tileHeight)
        self.tileRoi.scannerCoords = [
            tr.map(pt1),
            tr.map(pt2),
            ]

        
    def updateParams(self, root=None, changes=()):
        """Parameters have changed; update any dependent parameters and the scan program.
        """
        #check the devices first        
        # use the presets if they are engaged
        # preset = self.param['Preset']
        # self.loadPreset(preset)

        scanControl = self.param.child('Scan Control')

        self.scanProtocol = None  # invalidate cache

        sampleRate = scanControl['Sample Rate']
        downsample = scanControl['Downsample']
        # we'll let the rect tell us later how many samples are needed
        self.scanProgram.setSampling(rate=sampleRate, samples=0, downsample=downsample)
        self.scanProgram.setDevices(scanner=self.scannerDev, laser=self.laserDev)

        rect = self.scanProgram.components[0]
        rparams = rect.ctrlParameter()

        for param, change, args in changes:
            if change == 'value' and param is scanControl.child('Image Height'):
                # user explicitly requested image height; change ROI to match.
                try:
                    self.ignoreRoiChange = True
                    size = self.currentRoi.size()
                    self.currentRoi.setSize([size[0], size[0] * scanControl['Image Height'] / scanControl['Image Width']])
                finally:
                    self.ignoreRoiChange = False

        rparams['imageRows'] = scanControl['Image Height']
        rparams['imageRows', 'fixed'] = True
        rparams['imageCols'] = scanControl['Image Width']
        rparams['imageCols', 'fixed'] = True
        rparams['minOverscan'] = scanControl['Overscan']
        rparams['bidirectional'] = True
        rparams['pixelAspectRatio'] = 1.0
        rparams['pixelAspectRatio', 'fixed'] = True
        rparams['numFrames'] = scanControl['Average']

        rparams.system.solve()
        nSamples = rparams.system.scanStride[0] * rparams.system.numFrames
        nSamples += int(sampleRate * 200e-6)  # generate some padding for decomb
        self.scanProgram.setSampling(rate=sampleRate, samples=nSamples, downsample=downsample)

        # Update dependent parameters
        scanProp = self.param.child('Scan Properties')
        scanProp['Pixel Size'] = rparams.system.pixelWidth
        scanProp['Frame Time'] = rparams.system.frameDuration

        scanProp['Scan Speed'] = rparams.system.scanSpeed
        scanProp['Exposure per Frame'] = rparams.system.frameExposure
        scanProp['Total Exposure'] = rparams.system.totalExposure

        if rparams.system.checkOverconstraint() is not False:
            raise RuntimeError("Scan calculator is overconstrained (this is a bug).")

    def updateDecomb(self):
        if self.lastFrame is not None:
            self.lastFrame.setDecomb(self.param['Image Control', 'Decomb'], self.param['Image Control', 'Decomb', 'Subpixel'])
            self.frameDisplay.updateFrame()

    def autoDecomb(self):
        if self.lastFrame is not None:
            self.lastFrame.autoDecomb()
            self.param.child('Image Control', 'Decomb').setValue(self.lastFrame._decomb[0])

    # def loadPreset(self, preset):
    #     """
    #     load the selected preset into the parameters, and calculate some
    #     useful parameters for display for the user.
    #     """
    #     if preset != '':
    #         self.param['Preset'] = ''
    #         global Presets
    #         for k,v in Presets[preset].items():
    #             self.param[k] = v
                
       # with every change, recalculate some values about the display
        # state = self.currentRoi.getState()
        # self.width, self.height = state['size']
        # self.pixelSize = self.width/self.param['Image Width']
        # self.ui.pixelSize.setText('%8.3f' % (self.pixelSize*1e6))
        # self.param['Frame Time'] = self.param['Image Width']*self.param['Image Height']*self.param['Downsample']/self.param['Sample Rate']
        # self.param['Z-Stack', 'Depth'] = self.param['Z-Stack', 'Step Size'] * (self.param['Z-Stack', 'Steps']-1)
        # self.param['Timed', 'Duration'] = self.param['Timed', 'Interval'] * (self.param['Timed', 'N Intervals']-1)
        # self.dwellTime = self.param['Downsample']/self.param['Sample Rate']
        # self.ui.dwellTime.setText('%6.1f' % (self.dwellTime*1e6))
                
    # def imageAlphaAdjust(self):
    #     if self.img is None:
    #         return
    #     alpha = self.ui.alphaSlider.value()
    #     self.img.setImage(opacity=float(alpha/100.))
        
    # def hideOverlayImage(self):
    #     if self.img is None:
    #         return
    #     if self.ui.hide_check.isChecked() is True:
    #         self.img.hide()
    #     else:
    #         self.img.show()
        
    def PMT_Run(self):
        """
        This routine handles special cases where we want multiple frames to be
        automatically collected. The 3 modes implemented are:
        Z-stack (currently not used as the stage isn't good enough...)
        Tiles - collect a tiled x-y sequence of images as single images.
        Timed - collect a series of images as a 2p-stack. 
        The parameters for each are set in the paramtree, and the
        data collection is initiated with the "Run" button and
        can be terminated early with the "stop" button.
        """
        
        info = {}
        frameInfo = None  # will be filled in by takeImage()
        self.stopFlag = False
        if (self.param['Z-Stack'] and self.param['Timed']) or (self.param['Z-Stack'] and self.param['Tiles']) or self.param['Timed'] and self.param['Tiles']:
            return # only one mode at a time... 
        self.view.resetFrameCount() # always reset the ROI display in the imager window (different than in camera window) if it is being used
        
        if self.param['Z-Stack']: # moving in z for a focus stack
            imageFilename = '2pZstack'
            info['2pImageType'] = 'Z-Stack'
            stage = self.manager.getDevice(self.param['Z-Stack', 'Stage'])
            images = []
            nSteps = self.param['Z-Stack', 'Steps']
            for i in range(nSteps):
                img, frameInfo = self.takeImage()
                img = img[np.newaxis, ...]
                if img is None:
                    break
                images.append(img)
                self.view.setImage(img)
                
                if i < nSteps-1:
                    ## speed 20 is quite slow; timeouts may occur if we go much slower than that..
                    stage.moveBy([0.0, 0.0, self.param['Z-Stack', 'Step Size']], speed=20, block=True)  
            imgData = np.concatenate(images, axis=0)
            info.update(frameInfo)
            if self.param['Store']:
                dh = self.manager.getCurrentDir().writeFile(imgData, imageFilename + '.ma', info=info, autoIncrement=True)
        
        elif self.param['Tiles']: # moving in x and y to get a tiled image set
            info['2pImageType'] = 'Tiles'
            dirhandle = self.manager.getCurrentDir()
            if self.param['Store']:
                dirhandle = dirhandle.mkdir('2PTiles', autoIncrement=True, info=info)
            imageFilename = '2pImage'
            
            stage = self.manager.getDevice(self.param['Tiles', 'Stage'])
            #print dir(stage.mp285)
            #print stage.mp285.stat()
            #return
            self.param['Timed', 'Current Frame'] = 0 # get frame times ...
            images = []
            originalPos = stage.pos
            state = self.currentRoi.getState()
            self.width, self.height = state['size']
            originalSpeed = 200
            mp285speed = 1000

            x0 = self.param['Tiles', 'X0'] *1e-6 # convert back to meters
            x1 = x0 + self.param['Tiles', 'X1'] *1e-6
            y0 = self.param['Tiles', 'Y0'] *1e-6
            y1 = y0 + self.param['Tiles', 'Y1'] *1e-6
            tileXY = self.param['Tiles', 'StepSize']*1e-6
            nXTiles = np.ceil((x1-x0)/tileXY)
            nYTiles = np.ceil((y1-y0)/tileXY)
           
            # positions are relative......
            xpos = np.arange(x0, x0+nXTiles*tileXY, tileXY) +originalPos[0]
            ypos = np.arange(y0, y0+nYTiles*tileXY, tileXY) +originalPos[1]
            stage.moveTo([xpos[0], ypos[0]],
                         speed=mp285speed, fine = True, block=True) # move and wait until complete.  

            ypath = 0
            xdir = 1 # positive movement direction (serpentine tracking)
            xpos1 = xpos
            for yp in ypos:
                if self.stopFlag:
                    break
                for xp in xpos1:
                    if self.stopFlag:
                        break
                    stage.moveTo([xp, yp], speed=mp285speed, fine = True, block=True, timeout = 10.)
                    (images, frameInfo) = self.PMT_Snap(dirhandle = dirhandle) # now take image
                    #  stage.moveBy([tileXY*xdir, 0.], speed=mp285speed, fine = True, block=True, timeout = 10.)
                xdir *= -1 # reverse direction
                if xdir < 0:
                    xpos1 = xpos[::-1] # reverse order of array, serpentine movement.
                else:
                    xpos1 = xpos
            stage.moveTo([xpos[0], ypos[0]],
                         speed=originalSpeed, fine = True, block=True, timeout = 30.) # move and wait until complete.  

        elif self.param['Timed']: # 
            imageFilename = '2pTimed'
            info['2pImageType'] = 'Timed'
            self.param['Timed', 'Current Frame'] = 0
            images = []
            nSteps = self.param['Timed', 'N Intervals']
            for i in range(nSteps):
                if self.stopFlag:
                    break
                self.param['Timed', 'Current Frame'] = i
                (img, frameInfo) = self.takeImage()
                img = img[np.newaxis, ...]
                if img is None:
                   return
                images.append(img)
                self.view.setImage(img)
                if self.stopFlag:
                    break
                
                if i < nSteps-1:
                    time.sleep(self.param['Timed', 'Interval'])
            imgData = np.concatenate(images, axis=0)
            info.update(frameInfo)
            if self.param['Store']:
                dh = self.manager.getCurrentDir().writeFile(imgData, imageFilename + '.ma', info=info, autoIncrement=True)

        else:
            imageFilename = '2pImage'
            info['2pImageType'] = 'Snap'
            (imgData, frameInfo) = self.takeImage()
            if imgData is None:
                return
            self.view.setImage(imgData)
            info.update(frameInfo)
            if self.param['Store']:
                dh = self.manager.getCurrentDir().writeFile(imgData, imageFilename + '.ma', info=info, autoIncrement=True)

    def PMT_Stop(self):
        self.stopFlag = True
            
    # def PMT_Snap_std(self):
    #     self.loadPreset('StandardDef')
    #     self.PMT_Snap()

    # def PMT_Snap_high(self):
    #     self.loadPreset('HighDef')
    #     self.PMT_Snap()
    
    def loadModeSettings(self, params):
        param = self.param.child('Scan Control')
        with param.treeChangeBlocker():  # accumulate changes, emit once at the end.
            for name, val in params.items():
                param[name] = val

    def acquireFrameClicked(self, mode):
        """User requested acquisition of a single frame.
        """
        if mode is not None:
            self.loadModeSettings(FrameModes[mode])
        self.PMT_Snap()
        
    def startVideoClicked(self, mode):
        if mode is not None:
            self.loadModeSettings(VideoModes[mode])
        if not self.videoRunning:
            self.startVideo()

    def stopVideoClicked(self):
        self.videoRunning = False
            
    def PMT_Snap(self, dirhandle=None):
        """
        Take one image as a snap, regardless of whether a Z stack or a Timed acquisition is selected
        """            
        # need to resurrect this.
        assert dirhandle is None

        frame = self.takeImage()
        if frame is False:  # aborted
            return
        frame.info()['2pImageType'] = 'Snap'

        # if self.param['Store']:
        #     if dirhandle is None:
        #         dirhandle = self.manager.getCurrentDir()
        #     #microscope = self.#info['microscope'] = self.param['Scope Device'].value()
        #     #scope = self.Manager.getDevice(self.param['Scope Device'])
        #     #print dir(scope)
        #     #m = self.handle.info()['microscope']
        #     ### this needs to be fixed so that the microscope info is stored in the file - current NOT
        #     ### due to API change that I can't figure out.
        #     ###
        #     #info['microscope'] = scope.getState()
        #     imgData = frame.getImage()
        #     info = frame.info
        #     if self.ui.record_button.isChecked():
        #         mainfo = [
        #             {'name': 'Frame'},
        #             {'name': 'X'},
        #             {'name': 'Y'},
        #             info
        #         ]
        #         #print 'info: ', info  
        #         data = MA.MetaArray(imgData[np.newaxis, ...], info=mainfo, appendAxis='Frame')
        #         if self.currentStack is None:
        #             fh = dirhandle.writeFile(data, '2pStack.ma', info=info, autoIncrement=True,  appendAxis='Frame')
        #             self.currentStack = fh
        #         else:
        #             data.write(self.currentStack.name(), appendAxis='Frame')
        #         self.currentStackLength += 1
        #         self.ui.record_button.setText('Recording (%d)' % self.currentStackLength)
                
        #     else:
        #         dirhandle.writeFile(imgData, '2pImage.ma', info=info, autoIncrement=True)

        return frame

    def startVideo(self):
        if self.videoRunning:
            raise RuntimeError("Video acquisition already started.")

        if self.laserDev is not None and self.laserDev.hasShutter:
            # force shutter to stay open for the duration of the acquisition
            self.laserDev.openShutter()
        try:
            self.videoRunning = True
            self.imagingCtrl.acquisitionStarted()
            while self.videoRunning:
                frame = self.takeImage(allowBlanking=False)
                if not self.imagingCtrl.ui.acquireVideoBtn.isChecked():
                    break
                if frame is False:  # aborted
                    break
                # Qt event loop is usually visited while waiting for imaging results, but
                # we can't count on that.
                QtGui.QApplication.processEvents()

        finally:
            self.videoRunning = False
            self.imagingCtrl.acquisitionStopped()
            if self.laserDev is not None and self.laserDev.hasShutter:
                self.laserDev.closeShutter()
    

    def saveParams(self, root=None):
        if root is None:
            root = self.param
            
        params = {}
        for child in root:
            params[child.name()] = child.value()
            if child.hasChildren() and child.value() is True:
                for k,v in self.saveParams(child).items():
                    params[child.name() + '.' + k] = v
        # add the laser information            
        params['wavelength'] = self.laserDev.getWavelength()
        params['laserOutputPower'] = self.laserDev.outputPower()
        
        return params
    

    def updateLaserInfo(self):
        if self.laserDev is not None:
            self.param['Scan Properties', 'Wavelength'] = (self.laserDev.getWavelength()*1e9)
            self.param['Scan Properties', 'Power'] = (self.laserDev.outputPower())
        else:
            self.param['Scan Properties', 'Wavelength'] = 0.0
            self.param['Scan Properties', 'Power'] = 0.0
         
    def takeImage(self, allowBlanking=True):
        """
        Take an image using the scanning system and PMT, and return with the data.
        """
        # first make sure laser information is updated on the module interface
        self.updateLaserInfo()

        # generate the scan protocol and task
        prot = self.generateProtocol()
        task = self.manager.createTask(prot)

        # Blank screen and execute task
        blank = allowBlanking and self.param['Scan Control', 'Blank Screen'] is True
        with ScreenBlanker(blank) as blanker:
            start = pg.ptime.time()
            task.execute(block = False)
            while not task.isDone():
                QtGui.QApplication.processEvents()
                if blanker.cancelled or self.abort:
                    task.abort()
                    self.abort = False
                    return False
                time.sleep(0.01)

        # grab results and store PMT data for display
        data = task.getResult()
        pdDevice, pdChannel = self.param['Scan Control', 'Photodetector']
        scanDev = self.scannerDev.name()
        program = prot[scanDev]['program']
        pmtData = data[pdDevice][pdChannel].view(np.ndarray)
        info = self.saveParams()
        info['time'] = start

        info['deviceTranform'] = pg.SRTTransform3D(self.scannerDev.globalTransform())
        tr = self.scanProgram.components[0].ctrlParameter().system.imageTransform()
        info['transform'] = pg.SRTTransform3D(tr)

        self.lastFrame = ImagingFrame(pmtData, program, info)
        self.updateDecomb()

        self.imagingCtrl.newFrame(self.lastFrame)

        return self.lastFrame

    def generateProtocol(self):
        # return cached command if possible
        if self.scanProtocol is not None:
            vscan = self.scanProtocol
        else:
            # Generate scan voltages
            vscan = self.scanProgram.generateVoltageArray()
            self.scanProtocol = vscan

        # sample rate, duration, and other meta data
        rect = self.scanProgram.components[0].ctrlParameter()

        scanParams = self.param.child('Scan Control')
        samples = vscan.shape[0]
        sampleRate = scanParams['Sample Rate']
        duration = samples / sampleRate
        program = self.scanProgram.saveState()  # meta-data to annotate protocol

        pcell = np.empty(vscan.shape[0], dtype=np.float32)
        pcell[:] = scanParams['Pockels']

        # Look up device names
        pdDevice, pdChannel = scanParams['Photodetector']
        scanDev = self.scannerDev.name()

        prot = {
            'protocol': {
                'duration': duration,
                },
            'DAQ' : {
                'rate': sampleRate, 
                'numPts': samples,
                'downsample': scanParams['Downsample']
                }, 
            scanDev: {
                'xCommand' : vscan[:, 0],
                'yCommand' : vscan[:, 1],
                'program': program, 
                },
            # self.attenuatorDev.name(): {self.attenuatorChannel: {'preset': self.param['Pockels']}},
            self.laserDev.name(): {
                'pCell': {'command': pcell}, # {'preset': self.param['Pockels']},
                'shutterMode': 'open',
                },
            pdDevice: {
                pdChannel: {'record': True},
            },
        }

        return prot

    def imageUpdated(self, frame):
        ## New image is displayed; update image transform
        self.imageItem.setTransform(frame.globalTransform().as2D())

    # def updateImage(self):
    #     """Update images displayed in the canvas and local view to reflect the most recently acquired data 
    #     and image processing settings.
    #     """
    
        # display the image on top of the camera image
        # self.img = pg.ImageItem(imgData) # make data into a pyqtgraph image
        # self.img.setTransform(tr)
        # self.cameraModule.window().addItem(self.img)
        # self.hideOverlayImage() # hide if the box is checked    


        # img = self.lastFrame.getImage(decomb=True)
        # self.view.setImage(img.T, autoLevels=False)


    
    # def toggleVideo_std(self, b):
    #     self.loadPreset('video-std')
    #     self.vbutton = self.ui.video_std_button
    #     if b:
    #         self.startVideo()
            
    # def toggleVideo_fast(self, b):
    #     self.loadPreset('video-fast')
    #     self.vbutton = self.ui.video_fast_button
    #     if b:
    #         self.startVideo()
            
    # def toggleVideo_ultra(self, b):
    #     self.loadPreset('video-ultra')
    #     self.vbutton = self.ui.video_ultra_button
    #     if b:
    #         self.startVideo()
        

        
    # def recordToggled(self, b):
    #     if not b:
    #         self.currentStack = None
    #         self.currentStackLength = 0
    #         self.param['Store'] = False
    #         self.ui.record_button.setText('Record Stack')
    #     else:
    #         self.param['Store'] = True # turn off recording...
            
    # def getScopeDevice(self):
    #     return self.manager.getDevice(self.param['Scope Device'])
            
    # def getScannerDevice(self):
    #     return self.manager.getDevice(self.param['Scanner Device'])
            
    # def getLaserDevice(self):
    #     return self.manager.getDevice(self.param['Laser Device'])
            
    # def setupCameraModule(self):
    #     modName = self.param['Camera Module']
    #     mod = self.manager.getModule(modName)
        
        
        # pp = pprint.PrettyPrinter(indent=4)
        # #pp.pprint(dir(mod))
        # scope = self.getScopeDevice()
        # pos = self.currentRoi.mapToParent(self.currentRoi.pos())
        # si = self.currentRoi.mapToParent(self.currentRoi.size())
        # #print 'setup: pos, size: ', pos, si
        # #pp.pprint((scope.config))
        


class ImagingFrame(imaging.Frame):
    """Represents a single collected image frame and its associated metadata."""

    def __init__(self, data, program, info):
        self.lock = Mutex(recursive=True)  # because frame may be accesed by recording thread.
        self._program_state = program
        self._program = None
        self._decomb = (0, False)
        self._image = None
        imaging.Frame.__init__(self, data, info)

    @property
    def program(self):
        with self.lock:
            if self._program is None:
                self._program = ScanProgram()
                self._program.restoreState(self._program_state)
        return self._program

    @property
    def rectScan(self):
        with self.lock:
            return self.program.components[0].ctrlParameter().system

    def getImage(self, decomb=True, offset=None):
        # if decomb is True:
        #     if offset is None:
        #         offset = self.rect.measureMirrorLag(self.data, subpixel=True)
        # else:
        #     offset = 0
        if self._image is None:
            offset, subpixel = self._decomb
            img = self.rectScan.extractImage(self._data, offset=offset, subpixel=subpixel)
            # note we transpose the image here because pg prefers (col, row) order.
            self._image = img.mean(axis=0).T

        return self._image

    def setDecomb(self, offset, subpixel):
        d = (offset, subpixel)
        if self._decomb != d:
            self._decomb = d
            self._image = None

    def autoDecomb(self):
        offset, subpixel = self._decomb
        offset = self.rectScan.measureMirrorLag(self._data, subpixel=subpixel)
        self.setDecomb(offset, subpixel)





