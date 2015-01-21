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

from acq4.modules.Module import Module
from PyQt4 import QtGui, QtCore
from acq4.pyqtgraph import ImageView
import acq4.pyqtgraph as pg
from acq4.Manager import getManager
import acq4.Manager
import acq4.util.InterfaceCombo as InterfaceCombo
import acq4.pyqtgraph.parametertree as PT
import numpy as np
import acq4.util.metaarray as MA
from acq4.devices.Microscope import Microscope
import time
import pprint
from .imagerTemplate import Ui_Form
from acq4.devices.Scanner.scan_program import ScanProgram
from acq4.devices.Scanner.scan_program.rect import RectScan
# from acq4.devices.Scanner.scan_program.rect import ScannerUtility

# SUF = ScannerUtility()

"""
Create some useful configurations for the user.
"""
Presets = {
    'video-std': {
        'Average': 1,
        'Downsample': 1,
        'Image Width': 256,
        'Image Height': 256,
        'xSpan': 1.0,
        'ySpan': 1.0,
        'Store': False,
        'Blank Screen': False,
        'Bidirectional': True,
        'Decomb': True,
    },
    'video-fast': {
        'Average': 1,
        'Downsample': 2,
        'Image Width': 128 ,
        'Image Height': 128,
        'xSpan': 1.0,
        'ySpan': 1.0,
        'Store': False,
        'Blank Screen': False,
        'Bidirectional': True,
        'Decomb' : True,
    },

    'video-ultra': {
        'Downsample': 2,
        'Image Width': 64,
        'Image Height': 64,
        'xSpan': 0.15,
        'ySpan': 0.15,
        'Store': False,
        'Blank Screen': False,
        'Bidirectional': True,
        'Decomb' : True,
    },
    
    'StandardDef': {
        'Average': 1,
        'Downsample': 10,
        'Image Width': 512,
        'Image Height': 512,
        'xSpan': 1.0,
        'ySpan': 1.0,
        'Blank Screen': True,
        'Bidirectional' : True,
        'Decomb': True,
    },
    'HighDef': { # 7/25/2013 parameters for high def ok... 
        'Average': 4,
        'Downsample': 2,
        'Image Width': 1024,
        'Image Height': 1024,
        'xSpan': 1.0,
        'ySpan': 1.0,
        'Blank Screen': True,
        'Bidirectional': True,
        'Decomb': True,
    },
}

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

class ImagerView(pg.ImageView):
    """
    Subclass ImageView so that we can display the ROI differently.
    This one just catches the Roi data.
    
    10/2/2013 pbm
    """
    def __init__(self):
        pg.ImageView.__init__(self)
        self.resetFrameCount()
        
    def resetFrameCount(self):
        self.ImagerFrameCount = 0
        self.ImagerFrameArray = np.zeros(0)
        self.ImagerFrameData = np.zeros(0)

    def setImage(self, *args, **kargs):
        pg.ImageView.setImage(self, *args, **kargs)
        self.newFrameROI()

    def roiChanged(self):
        self.newFrameROI()
    
    def newFrameROI(self):
        """
        override ROI display information
        """
        if self.image is None:
            return           
        image = self.getProcessedImage()
        if image.ndim == 2:
            axes = (0, 1)
        elif image.ndim == 3:
            axes = (1, 2)
        else:
            return
        data, coords = self.roi.getArrayRegion(image.view(np.ndarray), self.imageItem, axes, returnMappedCoords=True)
        if data is not None:
            while data.ndim > 1:
                data = data.mean(axis=1)
            self.ImagerFrameCount += 1
            #if self.ImagerFrameCount == 2:
            #    raise NameError('this is an error')

            self.ImagerFrameArray = np.append(self.ImagerFrameArray, self.ImagerFrameCount)
            self.ImagerFrameData = np.append(self.ImagerFrameData, data.mean())
#            print self.ImagerFrameArray
#            print self.ImagerFrameData
            self.roiCurve.setData(x = self.ImagerFrameArray, y = self.ImagerFrameData)
            #if image.ndim == 3:
                #self.roiCurve.setData(y=data, x=self.tVals)
            #else:
                #while coords.ndim > 2:
                    #coords = coords[:,:,0]
                #coords = coords - coords[:,0,np.newaxis]
                #xvals = (coords**2).sum(axis=0) ** 0.5
                #self.roiCurve.setData(y=data, x=xvals)


