# -*- coding: utf-8 -*-

from lib.modules.Module import Module
from PyQt4 import QtGui, QtCore
from pyqtgraph.ImageView import ImageView
import pyqtgraph as PG
import InterfaceCombo
import pyqtgraph.parametertree as PT
import numpy as NP
import time
#import matplotlib.pylab as MP

class Black(QtGui.QWidget):
    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        brush = PG.mkBrush(0,0,0)
        p.fillRect(self.rect(), brush)
        p.end()
    
    
class ScreenBlanker:
    def __enter__(self):
        self.widgets = []
        d = QtGui.QApplication.desktop()
        #print "blank:", d.screenCount()
        for i in range(d.screenCount()):
            w = Black()
            self.widgets.append(w)
            sg = d.screenGeometry(i)
            #print "  ", sg.x(), sg.y()
            w.move(sg.x(), sg.y())
            w.showFullScreen()
        QtGui.QApplication.processEvents()
        
    def __exit__(self, *args):
        for w in self.widgets:
            #w.showNormal()
            w.hide()
        
        self.widgets = []
        
    


class Imager(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config) 
        self.win = QtGui.QMainWindow()
        self.testMode = True # set to True to just display the scan signals
        self.win.show()
        self.win.setWindowTitle('Multiphoton Imager')
        self.w1 = QtGui.QSplitter()
        #self.l1 = QtGui.QHBoxLayout()
        #self.w1.setLayout(self.l1)
        self.w1.setOrientation(QtCore.Qt.Horizontal)
        self.w2 = QtGui.QWidget()
        self.l2 = QtGui.QVBoxLayout()
        self.w2.setLayout(self.l2)
        
        self.win.setCentralWidget(self.w1)
        self.w1.addWidget(self.w2)
        
        self.view = ImageView()
        self.w1.addWidget(self.view)
        self.tree = PT.ParameterTree()
        self.l2.addWidget(self.tree)
        self.snap_button = QtGui.QPushButton('Snap')
        self.run_button = QtGui.QPushButton('Run')
        self.stop_button = QtGui.QPushButton('Stop')
        self.l2.addWidget(self.snap_button)
        self.l2.addWidget(self.run_button)
        self.l2.addWidget(self.stop_button)
        self.win.resize(800, 480)
        self.param = PT.Parameter(name = 'param', children=[
            dict(name='Sample Rate', type='float', value=100000., suffix='Hz', dec = True, minStep=100., step=0.5, limits=[10000., 1000000.], siPrefix=True),
            dict(name='Downsample', type='int', value=1, limits=[1,None]),
            dict(name='Image Size', type='list', value=256, limits=[32,64,128,256,512,1024,2048]),
            dict(name='Image Width', type='int', value=256),
            dict(name='Y = X', type='bool', value=True),
            dict(name='Image Height', type='int', value=256),
            dict(name='XCenter', type='float', value=0.25, suffix='V', dec=True, minStep=1e-3, limits=[-5, 5], step=0.5, siPrefix=True),
            dict(name='XSweep', type='float', value=0.5, suffix='V', dec=True, minStep=1e-3, limits=[-5, 5], step=0.5, siPrefix=True),
            dict(name='YCenter', type='float', value=-0.5, suffix='V', dec=True, minStep=1e-3, limits=[-5, 5], step=0.5, siPrefix=True),
            dict(name='YSweep', type='float', value=0.5, suffix='V', dec=True, minStep=1e-3, limits=[-5, 5], step=0.5, siPrefix=True),
            dict(name='Bidirectional', type='bool', value=True),
            dict(name='Overscan', type='float', value=2.0, suffix='%'),
            dict(name='Pockels', type='float', value= 0.03, suffix='V', dec=True, minStep=1e-3, limits=[0, 1.5], step=0.1, siPrefix=True),
            dict(name='Blank Screen', type='bool', value=True),
            dict(name='Show PMT V', type='bool', value=False),
            dict(name='Show Mirror V', type='bool', value=False),
            dict(name='Store', type='bool', value=True),
            dict(name='Frame Time', type='float', readonly=True, value=0.0),
            dict(name='Microscope', type='interface', interfaceTypes='microscope'),

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
            
        ])
        self.stopFlag = False
        self.tree.setParameters(self.param)
        self.param.sigTreeStateChanged.connect(self.update)
        self.param.param('Image Size').sigValueChanged.connect(self.updateXY)
        self.update()
        self.run_button.clicked.connect(self.PMT_Run)
        self.snap_button.clicked.connect(self.PMT_Snap)
        self.stop_button.clicked.connect(self.PMT_Stop)
        self.Manager = manager
        
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
                images.append(img)
                self.view.setImage(img)
                
                if i < nSteps-1:
                    ## speed 20 is quite slow; timeouts may occur if we go much slower than that..
                    stage.moveBy([0.0, 0.0, self.param['Z-Stack', 'Step Size']], speed=20, block=True)  
            imgData = NP.concatenate(images, axis=0)
        elif self.param['Timed']: # 
            
            self.param['Timed', 'Current Frame'] = 0
            self.images = []
            self.nSteps = self.param['Timed', 'N Intervals']
            self.nImages = 0
            self.TimedTimer = QtCore.QTimer()
            self.TimedTimer.timeout.connect(self.checkTimer)
            self.TimedTimer.start(0.0)
            return
        else:
            info['2pImageType'] = 'Snap'
            imgData = self.takeImage()

        self.view.setImage(imgData)
        info = self.param.getValues()
        
        if self.param['Store']:
            self.manager.getCurrentDir().writeFile(imgData, '2pImage.ma', info=info, autoIncrement=True)

    def checkTimer(self):
        if self.stopFlag:
            self.TimedTimer.stop()
            return
        self.param['Timed', 'Current Frame'] = self.nImages
        self.nImages += 1
        img = self.takeImage()[NP.newaxis, ...]
        self.images.append(img)
        self.view.setImage(img)
        
        self.nSteps -= 1
        if self.nSteps == 0:
            imgData = NP.concatenate(self.images, axis=0)
            self.TimedTimer.stop()
            self.view.setImage(imgData)
            info = self.param.getValues()           
            info['2pImageType'] = 'Timed'
            if self.param['Store']:
                self.manager.getCurrentDir().writeFile(imgData, '2pImage.ma', info=info, autoIncrement=True)  
                
        if self.nSteps > 0:
            self.TimedTimer.stop()
            self.TimedTimer.start(self.param['Timed', 'Interval']*1000.0)
            
        
    def PMT_Snap(self):
        """
        Take one image as a snap, regardless of whether a Z stack or a Timed acquisition is selected
        """
        imgData = self.takeImage()
        self.view.setImage(imgData)
        
        if self.param['Store']:
            scope = self.Manager.getDevice(self.param['Microscope'])
            scopePosition = scope.getPosition()
            objective = scope.getObjective()['name']
            info = self.param.getValues()
            info['scopePosition'] = scopePosition
            info['objective'] = objective
            info['2pImageType'] = 'Snap'
            dh = self.manager.getCurrentDir().writeFile(imgData, '2pImage.ma', info=info, autoIncrement=True)

    def PMT_Stop(self):
        self.stopFlag = True
        
    def takeImage(self):
        width = self.param['Image Width']
        if self.param['Y = X']:
            height = width
        else:
            height = self.param['Image Height']
        viewImagePts = height * width
        imagePts = height * width
        xscanV0 = self.param['XSweep']/2.0
        xcenter = self.param['XCenter']
        ycenter = self.param['YCenter']
        if self.param['Y = X']:
            yscanV = xscanV0
        else:
            yscanV = self.param['YSweep']/2.0
        overscan = self.param['Overscan'] # in percent of scan, in voltage
        xoverscan = xscanV0*overscan/100.0 # overscan voltage
        xscanV = xscanV0 + xoverscan
        downsample = self.param['Downsample']
        noverscan = int(width*overscan/100.0)
        nsamp = imagePts+2*noverscan*height
        samples = nsamp*downsample
        nscanwidth = downsample*(width+2*noverscan)
        if self.testMode:
            print '__________________________'
            print "imagePts: %d" % (imagePts)
            print "overscan: %f" % (overscan)
            print "noverscan: %d" % (noverscan)
            print "samples: %d" % (samples)
            print "downsample %d" % (downsample)
            print "xoverscan: %f" % (xoverscan)
        saw1 = NP.linspace(xcenter - xscanV, xcenter + xscanV, nscanwidth)
        if not self.param['Bidirectional']:
            xScan = NP.tile(saw1, (1, height))[0,:]
        else:
            scandir = 0
            xScan = NP.empty(samples)
            for y in range(height):
                if scandir == 0:
                    xScan[y*nscanwidth:(y+1)*nscanwidth] = saw1
                    scandir = 1
                elif scandir == 1:
                    xScan[y*nscanwidth:(y+1)*nscanwidth] = NP.flipud(saw1)
                    scandir = 0
        yvals = NP.linspace(ycenter-yscanV, ycenter+yscanV, height)
        yScan = NP.empty(samples)
        for y in range(height):
            yScan[y*nscanwidth:(y+1)*nscanwidth] = yvals[y]
        
