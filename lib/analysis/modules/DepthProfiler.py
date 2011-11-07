# -*- coding: utf-8 -*-
"""
Used for measuring illumination depth profiles from photobleached tissue.
"""
from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
from collections import OrderedDict
import pyqtgraph as pg
#from metaarray import MetaArray
import numpy as np
import functions as fn
import ProgressDialog

class DepthProfiler(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        self.analyzeBtn = QtGui.QPushButton('Analyze')
        self.analyzeBtn.setCheckable(True)
        self.analyzeBtn.clicked.connect(self.updateProfiles)
        
        # Setup basic GUI
        self._elements_ = OrderedDict([
            ('File Loader', {'type': 'fileInput', 'size': (100, 300), 'host': self, 'args': {'showFileTree': False}}),
            ('profiles', {'type': 'plot', 'pos': ('bottom', 'File Loader'), 'size': (300, 300)}),
            ('result table', {'type': 'table', 'pos': ('below', 'profiles')}),
            ('profile fits', {'type': 'plot', 'pos': ('below', 'result table'), 'size': (300, 300)}),
            ('view', {'type': 'viewBox', 'pos': ('right', 'File Loader'), 'size': (300,300), 'args': {'lockAspect': True, 'invertY': True}}),
            ('normalized', {'type': 'imageView', 'pos': ('right', 'view'), 'size': (300,300)}),
            ('total', {'type': 'plot', 'pos': ('right', 'profiles'), 'size': (300, 100)}),
            ('peak', {'type': 'plot', 'pos': ('bottom', 'total'), 'size': (300, 100)}),
            ('width', {'type': 'plot', 'pos': ('bottom', 'peak'), 'size': (300, 100)}),
            ('ctrl', {'type': 'ctrl', 'object': self.analyzeBtn, 'pos': ('bottom', 'File Loader'), 'size': (100, 20)}),
        ])
        self.initializeElements()
        
        self.image = None
        self.imageItem = pg.ImageItem()
        view = self.getElement('view', create=True).centralWidget
        view.addItem(self.imageItem)
        
        self.dataRgn = pg.widgets.RectROI(pos=(120,0), size=(100,100), pen=(0,255,0))
        self.dataRgn.addRotateHandle((1,0), (0.5, 0.5))
        self.bgRgn = pg.widgets.ROI(pos=(0,0), size=(100,100), pen=(255, 0,0), parent=self.dataRgn)
        self.bgRgn.addRotateHandle((1,0), (0.5, 0.5))
        self.bgRgn.addScaleHandle((1, 0.5), (0, 0.5))
        #self.bgRgn.setParentItem(self.dataRgn)
        view.addItem(self.bgRgn)
        view.addItem(self.dataRgn)
        
        self.dataRgn.sigRegionChanged.connect(self.updateImage)
        self.bgRgn.sigRegionChanged.connect(self.updateImage)
        self.dataRgn.sigRegionChangeFinished.connect(self.updateProfiles)
        self.bgRgn.sigRegionChangeFinished.connect(self.updateProfiles)
        

    def loadFileRequested(self, dh):
        """Called by file loader when a file load is requested."""
        if len(dh) != 1:
            raise Exception("Can only load one file at a time.")
        dh = dh[0]

        if not dh.isFile():
            return
            
        
        self.image = dh.read()
        self.imageItem.setImage(self.image)
        self.px = dh.info()['pixelSize']
        
    def updateImage(self):
        self.bgRgn.setSize([self.bgRgn.size()[0], self.dataRgn.size()[1]+1])
        
        bg = self.bgRgn.getArrayRegion(self.image, self.imageItem)
        bg = bg.mean(axis=0)
        data = self.dataRgn.getArrayRegion(self.image, self.imageItem)
        data = data.astype(float) / bg[np.newaxis, :data.shape[1]]
        self.normData = data
        norm = self.getElement('normalized')
        norm.setImage(data)
        
        
    def updateProfiles(self):
        if not self.analyzeBtn.isChecked():
            return
        plots = self.getElement('profiles'), self.getElement('profile fits')
        for plot in plots:
            plot.clear()
            plot.setLabel('bottom', 'distance', units='m')
        width, height = self.normData.shape
        xVals = np.linspace(0, self.px[0]*width, width)
        fits = []
        
        def slopeGaussian(v, x):  ## gaussian + slope
            return fn.gaussian(v[:4], x) + v[4] * x
        
        with ProgressDialog.ProgressDialog("Processing..", 0, height-1, cancelText=None) as dlg:
            for i in range(height):
                row = self.normData[:, i]
                guess = [-1.0, xVals[int(width/2)], self.px[0]*10, 1.0, 0.0]
                #fit = fn.fitGaussian(xVals=xVals, yVals=row, guess=guess)[0]
                fit = fn.fit(slopeGaussian, xVals=xVals, yVals=row, guess=guess)[0]
                fit[2] = abs(fit[2])
                dist = fit[1] / (self.px[0] * width / 2.)
                #print fit, dist
                ## sanity check on fit
                if dist-1 > 0.5 or fit[3] > 2.0:
                    fit = guess[:]
                    fit[0] = 0
                else:
                    # round 2: eliminate anomalous points and re-fit
                    fitCurve = slopeGaussian(fit, xVals)
                    diff = row - fitCurve
                    std = diff.std()
                    mask = abs(diff) < std * 1.5
                    x2 = xVals[mask]
                    y2 = row[mask]
                    print (1-mask).sum()
                    fit = fn.fit(slopeGaussian, xVals=x2, yVals=y2, guess=fit)[0]
                fits.append(fit)
                dlg += 1
                if dlg.wasCanceled():
                    raise Exception("Processing canceled by user")
        
        for i in range(len(fits)):  ## plot in reverse order
            pen = pg.intColor(height-i, height*1.4)
            plots[0].plot(self.normData[:, -1-i], pen=pen)
            plots[1].plot(slopeGaussian(fits[-1-i], xVals), pen=pen)
        
        yVals = np.linspace(0, self.px[0]*height, height)
        plots = self.getElement('total'), self.getElement('peak'), self.getElement('width')
        for p in plots:
            p.clear()
            p.setLabel('bottom', 'depth', units='m')
        plots[0].plot(x=yVals, y=[f[0]*f[2] for f in fits])
        plots[0].setLabel('left', 'total')
        plots[1].plot(x=yVals, y=[f[0] for f in fits])
        plots[1].setLabel('left', 'amplitude')
        plots[2].plot(x=yVals, y=[f[2] for f in fits])
        plots[2].setLabel('left', 'width', units='m')
        table = self.getElement('result table')
        table.setData(np.array(fits))
        
        