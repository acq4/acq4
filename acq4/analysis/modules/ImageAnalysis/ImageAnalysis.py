# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
from acq4.analysis.AnalysisModule import AnalysisModule
from collections import OrderedDict
import acq4.pyqtgraph as pg
from acq4.util.metaarray import MetaArray
import numpy as np

class ImageAnalysis(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        self.background = None
        
        #self.view = pg.GraphicsView()
        self.ctrl = Qt.QWidget()
        l = Qt.QGridLayout()
        self.ctrl.setLayout(l)
        self.ctrl.layout = l
        #self.loadBgBtn = Qt.QPushButton('load reference')
        #l.addWidget(self.loadBgBtn, 0, 0)
        self.addRoiBtn = Qt.QPushButton('add ROI')
        l.addWidget(self.addRoiBtn, 0, 0)
        s = Qt.QSpinBox()
        s.setMaximum(10)
        s.setMinimum(1)
        self.nsegSpin = s
        l.addWidget(s, 1, 0)
        self.rois = []
        self.data = []
        
        
        ## Setup basic GUI
        self._elements_ = OrderedDict([
            ('File Loader', {'type': 'fileInput', 'size': (200, 300), 'host': self, 'showFileTree': False}),
            ('Image',       {'type': 'imageView', 'pos': ('right', 'File Loader'), 'size': (800, 300)}),
            ('Time Plot',   {'type': 'plot', 'pos': ('bottom',), 'size': (800, 300)}),
            ('Trial Plot',  {'type': 'plot', 'pos': ('bottom', 'Time Plot'), 'size': (800, 300)}),
            ('Line Scan',   {'type': 'imageView', 'pos': ('right', 'Time Plot'), 'size': (800, 300)}),
            #('Data Table',  {'type': 'table', 'pos': ('below', 'Time Plot')}),
            ('Ctrl',        {'type': 'ctrl', 'pos': ('bottom', 'File Loader'), 'size': (200,30), 'object': self.ctrl}), 
        ])
        self.initializeElements()

        #self.traces = None
        self.plot = self.getElement('Time Plot', create=True)
        self.plot2 = self.getElement('Trial Plot', create=True)
        self.lr = pg.LinearRegionItem([0, 1])
        self.plot.addItem(self.lr)
        
        self.view = self.getElement('Image', create=True)
        
        ## Add a color scale
        ## removed for now--seems to be causing crashes :(
        #self.colorScale = pg.GradientLegend(self.plot1, (20, 150), (-10, -10))
        #self.plot1.scene().addItem(self.colorScale)
        
        ## Plots are updated when the selected region changes
        self.lr.sigRegionChanged.connect(self.updateAnalysis)
        self.addRoiBtn.clicked.connect(self.addRoi)
        self.view.sigProcessingChanged.connect(self.processData)
        #self.loadBgBtn.clicked.connect(self.loadBg)

    def addRoi(self):
        if self.nsegSpin.value() == 1:
            roi = pg.widgets.LineROI((0,0), (20, 20), 5)
        else:
            pts = [(i*10,i*10) for i in range(self.nsegSpin.value()+1)]
            roi = pg.widgets.MultiLineROI(pts, 5)
        self.rois.append(roi)
        self.view.addItem(roi)
        roi.sigRegionChanged.connect(self.roiChanged)
        
    def roiChanged(self, roi):
        if isinstance(roi, int):
            roi = self.currentRoi
        self.plot.clearPlots()
        c = 0
        lineScans = []
        for imgSet in self.data:
            data = roi.getArrayRegion(imgSet['procMean'], self.view.imageItem, axes=(1,2))
            m = data.mean(axis=1).mean(axis=1)
            lineScans.append(data.mean(axis=2))
            spacer = np.empty((lineScans[-1].shape[0], 1), dtype = lineScans[-1].dtype)
            spacer[:] = lineScans[-1].min()
            lineScans.append(spacer)
            
            data = roi.getArrayRegion(imgSet['procStd'], self.view.imageItem, axes=(1,2))
            s = data.mean(axis=1).mean(axis=1)
            
            self.plot.plot(m, pen=pg.hsvColor(c*0.2, 1.0, 1.0))
            self.plot.plot(m-s, pen=pg.hsvColor(c*0.2, 1.0, 0.4))
            self.plot.plot(m+s, pen=pg.hsvColor(c*0.2, 1.0, 0.4))
            
            c += 1
            
        lineScan = np.hstack(lineScans)
        self.getElement('Line Scan').setImage(lineScan)
        self.currentRoi = roi

    def processData(self):
        self.normData = []
        self.data = []
        for img in self.rawData:
            n = np.empty(img.shape, dtype=img.dtype)
            for i in range(img.shape[0]):
                n[i] = self.view.normalize(img[i])
            self.normData.append(n)
            
            imgSet = {'procMean': n.mean(axis=0), 'procStd': n.std(axis=0)}
            self.data.append(imgSet)
            
    def updateAnalysis(self):
        roi = self.currentRoi
        plot = self.getElement('Trial Plot')
        plot.clearPlots()
        c = 0
        for img in self.normData:
            #img = img.mean(axis=1)
            rgn = self.lr.getRegion()
            img = img[:, rgn[0]:rgn[1]].mean(axis=1)
            data = roi.getArrayRegion(img, self.view.imageItem, axes=(1,2))
            m = data.mean(axis=1).mean(axis=1)
            #data = roi.getArrayRegion(img, self.view.imageItem, axes=(1,2))
            #s = data.mean(axis=1).mean(axis=1)
            plot.plot(m, pen=pg.hsvColor(c*0.2, 1.0, 1.0))
            #self.plot.plot(m-s, pen=pg.hsvColor(c*0.2, 1.0, 0.4))
            #self.plot.plot(m+s, pen=pg.hsvColor(c*0.2, 1.0, 0.4))
            c += 1
            
            #if c == 1:
                #self.getElement('Line Scan').setImage(data.mean(axis=2))
        #if self.traces is None:
            #return
        #rgn = self.lr.getRegion()
        #data = self.traces['Time': rgn[0]:rgn[1]]
        #self.plot2.plot(data.mean(axis=1), clear=True)
        #self.plot2.plot(data.max(axis=1))
        #self.plot2.plot(data.min(axis=1))
        

    def loadFileRequested(self, dh):
        """Called by file loader when a file load is requested."""
        if len(dh) != 1:
            raise Exception("Can only load one file at a time.")
        dh = dh[0]
        
        if dh.isFile():
            self.background = dh.read()[np.newaxis,...].astype(float)
            self.background /= self.background.max()
            return
        
        
        self.plot.clearPlots()
        dirs = dh.subDirs()
        
        images = [[],[],[],[]]
        
        ## Iterate over sequence
        minFrames = None
        
        for d in dirs:
            d = dh[d]
            try:
                ind = d.info()[('Clamp1', 'amp')]
            except:
                print(d)
                print(d.info())
                raise
            img = d['Camera/frames.ma'].read()
            images[ind].append(img)
                
            if minFrames is None or img.shape[0] < minFrames:
                minFrames = img.shape[0]
                
                
        self.rawData = []
        self.data = []
        #print "len images: %d " % (len(images))
        while len(images) > 0:
            imgs = images.pop(0)
            img = np.concatenate([i[np.newaxis,:minFrames,...] for i in imgs], axis=0)
            self.rawData.append(img.astype(np.float32))
            #img /= self.background
            
        ## remove bleaching curve from first two axes
        ctrlMean = self.rawData[0].mean(axis=2).mean(axis=2)
        trialCurve = ctrlMean.mean(axis=1)[:,np.newaxis,np.newaxis,np.newaxis]
        timeCurve = ctrlMean.mean(axis=0)[np.newaxis,:,np.newaxis,np.newaxis]
        del ctrlMean
        for img in self.rawData:
            img /= trialCurve
            img /= timeCurve


        
        #for img in self.rawData:
            
            #m = img.mean(axis=0)
            #s = img.std(axis=0)
            #if self.background is not None:
                #m = m.astype(np.float32)
                #m /= self.background
                #s = s.astype(np.float32)
                #s /= self.background
            #imgSet = {'mean': m, 'std': s}
            #self.data.append(imgSet)
            #self.imgMeans.append(m)
            #self.imgStds.append(s)
        
        self.view.setImage(self.rawData[1].mean(axis=0))
        
        self.processData()
        
        ## set up the selection region correctly and prepare IV curves
        #if len(dirs) > 0:
            #end = cmd.xvals('Time')[-1]
            #self.lr.setRegion([end *0.5, end * 0.6])
            #self.updateAnalysis()
            #info = [
                #{'name': 'Command', 'units': cmd.axisUnits(-1), 'values': np.array(values)},
                #data.infoCopy('Time'), 
                #data.infoCopy(-1)]
            #self.traces = MetaArray(np.vstack(traces), info=info)
            
        return True
        


    
    
    