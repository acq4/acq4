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
import acq4.pyqtgraph as PG
from acq4.Manager import getManager
import acq4.Manager
import acq4.util.InterfaceCombo as InterfaceCombo
import acq4.pyqtgraph.parametertree as PT
import numpy as NP
import acq4.util.metaarray as MA
from acq4.devices.Microscope import Microscope
import time
import pprint
from .imagerTemplate import Ui_Form


"""
Create some useful configurations for the user.
"""
Presets = {
    'video-std': {
        'Average': 1,
        'Downsample': 1,
        'Image Width': 256,
        'Image Height': 256,
        'xSpan': 0.9,
        'ySpan': 0.9,
        'Overscan': 70,
        'Store': False,
        'Blank Screen': False,
        'Bidirectional': True,
        'Decomb': True,
        ('Decomb', 'Shift'): 170e-6,
        ('Decomb', 'Auto'): False,
    },
    'video-fast': {
        'Average': 1,
        'Downsample': 2,
        'Image Width': 128 ,
        'Image Height': 128,
        'xSpan': 0.9,
        'ySpan': 0.9,
        'Overscan': 68,
        'Store': False,
        'Blank Screen': False,
        'Bidirectional': True,
        'Decomb' : True,
        ('Decomb', 'Shift'): 85e-6,
        ('Decomb', 'Auto'): False,
    },

    'video-ultra': {
        'Downsample': 2,
        'Image Width': 64,
        'Image Height': 64,
        'xSpan': 0.15,
        'ySpan': 0.15,
        'Overscan': 250,
        'Store': False,
        'Blank Screen': False,
        'Bidirectional': True,
        'Decomb' : True,
        ('Decomb', 'Shift'): 168e-6,
        ('Decomb', 'Auto'): False,
    },
    
    'StandardDef': {
        'Average': 1,
        'Downsample': 10,
        'Image Width': 512,
        'Image Height': 512,
        'xSpan': 0.9,
        'ySpan': 0.9,
        'Overscan': 25,
       # 'Store': False,
        'Blank Screen': True,
        'Bidirectional' : True,
        'Decomb': True,
        ('Decomb', 'Shift'): 17e-6,
        ('Decomb', 'Auto'): False,
    },
    'HighDef': { # 7/25/2013 parameters for high def ok... 
        'Average': 4,
        'Downsample': 2,
        'Image Width': 1024,
        'Image Height': 1024,
        'xSpan': 0.9,
        'ySpan': 0.9,
        'Overscan': 25,
       # 'Store': False,
        'Blank Screen': True,
        'Bidirectional': True,
        'Decomb': True,
        ('Decomb', 'Shift'): 85e-6,
        ('Decomb', 'Auto'): False,
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

class ImagerView(PG.ImageView):
    """
    Subclass ImageView so that we can display the ROI differently.
    This one just catches the Roi data.
    
    10/2/2013 pbm
    """
    def __init__(self):
        PG.ImageView.__init__(self)
        self.resetFrameCount()
        
    def resetFrameCount(self):
        self.ImagerFrameCount = 0
        self.ImagerFrameArray = NP.zeros(0)
        self.ImagerFrameData = NP.zeros(0)

    def setImage(self, *args, **kargs):
        PG.ImageView.setImage(self, *args, **kargs)
        self.newFrameROI()

    def roiChanged(self):
        pass
    
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
        data, coords = self.roi.getArrayRegion(image.view(NP.ndarray), self.imageItem, axes, returnMappedCoords=True)
        if data is not None:
            while data.ndim > 1:
                data = data.mean(axis=1)
            self.ImagerFrameCount += 1
            #if self.ImagerFrameCount == 2:
            #    raise NameError('this is an error')

            self.ImagerFrameArray = NP.append(self.ImagerFrameArray, self.ImagerFrameCount)
            self.ImagerFrameData = NP.append(self.ImagerFrameData, data.mean())
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
        brush = PG.mkBrush(0.0)
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

        
class RegionCtrl(PG.ROI):
    """
    Create an ROI "Region Control" with handles, with specified size
    and color. 
    Note: Setting the ROI position here is advised, but it seems
    that when adding the ROI to the camera window with the Qt call
    window().addItem, the position is lost, and will have to be
    reset in the ROI.
    """
    def __init__(self, pos, size, roiColor = 'r'):
        PG.ROI.__init__(self, pos, size=size, pen=roiColor)
        self.addScaleHandle([0,0], [1,1])
        self.addScaleHandle([1,1], [0,0])
        self.setZValue(1200)
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
        self.roi = None # no current ROI
        self.regionCtrl = None
        self.currentRoi = None
        self.img = None # overlay image in the camera Window... 
        self.dwellTime = 0. # "pixel dwell time" computed from scan time and points.
        
        # we assume that you are not going to change the current camera or scope while running
        # ... not just yet anyway.
        # if this is to be allowed on a system, the change must be signaled to this class,
        # and we need to pick up the device in a routine that handles the change.
        try:
            self.cameraModule = self.manager.getModule(config['cameraModule'])
        except:
            self.manager.loadDefinedModule(config['cameraModule'])
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
        
        self.detectorDev = self.manager.getDevice(config['detector'][0])
        self.detectorChannel = config['detector'][1]
        
        self.attenuatorDev = self.manager.getDevice(config['attenuator'][0])
        self.attenuatorChannel = config['attenuator'][1]
        
        self.objectiveROImap = {} # this is a dict that we will populate with the name
        # of the objective and the associated ROI object .
        # That way, each objective has a scan region appopriate for it's magnification.
        
        self.ui.hide_check.stateChanged.connect(self.hideOverlayImage)
        self.ui.alphaSlider.valueChanged.connect(self.imageAlphaAdjust)        

        #self.ui.run_Button.clicked.connect(self.PMT_Run)
        self.ui.snap_Button.clicked.connect(self.PMT_Snap)
        self.ui.snap_Standard_Button.clicked.connect(self.PMT_Snap_std)
        self.ui.snap_High_Button.clicked.connect(self.PMT_Snap_high)
        
        self.ui.video_button.clicked.connect(self.toggleVideo)
        self.ui.video_std_button.clicked.connect(self.toggleVideo_std)
        self.ui.video_fast_button.clicked.connect(self.toggleVideo_fast)
        self.ui.record_button.toggled.connect(self.recordToggled)
        
        self.ui.run_button.clicked.connect(self.PMT_Run)
        self.ui.stop_button.clicked.connect(self.PMT_Stop)
        
        #self.ui.cameraSnapBtn.clicked.connect(self.cameraSnap)
        self.ui.restoreROI.clicked.connect(self.restoreROI)
        self.ui.saveROI.clicked.connect(self.saveROI)
        self.ui.Align_to_Camera.clicked.connect(self.reAlign)
        
        self.param = PT.Parameter(name = 'param', children=[
            dict(name="Preset", type='list', value='StandardDef', 
                 values=['StandardDef', 'HighDef', 'video-std', 'video-fast', 
                         'video-ultra']),
            dict(name='Store', type='bool', value=True),
            dict(name='Blank Screen', type='bool', value=True),
            dict(name='Sample Rate', type='float', value=1.0e6, suffix='Hz', dec = True, minStep=100., step=0.5, limits=[10e3, 5e6], siPrefix=True),
            dict(name='Downsample', type='int', value=1, limits=[1,None]),
            dict(name='Frame Time', type='float', readonly=True, value=0.0),
            dict(name='Average', type='int', value=1, limits=[1,100]),
            dict(name='Pockels', type='float', value= 0.03, suffix='V', dec=True, minStep=1e-3, limits=[0, 1.5], step=0.1, siPrefix=True),
            dict(name='Wavelength', type='float', value= 700, suffix = 'nm', readonly = True),
            dict(name='Power', type='float', value = 0.00, suffix = 'W', readonly = True),
            dict(name='Objective', type='str', value='Unknown', readonly=True),
            dict(name='Follow Stage', type='bool', value=True),
            dict(name='Image Width', type='int', value=500, readonly=False),
            dict(name='Image Height', type='int', value=500, readonly=False),
            #dict(name='Y = X', type='bool', value=True),
            #dict(name='Pixel Size', type='float', value=0.2e-7, readonly=True), #suffix='m', limits=[1.e-8, 1e-4], step=1e-7, siPrefix=True, readonly=True),
            dict(name='xSpan', type='float', value = 0.9, limits=[0.01, 2.5]), #limits=[0., 20.e-3], step=10e-6, siPrefix=True, readonly=True), #  True image width and height, in microns
            dict(name='ySpan', type = 'float', value = 0.9, limits=[0.01, 2.5]), # limits=[0., 20.e-3], step=10e-6, siPrefix=True, readonly=True),
            #dict(name='Xpos', type='float', value = 0.0e-6, suffix = 'm'), #, limits=[-50e-3, 50e-3], step=10e-6, siPrefix=True, readonly=True), #  True image width and height, in microns
            #dict(name='Ypos', type = 'float', value = 0.0e-6, suffix='m'), #, limits=[-50e-3, 50e-3], step=10e-6, siPrefix=True, readonly=True),

            #dict(name='XCenter', type='float', value=-0.3, suffix='V', dec=True, minStep=1e-3, limits=[-5, 5], step=0.5, siPrefix=True, readonly=True),
            #dict(name='XSweep', type='float', value=1.0, suffix='V', dec=True, minStep=1e-3, limits=[-5, 5], step=0.5, siPrefix=True, readonly=True),
            #dict(name='YCenter', type='float', value=-0.75, suffix='V', dec=True, minStep=1e-3, limits=[-5, 5], step=0.5, siPrefix=True, readonly=True),
            #dict(name='YSweep', type='float', value=1.0, suffix='V', dec=True, minStep=1e-3, limits=[-5, 5], step=0.5, siPrefix=True, readonly=True),
            dict(name='Bidirectional', type='bool', value=True),
            dict(name='Decomb', type='bool', value=True, children=[
                dict(name='Auto', type='bool', value=True),
                dict(name='Shift', type='float', value=100e-6, suffix='s', step=10e-6, siPrefix=True),
            ]),       
            dict(name='Overscan', type='float', value=25.0, suffix='%'),
            dict(name='Scope Device', type='interface', interfaceTypes=['microscope']),
            dict(name='Scanner Device', type='interface', interfaceTypes=['scanner']),
            dict(name='Laser Device', type='interface', interfaceTypes=['laser']),
            dict(name='Camera Module', type='interface', interfaceTypes=['cameraModule']),
            dict(name="Tiles", type="bool", value=False, children=[
                dict(name='Stage', type='interface', interfaceTypes='stage'),
                dict(name="X0", type="float", value=-100., suffix='um', dec=True, minStep=1, step=1, limits=[-1e3,1e3], siPrefix=True),
                dict(name="X1", type="float", value=100., suffix='um', dec=True, minStep=1, step=1, limits=[-1e3,1e3], siPrefix=True),
                dict(name="Y0", type="float", value=-100., suffix='um', dec=True, minStep=1, step=1, limits=[-1e3,1e3], siPrefix=True),
                dict(name="Y1", type="float", value=100., suffix='um', dec=True, minStep=1, step=1, limits=[-1e3,1e3], siPrefix=True),
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
        self.update() # also force update now to make sure all parameters are synchronized
        self.param.sigTreeStateChanged.connect(self.update)

    def quit(self):
        if self.img is not None:# clear the image ovelay if it exists
            self.cameraModule.window().removeItem(self.img)
            self.img = None
        for obj in self.objectiveROImap: # remove the ROI's for all objectives.
            try:
                self.cameraModule.window().removeItem(self.objectiveROImap[obj])
            except:
                pass
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
        color = 'r'
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
        #brect = self.camdev.getBoundary().boundingRect()
        
        #width = brect.width()
        #height = brect.height()
        #x = brect.x()+width*0.05
        #y = brect.y()+height*0.05
        cpos = self.cameraModule.ui.view.viewRect().center()
        #print 'camerawindow.py: addROI:: ', self.view.viewPixelSize()
        csize = [x*50 for x in self.cameraModule.ui.view.viewPixelSize()]
        
        #print self.param['xSpan']
        #csize= [width*self.param['xSpan'],  height*self.param['ySpan']]
        #cpos = [x, y]
        roiColor = self.getObjectiveColor(self.scopeDev.currentObjective) # pick up an objective color...
        roi = RegionCtrl(cpos, csize, roiColor) # Note that the position actually gets over ridden by the camera additem below..
        roi.setZValue(10000)
        self.cameraModule.window().addItem(roi)
        roi.setPos(cpos) # now is the time to do this. aaaaargh. Several hours later!!!
        roi.sigRegionChangeFinished.connect(self.roiChanged)
        #self.originalROI = [width, height, x, y]
        #print 'originalROI: ', self.originalROI
        return roi
    
    def hideROI(self, roi):
        """ just make the current roi invisible... 
        although we probalby also want to hide the associated image if it is present...
        """
        roi.hide()
    
    def restoreROI(self):
        if self.originalROI is not None:
            (width, height, x, y) = self.originalROI
            #print self.originalROI
            self.currentRoi.setSize([width, height])
            self.currentRoi.setPos([x, y])
#            print'Roi shyould be reset'
            self.roiChanged()

    def saveROI(self):
        state = self.currentRoi.getState()
        (width, height) = state['size']
        x, y = state['pos']
        self.originalROI = [width, height, x, y]
        
    def roiChanged(self):
        """ read the ROI rectangle width and height and repost
        in the parameter tree """
        state = self.currentRoi.getState()
        self.width, self.height = state['size']
        self.ui.width.setText('%8.1f' % (self.width*1e6)) # express in microns
        self.ui.height.setText('%8.1f' % (self.height*1e6))
        self.xPos, self.yPos = state['pos']
        self.ui.xpos.setText('%8.3f' % (self.xPos*1e3)) # in mm # param['Xpos'] = x
        self.ui.ypos.setText('%8.3f' % (self.yPos*1e3)) # in mm # param['Ypos'] = y
        self.pixelSize = self.width/self.param['Image Width']
        self.ui.pixelSize.setText('%8.3f' % (self.pixelSize*1e6)) # in microns
        
        # record position of ROI in Scanner's local coordinate system
        # we can use this later to allow the ROI to track stage movement
        tr = self.getScannerDevice().inverseGlobalTransform() # maps from global to device local
        pt1 = PG.Point(self.xPos, self.yPos)
        pt2 = PG.Point(self.xPos+self.width, self.yPos+self.height)
        self.currentRoi.scannerCoords = [
            tr.map(pt1),
            tr.map(pt2),
            ]

    def reAlign(self):
        self.objectiveUpdate(reset=True) # try this... 
        self.roiChanged()
    
    def update(self):
        """
        Update the presets, and read some relevant and critical laser device info into the param block
        as that will be saved with the data file. 
        """
        #check the devices first        
        # use the presets if they are engaged
        preset = self.param['Preset']
        self.loadPreset(preset)
        if self.laserDev is not None:
            self.param['Wavelength'] = (self.laserDev.getWavelength()*1e9)
            self.param['Power'] = (self.laserDev.outputPower()[0])
        else:
            self.param['Wavelength'] = 0.0
            self.param['Power'] = 0.0
        
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
                img = img[NP.newaxis, ...]
                if img is None:
                    break
                images.append(img)
                self.view.setImage(img)
                
                if i < nSteps-1:
                    ## speed 20 is quite slow; timeouts may occur if we go much slower than that..
                    stage.moveBy([0.0, 0.0, self.param['Z-Stack', 'Step Size']], speed=20, block=True)  
            imgData = NP.concatenate(images, axis=0)
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
            self.param['Timed', 'Current Frame'] = 0
            images = []
            originalPos = stage.pos
            state = self.currentRoi.getState()
            self.width, self.height = state['size']
            mp285speed = 1000
            
            #print 'Current stage position: ', currentPos
            x0 = self.param['Tiles', 'X0']*1e-6 # convert back to meters
            x1 = self.param['Tiles', 'X1']*1e-6
            y0 = self.param['Tiles', 'Y0']*1e-6
            y1 = self.param['Tiles', 'Y1']*1e-6
            tileXY = self.param['Tiles', 'StepSize']*1e-6
            nXTiles = NP.ceil((x1-x0)/tileXY)
            nYTiles = NP.ceil((y1-y0)/tileXY)
           
            xpos = NP.arange(x0, x0+nXTiles*tileXY, tileXY)+originalPos[0]
            ypos = NP.arange(y0, y0+nYTiles*tileXY, tileXY)+originalPos[1]
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
            stage.moveTo([originalPos[0], originalPos[1]],
                         speed=mp285speed, fine = True, block=True, timeout = 30.) # move and wait until complete.  
            
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
                img = img[NP.newaxis, ...]
                if img is None:
                   return
                images.append(img)
                self.view.setImage(img)
                if self.stopFlag:
                    break
                
                if i < nSteps-1:
                    time.sleep(self.param['Timed', 'Interval'])
            imgData = NP.concatenate(images, axis=0)
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
        
    def PMT_Snap(self, dirhandle=None):
        """
        Take one image as a snap, regardless of whether a Z stack or a Timed acquisition is selected
        """            

        if self.laserDev is not None and self.laserDev.hasShutter:
            self.laserDev.openShutter()
        (imgData, info) = self.takeImage()
        if self.laserDev is not None and self.laserDev.hasShutter:
            self.laserDev.closeShutter()
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
                data = MA.MetaArray(imgData[NP.newaxis, ...], info=mainfo, appendAxis='Frame')
                if self.currentStack is None:
                    fh = dirhandle.writeFile(data, '2pStack.ma', info=info, autoIncrement=True)
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
    
         
    def takeImage(self):
        """
        Take an image using the scanning system and PMT, and return with the data.
        """
        # first make sure laser information is updated on the module interface
        if self.laserDev is not None:
            self.param['Wavelength'] = (self.laserDev.getWavelength()*1e9)
            self.param['Power'] = (self.laserDev.outputPower()[0])
        else:
            self.param['Wavelength'] = 0.0
            self.param['Power'] = 0.0
        #
        # get image parameters from the ROI:
        #
        state = self.currentRoi.getState()
        w, h = state['size']
        p0 = PG.Point(0,0)
        p1 = PG.Point(w,0)
        p2 = PG.Point(0, h)
        points = [p0, p1, p2]
        points = [PG.Point(self.currentRoi.mapToView(p)) for p in points] # convert to view points (as needed for scanner)

        Xpos = self.xPos #self.param['Xpos']
        Ypos = self.yPos # self.param['Ypos']
        xCenter = Xpos # self.param['Xpos']#-width/2.0
        yCenter = Ypos # self.param['Ypos']#-height/2.0
        nPointsX = int(self.width/self.pixelSize) # self.param['Pixel Size'])
        nPointsY = int(self.height/self.pixelSize) # self.param['Pixel Size'])
        xScan = NP.linspace(0., self.width, nPointsX)
        xScan += xCenter
        sampleRate = self.param['Sample Rate']
        downsample = self.param['Downsample']
        overScan = self.param['Overscan']/100.     ## fraction of voltage scan range
        overScanWidth = self.width*overScan
        overScanPixels = int(nPointsX / 2. * overScan)
        pixelsPerRow = nPointsX + 2 * overScanPixels  ## make sure width is increased by an even number.
        samplesPerRow = pixelsPerRow * downsample
        samples = samplesPerRow * nPointsY
        if not self.param['Bidirectional']:
            saw1 = NP.linspace(0., self.width+overScanWidth, num=samplesPerRow)
            saw1 += xCenter-overScanWidth/2.0
            xSaw = NP.tile(saw1, (1, nPointsY))[0,:]
        else:
            saw1 = NP.linspace(0., self.width+overScanWidth, num=samplesPerRow)
            saw1 += xCenter-overScanWidth/2.0
            rows = [saw1, saw1[::-1]] * int(nPointsY/2)
            if len(rows) < nPointsY:
                rows.append(saw1)
            xSaw = NP.concatenate(rows, axis=0)

        yvals = NP.linspace(0., self.height, num=nPointsY)
        yvals += yCenter
        yScan = NP.empty(samples)
        for y in range(nPointsY):
            yScan[y*samplesPerRow:(y+1)*samplesPerRow] = yvals[y]
        
        # now translate this scan into scanner voltage coordinates...
        x, y = self.scannerDev.mapToScanner(xSaw, yScan, self.laserDev.name())

        # take some data
        imgData = NP.zeros((pixelsPerRow, nPointsY))
        for N in xrange(self.param['Average']):

            cmd= {'protocol': {'duration': samples/sampleRate},
                  'DAQ' : {'rate': sampleRate, 'numPts': samples, 'downsample':downsample}, 
                  'Scanner-Raw': {
                      'XAxis' : {'command': x},
                      'YAxis' : {'command': y}
                      },
                  'PockelCell': {'Switch' : {'preset': self.param['Pockels']}},
                  'PMT' : {
                      'Input': {'record': True},
                    #  'PlateVoltage': {'record' : False, 'recordInit': True}
                      }
                }
            task = self.Manager.createTask(cmd)
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
    
            data = task.getResult()
            imgData1 = data['PMT']['Input'].view(NP.ndarray)
            imgData1.shape = (nPointsY, pixelsPerRow)
            imgData += imgData1.transpose()
        
        if self.param['Average'] > 1:
            imgData = imgData/self.param['Average']
            
        if self.param['Bidirectional']:
            for y in range(1, nPointsY, 2):
                imgData[:,y] = imgData[::-1,y]
            if self.param['Decomb', 'Auto']:
                imgData, shift = self.decomb(imgData, minShift=0*sampleRate, maxShift=200e-6*sampleRate)  ## correct for mirror lag up to 200us
                self.param['Decomb', 'Shift'] = shift / sampleRate
            else:
                imgData, shift = self.decomb(imgData, auto=False, shift=self.param['Decomb', 'Shift']*sampleRate)
                
        if overScanPixels > 0:
            imgData = imgData[overScanPixels:-overScanPixels]  ## remove overscan

        if self.img is not None:
            self.cameraModule.window().removeItem(self.img)
            self.img = None
        
        # code to display the image on the camera image
        self.img = PG.ImageItem(imgData) # make data into a pyqtgraph image
        self.cameraModule.window().addItem(self.img)
        self.currentRoi.setZValue(10)
        self.hideOverlayImage()
        
        w = imgData.shape[0]
        h = imgData.shape[1]
        localPts = map(PG.Vector, [[0,0], [w,0], [0, h], [0,0,1]]) # w and h of data of image in pixels.
        globalPts = map(PG.Vector, [[Xpos, Ypos], [Xpos+self.width, Ypos], [Xpos, Ypos+self.height], [0, 0, 1]]) # actual values in global coordinates
        ##imgData.shape[0]*imgData.shape[1] # prog['points'] # sort of. - 
        m = PG.solve3DTransform(localPts, globalPts)
        m[:,2] = m[:,3]
        m[2] = m[3]
        m[2,2] = 1

        tr = QtGui.QTransform(*m[:3,:3].transpose().reshape(9))

        if self.ui.hide_check.isChecked() is False:
            if self.img is not None:
                self.cameraModule.window().removeItem(self.img)
            self.img = None
        
        # code to display the image on the camera image
            self.img = PG.ImageItem(imgData) # make data into a pyqtgraph image
            self.cameraModule.window().addItem(self.img)
            self.hideOverlayImage()
            self.img.setTransform(tr)
        
# flip the PMT image LR, since that is how it is... there is a mirror in the path
# (should this be a settable parameter? )

        imgData = NP.fliplr(imgData)
        
        if self.param['Show PMT V']:
            x=NP.linspace(0, samples/sampleRate, imgData.size)
            PG.plot(y=imgData.reshape(imgData.shape[0]*imgData.shape[1]), x=x)
        if self.param['Show Mirror V']:
            PG.plot(y=xScan, x=NP.linspace(0, samples/self.param['Sample Rate'], xScan.size))
        
        # generate all meta-data for this frame
        info = self.saveParams()
        info['transform'] = PG.SRTTransform3D(tr)
        #print 'info: ', info                            
        return (imgData, info)
    
    def decomb(self, img, minShift=0, maxShift=100, auto=True, shift=None):
        ## split image into fields
        nr = 2 * (img.shape[1] // 2)
        f1 = img[:,0:nr:2]
        f2 = img[:,1:nr+1:2]
        
        ## find optimal shift
        if auto:
            bestShift = None
            bestError = None
            #errs = []
            for shift in range(int(minShift), int(maxShift)):
                f2s = f2[:-shift] if shift > 0 else f2
                err1 = NP.abs((f1[shift:, 1:]-f2s[:, 1:])**2).sum()
                err2 = NP.abs((f1[shift:, 1:]-f2s[:, :-1])**2).sum()
                totErr = (err1+err2) / float(f1.shape[0]-shift)
                #errs.append(totErr)
                if totErr < bestError or bestError is None:
                    bestError = totErr
                    bestShift = shift
            #PG.plot(errs)
        else:
            bestShift = shift
        
        ## reconstrict from shifted fields
        leftShift = bestShift // 2
        rightShift = leftShift + (bestShift % 2)
        if rightShift == 0:
            return img, 0
        decombed = NP.zeros(img.shape, img.dtype)
        if leftShift > 0:
            decombed[:-leftShift, ::2] = img[leftShift:, ::2]
        else:
            decombed[:, ::2] = img[:, ::2]
        decombed[rightShift:, 1::2] = img[:-rightShift, 1::2]
        return decombed, bestShift
        
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
            
    def toggleVideo_ultra(self):
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

        while True:
            (img, info) = self.takeImage()
            if img is None:
                if self.laserDev.hasShutter:
                    self.laserDev.closeShutter()
                return
            self.view.setImage(img, autoLevels=False)
            QtGui.QApplication.processEvents()
            if not self.vbutton.isChecked(): # note only checks the button that called us...
                if self.laserDev.hasShutter:
                    self.laserDev.closeShutter()
                return
        
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
            
    def setupCameraModule(self):
        modName = self.param['Camera Module']
        mod = self.manager.getModule(modName)
        
        if self.regionCtrl is not None:
            self.regionCtrl.scene().removeItem(self.regionCtrl)
        
        pp = pprint.PrettyPrinter(indent=4)
        #pp.pprint(dir(mod))
        scope = self.getScopeDevice()
        #pp.pprint(dir(scope))
        pos = self.currentRoi.mapToParent(self.currentRoi.pos())
        si = self.currentRoi.mapToParent(self.currentRoi.size())
        print 'setup: pos, size: ', pos, si#pp.pprint((scope.config))
        #self.regionCtrl = RegionCtrl(self.currentRoi.pos(), self.currentRoi.size())
        #mod.addItem(self.currentRoi, z=1000)
        
    def cameraSnap(self):
        width = self.param['Image Width']
        #if self.param['Y = X']:
        #    height = width
        #else:
        height = self.param['Image Height']
        
        #xscan = self.param['XSweep']/2.0
        #xcenter = self.param['XCenter']
        #ycenter = self.param['YCenter']
        #if self.param['Y = X']:
            #yscan = xscan
        #else:
            #yscan = self.param['YSweep']/2.0
            
        xscan = self.regionCtrl.width()
        yscan = self.regionCtrl.height()
        xcenter = self.regionCtrl.center().x()
        ycenter = self.regionCtrl.center().y()
            
        sampleRate = self.param['Sample Rate']
        downsample = self.param['Downsample']
        overscan = self.param['Overscan']/100.     ## fraction of voltage scan range
        xscan *= overscan + 1.0 
        overscanPixels = int(width / 2. * overscan)
        pixelsPerRow = width + 2 * overscanPixels  ## make sure width is increased by an even number.
        samplesPerRow = pixelsPerRow * downsample
        samples = samplesPerRow * height
        if not self.param['Bidirectional']:
            saw1 = NP.linspace(xcenter-xscan, xcenter+xscan, samplesPerRow)
            xScan = NP.tile(saw1, (1, height))[0,:]
        else:
            saw1 = NP.linspace(xcenter-xscan, xcenter+xscan, samplesPerRow)
            rows = [saw1, saw1[::-1]] * int(height/2)
            if len(rows) < height:
                rows.append(saw1)
            xScan = NP.concatenate(rows, axis=0)
            
        yvals = NP.linspace(ycenter-yscan, ycenter+yscan, height)
        yScan = NP.empty(samples)
        for y in range(height):
            yScan[y*samplesPerRow:(y+1)*samplesPerRow] = yvals[y]
        
            
        cmd= {'protocol': {'duration': samples/sampleRate},
              'DAQ' : {'rate': sampleRate, 'numPts': samples, 'downsample':downsample}, 
              #'Scanner-Raw': {
                  #'XAxis' : {'command': xScan},
                  #'YAxis' : {'command': yScan}
                  #},
              'Scanner': {
                  'xPosition' : xScan,
                  'yPosition' : yScan
                  },
              self.attenuatorDev.name(): {self.attenuatorChannel : {'preset': self.param['Pockels']}},
              self.detectorDev.name() : {
                  self.detectorChannel: {'record': True},
                  }
            }
        # take some data
        task = self.Manager.createTask(cmd)
        if self.param['Blank Screen']:
            with ScreenBlanker():
                task.execute(block = False)
                while not task.isDone():
                    QtGui.QApplication.processEvents()
                    time.sleep(0.1)
        else:
            task.execute(block = False)
            while not task.isDone():
                QtGui.QApplication.processEvents()
                time.sleep(0.1)

        data = task.getResult()
        imgData = data[self.detectorDev.name()]['Input'].view(NP.ndarray)
        imgData.shape = (height, pixelsPerRow)
        imgData = imgData.transpose()
        
        if self.param['Bidirectional']:
            for y in range(1, height, 2):
                imgData[:,y] = imgData[::-1,y]
            if self.param['Decomb', 'Auto']:
                imgData, shift = self.decomb(imgData, minShift=0*sampleRate, maxShift=200e-6*sampleRate)  ## correct for mirror lag up to 200us
                self.param['Decomb', 'Shift'] = shift / sampleRate
            else:
                #print self.param['Decomb', 'Shift'], sampleRate
                imgData, shift = self.decomb(imgData, auto=False, shift=self.param['Decomb', 'Shift']*sampleRate)
            
        
        if overscanPixels > 0:
            imgData = imgData[overscanPixels:-overscanPixels]  ## remove overscan

        if self.param['Show PMT V']:
            PG.plot(y=imgData, x=NP.linspace(0, samples/sampleRate, imgData.size))
        if self.param['Show Mirror V']:
            PG.plot(y=xScan, x=NP.linspace(0, samples/self.param['Sample Rate'], xScan.size))

        self.view.setImage(imgData)

        return imgData
        