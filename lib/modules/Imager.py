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
# 2012 Paul B. Manis, Ph.D. and Luke Campagnola
# UNC Chapel Hill
# Distributed under MIT/X11 license. See license.txt for more infomation.
#

from lib.modules.Module import Module
from PyQt4 import QtGui, QtCore
from pyqtgraph import ImageView
import pyqtgraph as PG
from lib.Manager import getManager
import lib.Manager
import InterfaceCombo
import pyqtgraph.parametertree as PT
import numpy as NP
import metaarray as MA
import time
import pprint

"""
Create some useful configurations for the user.
"""
Presets = {
    'video-std': {
        'Downsample': 1,
        #'Image Width': 200 ,
        #'Image Height': 200,
        'Pixel Size' : 0.5e-6,
        'Overscan': 60,
        'Store': False,
        'Blank Screen': False,
        ('Decomb', 'Shift'): 173e-6,
        ('Decomb', 'Auto'): False,
    },
    'video-fast': {
        'Downsample': 2,
        #'Image Width': 128 ,
        #'Image Height': 128,
         'Pixel Size' : 2e-6,
         'Overscan': 60,
        'Store': False,
        'Blank Screen': False,
        ('Decomb', 'Shift'): 58e-6,
        ('Decomb', 'Auto'): False,
    },

    'StandardDef': {
        'Downsample': 10,
        #'Image Width': 500,
        #'Image Height': 500,
         'Pixel Size' : 0.5e-6,
         'Overscan': 5,
        'Store': False,
        'Blank Screen': True,
        ('Decomb', 'Shift'): 17e-6,
        ('Decomb', 'Auto'): False,
    },
    'HighDef': {
        'Downsample': 10,
        #'Image Width': 1000,
        #'Image Height': 1000,
         'Pixel Size' : 2e-7,
         'Overscan': 5,
        'Store': False,
        'Blank Screen': True,
        ('Decomb', 'Shift'): 17e-6,
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
        self.setZValue(1000)
        #self.addRotateHandle([1,0], [0,1])
        #self.addRotateHandle([0,1], [1,0])


class Imager(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config) 
        self.win = ImagerWindow(self) # make the main window - mostly to catch window close event...
        self.testMode = False # set to True to just display the scan signals
        self.win.show()
        self.win.setWindowTitle('Multiphoton Imager')
        self.win.resize(800, 600) # make the window big enough to use on a large monitor...

        self.w1 = QtGui.QSplitter()
        self.w1.setOrientation(QtCore.Qt.Horizontal)
        self.w2 = QtGui.QWidget()
        self.l2 = QtGui.QVBoxLayout()
        self.w2.setLayout(self.l2)
        self.currentStack = None
        self.currentStackLength = 0
        # we assume that you are not going to change the current camera or scope while running
        # ... not just yet anyway.
        # if this is to be allowed on a system, the change must be signaled to this class,
        # and we need to pick up the device in a routine that handles the change.
        self.camdev = self.manager.getDevice('Camera')
        self.cameraModule = self.manager.getModule('Camera')
        self.scopeDev = self.camdev.scopeDev
        
        self.scopeDev.sigObjectiveChanged.connect(self.objectiveUpdate)
        self.scopeDev.sigGlobalTransformChanged.connect(self.transformChanged)
        self.objectiveROImap = {} # this is a dict that we will populate with the name
        # of the objective and the associated ROI object .
        # That way, each objective has a scan region appopriate for it's magnification.
        
        self.regionCtrl = None
        self.currentRoi = None
        self.img = None # overlay image in the camera Window... 
        
        self.win.setCentralWidget(self.w1)
        self.w1.addWidget(self.w2)
        
        self.view = ImageView()
        self.w1.addWidget(self.view)
        #if 'defaultCamera' in self.dev.config:
        # self.dev.config['defaultCamera']
 #       if 'defaultLaser' in self.dev.config:
 #           defLaser = self.dev.config['defaultLaser']

        # create the user interface
        self.tree = PT.ParameterTree()
        self.l2.insertWidget(0, self.tree)
        self.buttonGrid = QtGui.QGridLayout()
        self.l2.insertLayout(1, self.buttonGrid)
        # action buttons:
        self.snap_button = QtGui.QPushButton('Snap')
        self.run_button = QtGui.QPushButton('Run')
        self.stop_button = QtGui.QPushButton('Stop')
        self.video_button = QtGui.QPushButton('Video')
        self.record_button = QtGui.QPushButton('Record Stack')
        self.record_button.setCheckable(True)
        self.video_button.setCheckable(True)
        self.cameraSnapBtn = QtGui.QPushButton('Camera Snap')
        self.hide_check = QtGui.QCheckBox('Hide Overlay')
        self.hide_check.setCheckState(False)
        self.hide_check.stateChanged.connect(self.hideOverlayImage)
        # control the alpha of the overlay image created from scanning the ROI
        self.alphaSlider = QtGui.QSlider()
        self.alphaSlider.setMaximum(100)
        self.alphaSlider.setSingleStep(2)
        self.alphaSlider.setProperty("value", 50)
        self.alphaSlider.setOrientation(QtCore.Qt.Horizontal)
        self.alphaSlider.setInvertedAppearance(False)
        self.alphaSlider.setInvertedControls(True)
        self.alphaSlider.setTickPosition(QtGui.QSlider.TicksBelow)            
        self.alphaSlider.valueChanged.connect(self.imageAlphaAdjust)        
        self.alphaSlider.setObjectName("alphaSlider")
        
        self.buttonGrid.addWidget(self.snap_button, 0, 0)
        self.buttonGrid.addWidget(self.run_button, 1, 0)
        self.buttonGrid.addWidget(self.stop_button, 2, 0)
        self.buttonGrid.addWidget(self.hide_check, 3, 0)
        self.buttonGrid.addWidget(self.video_button, 0, 1)
        self.buttonGrid.addWidget(self.record_button, 1, 1)
        self.buttonGrid.addWidget(self.cameraSnapBtn, 2, 1)
        self.buttonGrid.addWidget(self.alphaSlider, 3, 1)


        self.run_button.clicked.connect(self.PMT_Run)
        self.snap_button.clicked.connect(self.PMT_Snap)
        self.stop_button.clicked.connect(self.PMT_Stop)
        self.video_button.clicked.connect(self.toggleVideo)
        self.record_button.toggled.connect(self.recordToggled)
        self.cameraSnapBtn.clicked.connect(self.cameraSnap)
        
        self.param = PT.Parameter(name = 'param', children=[
            dict(name="Preset", type='list', value='', 
                 values=['', 'video-std', 'video-fast', 'StandardDef', 'HighDef']),
            dict(name='Store', type='bool', value=True),
            dict(name='Blank Screen', type='bool', value=True),
            dict(name='Sample Rate', type='float', value=1.0e6, suffix='Hz', dec = True, minStep=100., step=0.5, limits=[10e3, 5e6], siPrefix=True),
            dict(name='Downsample', type='int', value=1, limits=[1,None]),
            dict(name='Frame Time', type='float', readonly=True, value=0.0),
            dict(name='Pockels', type='float', value= 0.03, suffix='V', dec=True, minStep=1e-3, limits=[0, 1.5], step=0.1, siPrefix=True),
            dict(name='Objective', type='str', value='Unknown', readonly=True),
            dict(name='Image Width', type='int', value=500, readonly=True),
            dict(name='Image Height', type='int', value=500, readonly=True),
            dict(name='Pixel Size', type='float', value=0.5e-7, suffix='m', limits=[1.e-8, 1e-4], step=1e-7, siPrefix=True),
            dict(name='Width', type='float', value = 50.0e-6, suffix = 'm', limits=[0., 20.e-3], step=10e-6, siPrefix=True, readonly=True), #  True image width and height, in microns
            dict(name='Height', type = 'float', value = 50.0e-6, suffix='m', limits=[0., 20.e-3], step=10e-6, siPrefix=True, readonly=True),
            dict(name='Xpos', type='float', value = 0.0e-6, suffix = 'm', limits=[-50e-3, 50e-3], step=10e-6, siPrefix=True, readonly=True), #  True image width and height, in microns
            dict(name='Ypos', type = 'float', value = 0.0e-6, suffix='m', limits=[-50e-3, 50e-3], step=10e-6, siPrefix=True, readonly=True),
            dict(name='Y = X', type='bool', value=True),
            dict(name='XCenter', type='float', value=-0.3, suffix='V', dec=True, minStep=1e-3, limits=[-5, 5], step=0.5, siPrefix=True, readonly=True),
            dict(name='XSweep', type='float', value=1.0, suffix='V', dec=True, minStep=1e-3, limits=[-5, 5], step=0.5, siPrefix=True, readonly=True),
            dict(name='YCenter', type='float', value=-0.75, suffix='V', dec=True, minStep=1e-3, limits=[-5, 5], step=0.5, siPrefix=True, readonly=True),
            dict(name='YSweep', type='float', value=1.0, suffix='V', dec=True, minStep=1e-3, limits=[-5, 5], step=0.5, siPrefix=True, readonly=True),
            dict(name='Bidirectional', type='bool', value=True),
            dict(name='Decomb', type='bool', value=True, children=[
                dict(name='Auto', type='bool', value=True),
                dict(name='Shift', type='float', value=100e-6, suffix='s', step=10e-6, siPrefix=True),
            ]),
            
            dict(name='Overscan', type='float', value=5.0, suffix='%'),
            dict(name='Scope Device', type='interface', interfaceTypes=['microscope']),
            dict(name='Scanner Device', type='interface', interfaceTypes=['scanner']),
            dict(name='Laser Device', type='interface', interfaceTypes=['laser']),
            dict(name='Camera Module', type='interface', interfaceTypes=['cameraModule']),
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
        self.update() # also force update now to make sure all parameters are synchronized
        self.param.sigTreeStateChanged.connect(self.update)

        self.Manager = manager
        # insert an ROI into the camera image that corresponds to our scan area                
        self.objectiveUpdate() # force update of objective information and create appropriate ROI
# check the devices...        
        self.laserDev = self.manager.getDevice(self.param['Laser Device'])
        self.scannerDev = self.manager.getDevice(self.param['Scanner Device'])

    def quit(self):
       # print 'Imager quit WAS CALLED'
        for obj in self.objectiveROImap:
            try:
                self.cameraModule.window().removeItem(self.objectiveROImap[obj])
            except:
                pass
        Module.quit(self)

    def objectiveUpdate(self):
        """ Update the objective information and the associated ROI
        Used to report that the objective has changed in the parameter tree,
        and then (future) reposition the ROI that drives the image region.
        """
        self.param['Objective'] = self.scopeDev.currentObjective.name()
        if self.param['Objective'] not in self.objectiveROImap: # add the objective and an ROI
            self.objectiveROImap[self.param['Objective']] = self.createROI()
        for obj in self.objectiveROImap:
            if obj == self.param['Objective']:
                self.currentRoi = self.objectiveROImap[obj]
                self.currentRoi.show()
                self.updateFromROI() # do this now as well so that the parameter tree is correct. 

                continue
            self.hideROI(self.objectiveROImap[obj])
    
    def transformChanged(self):
        """
        Report that the tranform has changed, which might include the objective, or
        perhaps the stage position, etc. This needs to be obtained to re-align
        the scanner
        """
        pass

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
        brect = self.camdev.getBoundary().boundingRect()
        width = brect.width()
        height = brect.height()
        x = brect.x()+width*0.05
        y = brect.y()+height*0.05
        csize= [width*0.9,  height*0.9]
        cpos = [x, y]
        roiColor = self.getObjectiveColor(self.scopeDev.currentObjective) # pick up an objective color...
        roi = RegionCtrl(cpos, csize, roiColor) # Note that the position actually gets over ridden by the camera additem below..
        roi.setZValue(1000)
        self.cameraModule.window().addItem(roi)
        roi.setPos(cpos) # now is the time to do this. aaaaargh. Several hours later!!!
        roi.sigRegionChangeFinished.connect(self.updateFromROI)
        return roi
    
    def hideROI(self, roi):
        """ just make the current roi invisible... 
        although we probalby also want to hide the associated image ifit is present...
        """
        roi.hide()
    
    def updateFromROI(self):
        """ read the ROI rectangle width and height and repost
        in the parameter tree """
        state = self.currentRoi.getState()
        w, h = state['size']
        self.param['Width'] = w
        self.param['Height'] = h
        x, y = state['pos']
        self.param['Xpos'] = x
        self.param['Ypos'] = y
        self.param['Image Width'] = int(self.param['Width']/self.param['Pixel Size'])
        if self.param['Y = X']:
            self.param['YSweep'] = self.param['XSweep']
            self.param['Image Height'] = self.param['Image Width']
        else:
            self.param['Image Height'] = int(self.param['Height']/self.param['Pixel Size'])
            

    def update(self):
        try:
            self.param.sigTreeStateChanged.disconnect(self.update) # prevent recursion. 
        except:
            pass
        # check the devices first        
        self.laserDev = self.manager.getDevice(self.param['Laser Device'])
        self.scannerDev = self.manager.getDevice(self.param['Scanner Device'])
        # use the presets if they are engaged
        preset = self.param['Preset']
        if preset != '':
            self.param['Preset'] = ''
            global Presets
            for k,v in Presets[preset].iteritems():
                self.param[k] = v
        # calculate some values
        
        self.param['Image Width'] = int(self.param['Width']/self.param['Pixel Size'])
        if self.param['Y = X']:
            self.param['YSweep'] = self.param['XSweep']
            self.param['Image Height'] = self.param['Image Width']
        else:
            self.param['Image Height'] = int(self.param['Height']/self.param['Pixel Size'])

        self.param['Frame Time'] = self.param['Image Width']*self.param['Image Height']*self.param['Downsample']/self.param['Sample Rate']
        self.param['Z-Stack', 'Depth'] = self.param['Z-Stack', 'Step Size'] * (self.param['Z-Stack', 'Steps']-1)
        self.param['Timed', 'Duration'] = self.param['Timed', 'Interval'] * (self.param['Timed', 'N Intervals']-1)
        self.param.sigTreeStateChanged.connect(self.update) # restore updating

        
    def imageAlphaAdjust(self):
        if self.img is None:
            return
        alpha = self.alphaSlider.value()
        self.img.setImage(opacity=float(alpha/100.))
        
    def hideOverlayImage(self):
        if self.img is None:
            print 'img is none'
            return
        if self.hide_check.isChecked() is True:
            print 'hide'
            self.img.hide()
        else:
            print 'show'
            self.img.show()
        
    def PMT_Run(self):
        info = {}
        self.stopFlag = False
        if self.param['Z-Stack'] and self.param['Timed']:
            return
        if self.param['Z-Stack']: # moving in z for a focus stack
            info['2pImageType'] = 'Z-Stack'
            stage = self.manager.getDevice(self.param['Z-Stack', 'Stage'])
            images = []
            nSteps = self.param['Z-Stack', 'Steps']
            for i in range(nSteps):
                img = self.takeImage()[NP.newaxis, ...]
                if img is None:
                    break
                images.append(img)
                self.view.setImage(img)
                
                if i < nSteps-1:
                    ## speed 20 is quite slow; timeouts may occur if we go much slower than that..
                    stage.moveBy([0.0, 0.0, self.param['Z-Stack', 'Step Size']], speed=20, block=True)  
            imgData = NP.concatenate(images, axis=0)
        elif self.param['Timed']: # 
            info['2pImageType'] = 'Timed'
            self.param['Timed', 'Current Frame'] = 0
            images = []
            nSteps = self.param['Timed', 'N Intervals']
            for i in range(nSteps):
                if self.stopFlag:
                    break
                self.param['Timed', 'Current Frame'] = i
                img = self.takeImage()[NP.newaxis, ...]
                if img is None:
                   return
                images.append(img)
                self.view.setImage(img)
                if self.stopFlag:
                    break
                
                if i < nSteps-1:
                    time.sleep(self.param['Timed', 'Interval'])
            imgData = NP.concatenate(images, axis=0)

        else:
            info['2pImageType'] = 'Snap'
            imgData = self.takeImage()
            if imgData is None:
                return

        self.view.setImage(imgData)
        info = self.param.getValues()
        
        if self.param['Store']:
            dh = self.manager.getCurrentDir().writeFile(imgData, '2pImage.ma', info=info, autoIncrement=True)

    def PMT_Snap(self):
        """
        Take one image as a snap, regardless of whether a Z stack or a Timed acquisition is selected
        """
        imgData = self.takeImage()
        if self.testMode or imgData is None:
            return
        self.view.setImage(imgData)
        info = self.param.getValues()
        info['2pImageType'] = 'Snap'
        if self.param['Store']:
            info = self.param.getValues()
            info['2pImageType'] = 'Snap'
            #microscope = self.#info['microscope'] = self.param['Scope Device'].value()
            scope = self.Manager.getDevice(self.param['Scope Device'])
            #print dir(scope)
            #m = self.handle.info()['microscope']
           ### this needs to be fixed so that the microscope info is stored in the file - current NOT
           ### due to API change that I can't figure out.
           ###
           #info['microscope'] = scope.getState()
            if self.record_button.isChecked():
                mainfo = [
                    {'name': 'Frame'},
                    {'name': 'X'},
                    {'name': 'Y'},
                    info
                ]
                    
                data = MA.MetaArray(imgData[NP.newaxis, ...], info=mainfo, appendAxis='Frame')
                if self.currentStack is None:
                    fh = self.manager.getCurrentDir().writeFile(data, '2pStack.ma', info=info, autoIncrement=True)
                    self.currentStack = fh
                else:
                    data.write(self.currentStack.name(), appendAxis='Frame')
                self.currentStackLength += 1
                self.record_button.setText('Recording (%d)' % self.currentStackLength)
                
            else:
                self.manager.getCurrentDir().writeFile(imgData, '2pImage.ma', info=info, autoIncrement=True)

    def PMT_Stop(self):
        self.stopFlag = True
        
    def takeImage(self):
        """
        Take an image using the scanning system and PMT, and return with the data.
        """
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

    #return {'type': self.name, 'points': points, 'startTime': self.params['startTime'], 
        #        'endTime': self.params['endTime'], 'nScans': self.params['nScans'],
        #        'lineSpacing': self.params['linespacing']} 

        width = self.param['Width']
        if self.param['Y = X']:
            height = width
        else:
            height = self.param['Height']
        Xpos = self.param['Xpos']
        Ypos = self.param['Ypos']
        xCenter = self.param['Xpos']#-width/2.0
        yCenter = self.param['Ypos']#-height/2.0
        nPointsX = int(width/self.param['Pixel Size'])
        nPointsY = int(height/self.param['Pixel Size'])
        xScan = NP.linspace(0., width, nPointsX)
        xScan += xCenter
#        print 'w, h, xc, yc', width, height, xCenter, yCenter   
        sampleRate = self.param['Sample Rate']
        downsample = self.param['Downsample']
        overScan = self.param['Overscan']/100.     ## fraction of voltage scan range
        overScanWidth = width*overScan
#        print 'overscan: ', overScan
        #xScan *= overScan + 1.0 
        overScanPixels = int(nPointsX / 2. * overScan)
        pixelsPerRow = nPointsX + 2 * overScanPixels  ## make sure width is increased by an even number.
        samplesPerRow = pixelsPerRow * downsample
        samples = samplesPerRow * nPointsY
#        print 'nPointsX, Pixels per row, overScanPixels: ', nPointsX, pixelsPerRow, overScanPixels
        if not self.param['Bidirectional']:
            saw1 = NP.linspace(0., width+overScanWidth, num=samplesPerRow)
            saw1 += xCenter-overScanWidth/2.0
            xSaw = NP.tile(saw1, (1, nPointsY))[0,:]
        else:
            saw1 = NP.linspace(0., width+overScanWidth, num=samplesPerRow)
            saw1 += xCenter-overScanWidth/2.0
            rows = [saw1, saw1[::-1]] * int(nPointsY/2)
            if len(rows) < nPointsY:
                rows.append(saw1)
            xSaw = NP.concatenate(rows, axis=0)

        yvals = NP.linspace(0., height, num=nPointsY)
        yvals += yCenter
        yScan = NP.empty(samples)
        for y in range(nPointsY):
            yScan[y*samplesPerRow:(y+1)*samplesPerRow] = yvals[y]
        
        # now translate this scan into scanner voltage coordinates...

        x, y = self.scannerDev.mapToScanner(xSaw, yScan, self.laserDev.name())
#        print 'xS, yS: ', xScan[0:10], yScan[0:10]
#        print 'xl, yl: ', x[0:10], y[0:10]
        
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
        imgData = data['PMT']['Input'].view(NP.ndarray)
        imgData.shape = (nPointsY, pixelsPerRow)
        imgData = imgData.transpose()
        
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
        w = imgData.shape[0]
        h = imgData.shape[1]
        localPts = map(PG.Vector, [[0,0], [w,0], [0, h], [0,0,1]]) # w and h of data of image in pixels.
        globalPts = map(PG.Vector, [[Xpos, Ypos], [Xpos+width, Ypos], [Xpos, Ypos+height], [0, 0, 1]]) # actual values in global coordinates
        ##imgData.shape[0]*imgData.shape[1] # prog['points'] # sort of. - 
        m = PG.solve3DTransform(localPts, globalPts)
        m[:,2] = m[:,3]
        m[2] = m[3]
        m[2,2] = 1

        tr = QtGui.QTransform(*m[:3,:3].transpose().reshape(9))
        self.img.setTransform(tr)
# flip the PMT image upside down, since that is how it is... there is a mirror in the path
# (should this be a settable parameter? )

        #imgData = NP.flipud(imgData)
        imgData = NP.fliplr(imgData)
        
        if self.param['Show PMT V']:
            x=NP.linspace(0, samples/sampleRate, imgData.size)
            PG.plot(y=imgData.reshape(imgData.shape[0]*imgData.shape[1]), x=x)
        if self.param['Show Mirror V']:
            PG.plot(y=xScan, x=NP.linspace(0, samples/self.param['Sample Rate'], xScan.size))
        return imgData
            
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
        
        
    def toggleVideo(self, b):
        if b:
            self.startVideo()
            
    def startVideo(self):
        while True:
            img = self.takeImage()
            if img is None:
                return
            self.view.setImage(img, autoLevels=False)
            QtGui.QApplication.processEvents()
            if not self.video_button.isChecked():
                return
        
    def recordToggled(self, b):
        if not b:
            self.currentStack = None
            self.currentStackLength = 0
            self.param['Store'] = False
            self.record_button.setText('Record Stack')
        else:
            self.param['Store'] = True # turn off recording...
            
    def getScopeDevice(self):
        return self.manager.getDevice(self.param['Scope Device'])
            
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
        if self.param['Y = X']:
            height = width
        else:
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
              'PockelCell': {'Switch' : {'preset': self.param['Pockels']}},
              'PMT' : {
                  'Input': {'record': True},
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
        imgData = data['PMT']['Input'].view(NP.ndarray)
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
        