class Black(QtGui.QWidget):
    """ make a black rectangle to fill screen when "blanking" """
    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        brush = pg.mkBrush(0.0)
        p.fillRect(self.rect(), brush)
        p.end()
     

class ScreenBlanker:
    """
    Perform the blanking on ALL screens that we can detect.
    This is so that extraneous light does not leak into the 
    detector during acquisition.
    """
    def __enter__(self):
        self.widgets = []
        d = QtGui.QApplication.desktop()
        for i in range(d.screenCount()): # look for all screens
            w = Black()
            self.widgets.append(w) # make a black widget
            sg = d.screenGeometry(i) # get the screen size
            w.move(sg.x(), sg.y()) # put the widget there
            w.showFullScreen() # duh
        QtGui.QApplication.processEvents() # make it so
        
    def __exit__(self, *args):
        for w in self.widgets:
            w.hide() # just take them away
        self.widgets = []

        
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
        self.setZValue(1200)
        #self.addRotateHandle([1,0], [0,1])
        #self.addRotateHandle([0,1], [1,0])

class TileControl(pg.ROI):
    """
    Create an ROI for the Tile Regions. Note that the color is RED, 
    """    
    def __init__(self, pos, size, roiColor = 'r'):
        pg.ROI.__init__(self, pos, size=size, pen=roiColor)
        self.addScaleHandle([0,0], [1,1])
        self.addScaleHandle([1,1], [0,0])
        self.setZValue(1400)
        #self.addRotateHandle([1,0], [0,1])
        #self.addRotateHandle([0,1], [1,0])
    