#        if self.testMode:
#            MP.figure(1)
#            MP.plot(xScan, 'r-')
#            MP.plot(yScan, 'b-')
#            MP.show()
#            return
            
        cmd= {'protocol': {'duration': nsamp/self.param['Sample Rate']},
              'DAQ' : {'rate': self.param['Sample Rate'], 'numPts': nsamp, 'downsample':downsample}, 
              'Scanner-Raw': {
                  'XAxis' : {'command': xScan},
                  'YAxis' : {'command': yScan}
                  },
             # 'Laser-2P': {'pCell' : {'preset': self.param['Pockels']}},
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
                    time.sleep(0.01)
        else:
            task.execute(block = False)
            while not task.isDone():
                QtGui.QApplication.processEvents()
                time.sleep(0.01)

        data = task.getResult()
        imgData = data['PMT']['Input'].view(NP.ndarray)
#        print imgData.shape
#        print width*height
        imgTemp = NP.zeros((width * height))
        if noverscan > 0: # remove the overscan data
            for y in range(height): # first remove the overscan data from the array
#                if y < 10:
#                    print "y: %d y0: %d + width: %d into: %d, %d" % (y, y0, y0+width, y*width, (y+1)*width)
                imgTemp[y*width:(y+1)*width] = imgData[y*nscanwidth+noverscan:(y+1)*nscanwidth-noverscan]
            imgData = imgTemp # [width*height]
            imgTemp=[]
        if self.param['Bidirectional']:
            scandir = 0
            for y in range(height):
                if scandir == 0:
                    scandir = 1
                elif scandir == 1:
                    imgData[y*width:(y+1)*width] = imgData[(y+1)*width-1:(y*width)-1:-1]
                    scandir = 0            
        if self.param['Show PMT V']:
            PG.plot(y=imgData, x=NP.linspace(0,imagePts*downsample/self.param['Sample Rate'], 
            imagePts))
        if self.param['Show Mirror V']:
            PG.plot(y=xScan, x=NP.linspace(0,samples*downsample/self.param['Sample Rate'], 
            samples))


        imgData = imgData.reshape((width, height)).transpose()
        if self.testMode:
            print "size of imgData on return: ", imgData.shape
            print NP.max(NP.max(imgData))
            print NP.min(NP.min(imgData))
        return imgData
  
    def update(self):
        self.param['Frame Time'] = self.param['Image Width']*self.param['Image Height']*self.param['Downsample']/self.param['Sample Rate']
        self.param['Z-Stack', 'Depth'] = self.param['Z-Stack', 'Step Size'] * (self.param['Z-Stack', 'Steps']-1)
        self.param['Timed', 'Duration'] = self.param['Timed', 'Interval'] * (self.param['Timed', 'N Intervals']-1)
        if self.param['Y = X']:
            self.param['YSweep'] = self.param['XSweep']
            self.param['Image Height'] = self.param['Image Width']
            
    def updateXY(self):
        self.param['Image Height'] = self.param['Image Size']
        self.param['Image Width'] = self.param['Image Size']
        
            
        