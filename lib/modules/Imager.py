# -*- coding: utf-8 -*-

from lib.modules.Module import Module
from PyQt4 import QtGui, QtCore
from pyqtgraph import ImageView
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
        
    


class MPImager(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config) 
        self.win = QtGui.QMainWindow()
        self.testMode = False # set to True to just display the scan signals
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
            info['2pImageType'] = 'Timed'
            self.param['Timed', 'Current Frame'] = 0
            images = []
            nSteps = self.param['Timed', 'N Intervals']
            for i in range(nSteps):
                if self.stopFlag:
                    break
                self.param['Timed', 'Current Frame'] = i
                img = self.takeImage()[NP.newaxis, ...]
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

        self.view.setImage(imgData)
        info = self.param.getValues()
        
        if self.param['Store']:
            dh = self.manager.getCurrentDir().writeFile(imgData, '2pImage.ma', info=info, autoIncrement=True)

    def PMT_Snap(self):
        """
        Take one image as a snap, regardless of whether a Z stack or a Timed acquisition is selected
        """
        imgData = self.takeImage()
        if self.testMode:
            return
        self.view.setImage(imgData)
        info = self.param.getValues()
        info['2pImageType'] = 'Snap'
        if self.param['Store']:
            info = self.param.getValues()
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
        xscan = self.param['XSweep']/2.0
        xcenter = self.param['XCenter']
        ycenter = self.param['YCenter']
        if self.param['Y = X']:
            yscan = xscan
        else:
            yscan = self.param['YSweep']/2.0
        overscan = self.param['Overscan'] # in percent of scan, in voltage
        xoverscan = xscan*overscan/100.0 # overscan voltage
        downsample = self.param['Downsample']
        noverscan = int(width*xoverscan)
        nsamp = imagePts+2*noverscan*height
        samples = nsamp*downsample
        nscwidth = downsample*(width+2*noverscan)
#        if self.testMode:
#            print "imagePts: %d" % (imagePts)
#            print "noverscan: %d" % (noverscan)
#            print "samples: %d" % (samples)
#            print "downsample %d" % (downsample)
#            print "xoverscan: %f" % (xoverscan)
        if not self.param['Bidirectional']:
            saw1 = NP.linspace(xcenter - xscan, xcenter+xscan, width*downsample)
            if noverscan > 0:
                saw1 = NP.concatenate((saw1[0]*NP.ones(noverscan), saw1, saw1[-1]*NP.ones(noverscan)))
            xScan = NP.tile(saw1, (1, height))[0,:]
        else:
            saw1 = NP.linspace(xcenter - xscan, xcenter+xscan, width*downsample)
            if noverscan > 0:
                saw1 = NP.concatenate((saw1[0]*NP.ones(noverscan), saw1, saw1[-1]*NP.ones(noverscan)))
            scandir = 0
            xScan = NP.empty(samples)
            for y in range(height):
                if scandir == 0:
                    xScan[y*nscwidth:(y+1)*nscwidth] = saw1
                    scandir = 1
                elif scandir == 1:
                    xScan[y*nscwidth:(y+1)*nscwidth] = NP.flipud(saw1)
                    scandir = 0
        yvals = NP.linspace(ycenter-yscan, ycenter+yscan, height)
        yScan = NP.empty(samples)
        for y in range(height):
            yScan[y*nscwidth:(y+1)*nscwidth] = yvals[y]
        
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
                    time.sleep(0.1)
        else:
            task.execute(block = False)
            while not task.isDone():
                QtGui.QApplication.processEvents()
                time.sleep(0.1)

        data = task.getResult()
        imgData = data['PMT']['Input'].view(NP.ndarray)
#        print imgData.shape
#        print width*height
        imgTemp = NP.zeros((width * height))
        if noverscan > 0: # remove the overscan data
            actualWidth = 2*noverscan+width
            #print "actualWidth: %d" % (actualWidth)
            for y in range(height): # first remove the overscan data from the array
                y0 = y*actualWidth + noverscan # first point in non-overscanned dat for this line
#                if y < 10:
#                    print "y: %d y0: %d + width: %d into: %d, %d" % (y, y0, y0+width, y*width, (y+1)*width)
                imgTemp[y*width:(y+1)*width] = imgData[y0:y0+width]
            imgData = imgTemp # [width*height]
            imgTemp=[]
        if self.param['Bidirectional']:
            scandir = 0
            for y in range(height):
                if scandir == 0:
                    scandir = 1
                elif scandir == 1:
                    imgData[y*width:(y+1)*width] = NP.flipud(imgData[y*width:(y+1)*width])
                    scandir = 0            
        if self.param['Show PMT V']:
            PG.plot(y=imgData, x=NP.linspace(0,imagePts*downsample/self.param['Sample Rate'], 
            imagePts))
        if self.param['Show Mirror V']:
            PG.plot(y=xScan, x=NP.linspace(0,samples*downsample/self.param['Sample Rate'], 
            samples))


        imgData = imgData.reshape((width, height)).transpose()
        return imgData
  
    def update(self):
        self.param['Frame Time'] = self.param['Image Width']*self.param['Image Height']*self.param['Downsample']/self.param['Sample Rate']
        self.param['Z-Stack', 'Depth'] = self.param['Z-Stack', 'Step Size'] * (self.param['Z-Stack', 'Steps']-1)
        self.param['Timed', 'Duration'] = self.param['Timed', 'Interval'] * (self.param['Timed', 'N Intervals']-1)
        if self.param['Y = X']:
            self.param['YSweep'] = self.param['XSweep']
            self.param['Image Height'] = self.param['Image Width']
            
        