class Imager(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config) 
        self.win = ImagerWindow(self) # make the main window - mostly to catch window close event...
        self.ui = Ui_Form()
        self.testMode = False # set to True to just display the scan signals
        self.win.show()
        self.win.setWindowTitle('Multiphoton Imager V 1.01')
        self.win.resize(1200, 900) # make the window big enough to use on a large monitor...

        self.w1 = QtGui.QSplitter() # divide l, r
        self.w1.setOrientation(QtCore.Qt.Horizontal)
        self.w2s = QtGui.QSplitter()
        self.w2s.setOrientation(QtCore.Qt.Vertical)

        self.win.setCentralWidget(self.w1) # w1 is the "main window" splitter
        self.w1.addWidget(self.w2s) # now we add w2s, the spliter on the left
        self.ui.setupUi(self.w2s)  # put the ui on the top 
        # create the user interface
        self.tree = PT.ParameterTree()
        self.w2s.addWidget(self.tree) # put the parameters on the bottom
        self.w2s.setSizes([1,1,900]) # Ui top widget has multiple splitters itself - force small space..
        self.view = ImagerView()
        self.w1.addWidget(self.view)   # add the view to the right of w1     
        self.originalROI = None
        self.currentStack = None
        self.currentStackLength = 0
        self.regionCtrl = None
        self.currentRoi = None
        self.tileRoi = None
        self.tileRoiVisible = False
        self.tilexPos = 0.
        self.tileyPos = 0.
        self.tileWidth = 2e-4
        self.tileHeight = 2e-4
        self.img = None # overlay image in the camera Window... 
        self.dwellTime = 0. # "pixel dwell time" computed from scan time and points.
        self.fieldSize = 63.0*120e-6 # field size for 63x, will be scaled for others
        
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
        #self.scopeDev = self.camdev.scopeDev
        self.laserDev = self.manager.getDevice(config['laser'])
        
        self.scannerDev = self.manager.getDevice(config['scanner'])
        #self.scannerDev.sigGlobalSubdeviceChanged.connect(self.objectiveUpdate)
        #self.scannerDev.sigGlobalTransformChanged.connect(self.transformUpdate)
        
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
        
        self.objectiveROImap = {} # this is a dict that we will populate with the name
        # of the objective and the associated ROI object .
        # That way, each objective has a scan region appopriate for it's magnification.
        
        self.ui.hide_check.stateChanged.connect(self.hideOverlayImage)
        self.ui.alphaSlider.valueChanged.connect(self.imageAlphaAdjust)        

        self.ui.snap_Button.clicked.connect(self.PMT_SnapClicked)
        self.ui.snap_Standard_Button.clicked.connect(self.PMT_Snap_std)
        self.ui.snap_High_Button.clicked.connect(self.PMT_Snap_high)
        
        self.ui.video_button.clicked.connect(self.toggleVideo)
        self.ui.video_std_button.clicked.connect(self.toggleVideo_std)
        self.ui.video_fast_button.clicked.connect(self.toggleVideo_fast)
        self.ui.record_button.toggled.connect(self.recordToggled)
        
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
            dict(name="Preset", type='list', value='StandardDef', 
                 values=['StandardDef', 'HighDef', 'video-std', 'video-fast', 
                         'video-ultra']),
            dict(name='Store', type='bool', value=True),
            dict(name='Blank Screen', type='bool', value=True),
            dict(name='Image Width', type='int', value=500, readonly=False),
            dict(name='Image Height', type='int', value=500, readonly=False),
            dict(name='Frame Time', type='float', value=50e-3),
            dict(name='Sample Rate', type='float', value=1.0e6, suffix='Hz', dec = True, minStep=100., step=0.5, limits=[10e3, 5e6], siPrefix=True),
            dict(name='Downsample', type='int', value=1, limits=[1,None]),
            dict(name='Average', type='int', value=1, limits=[1,100]),
            dict(name='Pockels', type='float', value=0.03, suffix='V', step=0.005, limits=[0, 1.5], siPrefix=True),
            dict(name='Wavelength', type='float', value=700, suffix='nm', readonly=True),
            dict(name='Power', type='float', value=0.00, suffix='W', readonly=True),
            dict(name='Objective', type='str', value='Unknown', readonly=True),
            dict(name='Follow Stage', type='bool', value=True),
            dict(name='xSpan', type='float', value=1.0, limits=[0.01, 2.5]), #limits=[0., 20.e-3], step=10e-6, siPrefix=True, readonly=True), #  True image width and height, in microns
            dict(name='ySpan', type='float', value=1.0, limits=[0.01, 2.5]), # limits=[0., 20.e-3], step=10e-6, siPrefix=True, readonly=True),
            dict(name='Bidirectional', type='bool', value=True),
            dict(name='Decomb', type='bool', value=True, children=[
                dict(name='Auto', type='bool', value=True),
                dict(name='Shift', type='float', value=100e-6, suffix='s', step=10e-6, siPrefix=True),
            ]),       
            dict(name='Overscan', type='float', value=150e-6, suffix='s', siPrefix=True),
            dict(name='Scope Device', type='interface', interfaceTypes=['microscope']),
            dict(name='Scanner Device', type='interface', interfaceTypes=['scanner']),
            dict(name='Laser Device', type='interface', interfaceTypes=['laser']),
            dict(name='Photodetector', type='list', values=self.detectors),
            dict(name='Camera Module', type='interface', interfaceTypes=['cameraModule']),
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
        self.stopFlag = False
        self.tree.setParameters(self.param)

        self.Manager = manager
        # insert an ROI into the camera image that corresponds to our scan area                
        self.objectiveUpdate() # force update of objective information and create appropriate ROI
        # check the devices...        
        self.updateParams() # also force update now to make sure all parameters are synchronized
        self.param.sigTreeStateChanged.connect(self.updateParams)

    def quit(self):
        if self.img is not None:# clear the image ovelay if it exists
            self.cameraModule.window().removeItem(self.img)
            self.img = None
        for obj in self.objectiveROImap: # remove the ROI's for all objectives.
            try:
                self.cameraModule.window().removeItem(self.objectiveROImap[obj])
            except:
                pass
        if self.tileRoi is not None:
            self.cameraModule.window().removeItem(self.tileRoi)
            self.tileRoi = None
        Module.quit(self)

    def objectiveUpdate(self, reset=False):
        """ Update the objective information and the associated ROI
        Used to report that the objective has changed in the parameter tree,
        and then reposition the ROI that drives the image region.
        """
        if self.img is not None:# clear the image ovelay if it exists
            self.cameraModule.window().removeItem(self.img)
            self.img = None
        self.param['Objective'] = self.scopeDev.currentObjective.name()
        if reset:
            self.clearROIMap()
        if self.param['Objective'] not in self.objectiveROImap: # add the objective and an ROI
            print "create roi:",  self.param['Objective']
            self.objectiveROImap[self.param['Objective']] = self.createROI()
        for obj in self.objectiveROImap:
            if obj == self.param['Objective']:
                self.currentRoi = self.objectiveROImap[obj]
                self.currentRoi.show()
                self.roiChanged() # do this now as well so that the parameter tree is correct. 

                continue
            self.hideROI(self.objectiveROImap[obj])

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
        globalTr = self.getScannerDevice().globalTransform()
        pt1 = globalTr.map(self.currentRoi.scannerCoords[0])
        pt2 = globalTr.map(self.currentRoi.scannerCoords[1])
        diff = pt2 - pt1
        self.currentRoi.setPos(pt1)
        self.currentRoi.setSize(diff)
        #self.originalROI = [diff.x, diff.y, pt1.x, pt1.y]
        
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
    
    def hideROI(self, roi):
        """ just make the current roi invisible... 
        although we probalby also want to hide the associated image if it is present...
        """
        roi.hide()
        self.hideOverlayImage()
    
    def restoreROI(self):
        
        if self.originalROI is not None:
            (width, height, x, y) = self.originalROI
            #print self.originalROI
            self.currentRoi.setSize([width, height])
            self.currentRoi.setPos([x, y])
#            print'Roi shyould be reset'
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
        self.originalROI = [width, height, x, y]
        
    def roiChanged(self):
        """ read the ROI rectangle width and height and repost
        in the parameter tree """
        roi = self.currentRoi
        state = roi.getState()
        w, h = state['size']
        rparam = self.scanProgram.components[0].ctrlParameter()
        rparam.system.p0 = pg.Point(roi.mapToView(pg.Point(0,h)))  # top-left
        rparam.system.p1 = pg.Point(roi.mapToView(pg.Point(w,h)))  # rop-right
        rparam.system.p2 = pg.Point(roi.mapToView(pg.Point(0,0)))  # bottom-left

        #print 'roiChanged state: ', state
        # self.width, self.height = state['size']
        # self.ui.width.setText('%8.1f' % (self.width*1e6)) # express in microns
        # self.ui.height.setText('%8.1f' % (self.height*1e6))
        # self.xPos, self.yPos = state['pos']
        # self.ui.xpos.setText('%8.3f' % (self.xPos*1e3)) # in mm # param['Xpos'] = x
        # self.ui.ypos.setText('%8.3f' % (self.yPos*1e3)) # in mm # param['Ypos'] = y
        # self.pixelSize = self.width/self.param['Image Width']
        # self.ui.pixelSize.setText('%8.3f' % (self.pixelSize*1e6)) # in microns
        
        # # record position of ROI in Scanner's local coordinate system
        # # we can use this later to allow the ROI to track stage movement
        # tr = self.getScannerDevice().inverseGlobalTransform() # maps from global to device local
        # pt1 = pg.Point(self.xPos, self.yPos)
        # pt2 = pg.Point(self.xPos+self.width, self.yPos+self.height)
        # self.currentRoi.scannerCoords = [
        #     tr.map(pt1),
        #     tr.map(pt2),
        #     ]

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
        self.tileRoi.setPos(cpos) # now is the time to do this. aaaaargh. Several hours later!!!
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
        tr = self.getScannerDevice().inverseGlobalTransform() # maps from global to device local
        pt1 = pg.Point(self.tilexPos, self.tileyPos)
        pt2 = pg.Point(self.tilexPos+self.tileWidth, self.tileyPos+self.tileHeight)
        self.tileRoi.scannerCoords = [
            tr.map(pt1),
            tr.map(pt2),
            ]

        
    def updateParams(self):
        """Parameters have changed; update any dependent parameters and the scan program.
        """
        #check the devices first        
        # use the presets if they are engaged
        # preset = self.param['Preset']
        # self.loadPreset(preset)
        if self.laserDev is not None:
            self.param['Wavelength'] = (self.laserDev.getWavelength()*1e9)
            self.param['Power'] = (self.laserDev.outputPower())
        else:
            self.param['Wavelength'] = 0.0
            self.param['Power'] = 0.0

        self.scanProgram.setDevices(scanner=self.getScannerDevice(), laser=self.getLaserDevice())
        rect = self.scanProgram.components[0]
        rparams = rect.ctrlParameter()
        rparams.system.sampleRate = self.param['Sample Rate']
        rparams.system.downsample = self.param['Downsample']
        rparams['minOverscan'] = self.param['Overscan']
        rparams['bidirectional'] = True
        rparams['frameDuration'] = self.param['Frame Time']
        rparams['frameDuration', 'fixed'] = True
        rparams['pixelAspectRatio'] = self.param['Downsample']
        rparams['pixelAspectRatio', 'fixed'] = True

        self.param['Image Width'] = rparams['pixelWidth']
        self.param['Image Height'] = rparams['pixelWidth']

        
    def loadPreset(self, preset):
        """
        load the selected preset into the parameters, and calculate some
        useful parameters for display for the user.
        """
        if preset != '':
            self.param['Preset'] = ''
            global Presets
            for k,v in Presets[preset].iteritems():
                self.param[k] = v
                
       # with every change, recalculate some values about the display
        state = self.currentRoi.getState()
        self.width, self.height = state['size']
        self.pixelSize = self.width/self.param['Image Width']
        self.ui.pixelSize.setText('%8.3f' % (self.pixelSize*1e6))
        self.param['Frame Time'] = self.param['Image Width']*self.param['Image Height']*self.param['Downsample']/self.param['Sample Rate']
        self.param['Z-Stack', 'Depth'] = self.param['Z-Stack', 'Step Size'] * (self.param['Z-Stack', 'Steps']-1)
        self.param['Timed', 'Duration'] = self.param['Timed', 'Interval'] * (self.param['Timed', 'N Intervals']-1)
        self.dwellTime = self.param['Downsample']/self.param['Sample Rate']
        self.ui.dwellTime.setText('%6.1f' % (self.dwellTime*1e6))
                
    def imageAlphaAdjust(self):
        if self.img is None:
            return
        alpha = self.ui.alphaSlider.value()
        self.img.setImage(opacity=float(alpha/100.))
        
    def hideOverlayImage(self):
        if self.img is None:
            return
        if self.ui.hide_check.isChecked() is True:
            self.img.hide()
        else:
            self.img.show()
        
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

            
    def PMT_Snap_std(self):
        self.loadPreset('StandardDef')
        self.PMT_Snap()

    def PMT_Snap_high(self):
        self.loadPreset('HighDef')
        self.PMT_Snap()
    
    def PMT_SnapClicked(self):
        """
        Prevent passing button state junk from Qt to the snap routine instead of dirhandle.
        """
        self.PMT_Snap()
        
    def PMT_Snap(self, dirhandle=None):
        """
        Take one image as a snap, regardless of whether a Z stack or a Timed acquisition is selected
        """            
        ## moved shutter operations to takeImage itself.
        (imgData, info) = self.takeImage()
        if self.testMode or imgData is None:
            return
        if dirhandle is None:
            dirhandle = self.manager.getCurrentDir()
        self.view.setImage(imgData)
        info['2pImageType'] = 'Snap'
        if self.param['Store']:
            #microscope = self.#info['microscope'] = self.param['Scope Device'].value()
            #scope = self.Manager.getDevice(self.param['Scope Device'])
            #print dir(scope)
            #m = self.handle.info()['microscope']
           ### this needs to be fixed so that the microscope info is stored in the file - current NOT
           ### due to API change that I can't figure out.
           ###
           #info['microscope'] = scope.getState()
            if self.ui.record_button.isChecked():
                mainfo = [
                    {'name': 'Frame'},
                    {'name': 'X'},
                    {'name': 'Y'},
                    info
                ]
                #print 'info: ', info    
                data = MA.MetaArray(imgData[np.newaxis, ...], info=mainfo, appendAxis='Frame')
                if self.currentStack is None:
                    fh = dirhandle.writeFile(data, '2pStack.ma', info=info, autoIncrement=True,  appendAxis='Frame')
                    self.currentStack = fh
                else:
                    data.write(self.currentStack.name(), appendAxis='Frame')
                self.currentStackLength += 1
                self.ui.record_button.setText('Recording (%d)' % self.currentStackLength)
                
            else:
                dirhandle.writeFile(imgData, '2pImage.ma', info=info, autoIncrement=True)
        return(imgData, info)
    
    def PMT_Stop(self):
        self.stopFlag = True

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
    
         
    def takeImage(self, doShutter = True, reCompute = True):
        """
        Take an image using the scanning system and PMT, and return with the data.
        doShutter True means that we normally trigger the shutter from here
        but there may be times when that is not appropriate
        """
        # first make sure laser information is updated on the module interface
        if self.laserDev is not None:
            self.param['Wavelength'] = (self.laserDev.getWavelength()*1e9)
            self.param['Power'] = (self.laserDev.outputPower())
        else:
            self.param['Wavelength'] = 0.0
            self.param['Power'] = 0.0
        

        # compute the scan voltages and return some computed values
        cmd = self.scanProgram.generateVoltageArray()
        self.xScanner = cmd[:,0]
        self.yScanner = cmd[:,1]

        # (self.xScanner, self.yScanner) = SUF.designRectScan(scannerDev = self.scannerDev,
        #                         laserDev = self.laserDev.name(), 
        #                         rectRoi = points,
        #                         pixelSize = self.pixelSize,
        #                         sampleRate = self.param['Sample Rate'],
        #                         downSample = self.param['Downsample'],
        #                         overScan = self.param['Overscan'],
        #                         bidirectional = self.param['Bidirectional'])

        

        # Now, take some data
        # imgData = np.zeros(SUF.getScanXYSize()) # allocate an array
        # samples = SUF.getSamples()
        rect = self.scanProgram.components[0].ctrlParameter()
        samples = cmd.shape[0]
        sampleRate = self.param['Sample Rate']
        duration = samples / sampleRate
        program = self.scanProgram.saveState()  # meta-data to annotate protocol

        # set up a task for the task manager.
        pdDevice, pdChannel = self.param['Photodetector']
        scanDev = self.param['Scanner Device']

        laserCmd = {'pCell': {'preset': self.param['Pockels']},
                    'shutterMode': 'open',}

        cmd= {'protocol': {'duration': duration},
              'DAQ' : {'rate': sampleRate, 'numPts': samples,
                       'downsample': self.param['Downsample']}, 
              scanDev: {
                  'xCommand' : self.xScanner,
                  'yCommand' : self.yScanner,
                  'program': program, 
                  },
              # self.attenuatorDev.name(): {self.attenuatorChannel: {'preset': self.param['Pockels']}},
              self.laserDev.name(): laserCmd,  # 
              pdDevice: {
                  pdChannel: {'record': True},
                #  'PlateVoltage': {'record' : False, 'recordInit': True}
                  }
            }

        task = self.Manager.createTask(cmd)

        # Blank screen and execute task
        if self.param['Blank Screen'] and not self.ui.video_button.isChecked(): # prevent video push from using blanking
            with ScreenBlanker():
                task.execute(block = False)
                while not task.isDone():
                    QtGui.QApplication.processEvents()
                    time.sleep(0.01)
        else:
            task.execute(block = False)
            while not task.isDone():
                QtGui.QApplication.processEvents()
                time.sleep(0.01)

        # Close shutter if needed
        if doShutter and self.laserDev is not None and self.laserDev.hasShutter:
            self.laserDev.closeShutter() # immediately after acquisition...        

        # grab results and store PMT data for display
        data = task.getResult()
        pmtData = data[pdDevice][pdChannel].view(np.ndarray)
        self.lastFrame = ImagingFrame(pmtData, program)
        self.updateImage()

        # xys = SUF.getScanXYSize()
        # imgData1.shape = (xys[1], xys[0]) # (npointsY, pixelsPerRow) # make 2d image
        # imgData += imgData1.transpose() # sum if we are averaging.

        # if self.param['Average'] > 1:
        #     imgData = imgData/self.param['Average']            
        
        # if self.param['Bidirectional']:
        #     imgData, shift = SUF.adjustBidirectional(imgData, 
        #                                                     self.param['Decomb', 'Auto'],
        #                                                     self.param['Decomb', 'Shift'])
        #     if self.param['Decomb', 'Auto']:
        #         self.param['Decomb', 'Shift'] = shift
                
        # imgData = SUF.removeOverscan(imgData)

        # w = imgData.shape[0]
        # h = imgData.shape[1]
        # localPts = map(pg.Vector, [[0,h], [w,h], [0, 0], [0,0,1]]) # w and h of data of image in pixels.
        # globalPts = map(pg.Vector, [points[0], 
        #                             points[1], 
        #                             points[2], [0, 0, 1]]) # actual values in global coordinates
        # m = pg.solve3DTransform(localPts, globalPts)
        # m[:,2] = m[:,3]
        # m[2] = m[3]
        # m[2,2] = 1
        # tr = QtGui.QTransform(*m[:3,:3].transpose().reshape(9))

        # if self.param['Show PMT V']:
        #     xv=np.linspace(0, samples/sampleRate, imgData.size)
        #     pg.plot(y=imgData.reshape(imgData.shape[0]*imgData.shape[1]), x=xv)
        # if self.param['Show Mirror V']:
        #     pg.plot(y=y, x=np.linspace(0, samples/self.param['Sample Rate'], len(x)))
        
        # generate all meta-data for this frame
        # info = self.saveParams()
        # info['transform'] = pg.SRTTransform3D(tr)
        #print 'info: ', info
        return self.lastFrame


    def updateImage(self):
        """Update images displayed in the canvas and local view to reflect the most recently acquired data 
        and image processing settings.
        """
    
        # display the image on top of the camera image
        # self.img = pg.ImageItem(imgData) # make data into a pyqtgraph image
        # self.img.setTransform(tr)
        # self.cameraModule.window().addItem(self.img)
        # self.hideOverlayImage() # hide if the box is checked    


        img = self.lastFrame.getImage(decomb=True, auto=True)
        self.view.setImage(img, autoLevels=False)

    
    def toggleVideo_std(self, b):
        self.loadPreset('video-std')
        self.vbutton = self.ui.video_std_button
        if b:
            self.startVideo()
            
    def toggleVideo_fast(self, b):
        self.loadPreset('video-fast')
        self.vbutton = self.ui.video_fast_button
        if b:
            self.startVideo()
            
    def toggleVideo_ultra(self, b):
        self.loadPreset('video-ultra')
        self.vbutton = self.ui.video_ultra_button
        if b:
            self.startVideo()
        
    def toggleVideo(self, b):
        self.vbutton = self.ui.video_button
        if b:
            self.startVideo()
            
    def startVideo(self):
        if self.laserDev.hasShutter:
            self.laserDev.openShutter()
        self.view.resetFrameCount() # always reset the ROI in the imager display if it is being used

        reCompute = True
        if self.laserDev is not None and self.laserDev.hasShutter:
            self.laserDev.openShutter()
        try:
            while True:
                (img, info) = self.takeImage(reCompute=reCompute)
                reCompute = False
                if img is None:
                    return
                QtGui.QApplication.processEvents()
                if not self.vbutton.isChecked(): # note only checks the button that called us...
                    return
        finally:
            if self.laserDev is not None and self.laserDev.hasShutter:
                self.laserDev.closeShutter()
        
    def recordToggled(self, b):
        if not b:
            self.currentStack = None
            self.currentStackLength = 0
            self.param['Store'] = False
            self.ui.record_button.setText('Record Stack')
        else:
            self.param['Store'] = True # turn off recording...
            
    def getScopeDevice(self):
        return self.manager.getDevice(self.param['Scope Device'])
            
    def getScannerDevice(self):
        return self.manager.getDevice(self.param['Scanner Device'])
            
    def getLaserDevice(self):
        return self.manager.getDevice(self.param['Laser Device'])
            
    def setupCameraModule(self):
        modName = self.param['Camera Module']
        mod = self.manager.getModule(modName)
        
        if self.regionCtrl is not None:
            self.regionCtrl.scene().removeItem(self.regionCtrl)
        
        pp = pprint.PrettyPrinter(indent=4)
        #pp.pprint(dir(mod))
        scope = self.getScopeDevice()
        pos = self.currentRoi.mapToParent(self.currentRoi.pos())
        si = self.currentRoi.mapToParent(self.currentRoi.size())
        #print 'setup: pos, size: ', pos, si
        #pp.pprint((scope.config))
        


class ImagingFrame(object):
    """Represents a single collected image frame and its associated metadata."""

    def __init__(self, data, program):
        self.data = data  # raw pmt signal
        self.program = ScanProgram()
        self.program.restoreState(program)
        self.rect = self.program.components[0].ctrlParameter().system

    def getImage(self, decomb=True, auto=False, offset=None):
        offset = self.rect.measureMirrorLag(self.data, subpixel=True)
        return self.rect.extractImage(self.data, offset=offset, subpixel=True)
