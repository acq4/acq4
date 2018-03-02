# -*- coding: utf-8 -*-
from __future__ import print_function
"""
Used for measuring illumination depth profiles from photobleached tissue.
"""
from acq4.util import Qt
from acq4.analysis.AnalysisModule import AnalysisModule
from collections import OrderedDict
import acq4.pyqtgraph as pg
from acq4.util.metaarray import MetaArray
import numpy as np
import acq4.util.functions as fn
#import acq4.pyqtgraph.ProgressDialog as ProgressDialog
import scipy.optimize

class DepthProfiler(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        self.ctrl = Qt.QWidget()
        l = Qt.QVBoxLayout()
        self.ctrl.setLayout(l)
        self.analyzeBtn = Qt.QPushButton('Analyze')
        self.analyzeBtn.clicked.connect(self.updateProfiles)
        self.saveBtn = Qt.QPushButton('Save')
        self.saveBtn.clicked.connect(self.save)
        l.addWidget(self.analyzeBtn)
        l.addWidget(self.saveBtn)
        
        
        
        # Setup basic GUI
        self._elements_ = OrderedDict([
            ('File Loader', {'type': 'fileInput', 'size': (100, 300), 'host': self, 'args': {'showFileTree': False}}),
            ('profiles', {'type': 'plot', 'pos': ('bottom', 'File Loader'), 'size': (300, 300)}),
            ('result table', {'type': 'table', 'pos': ('below', 'profiles')}),
            ('profile fits', {'type': 'plot', 'pos': ('below', 'result table'), 'size': (300, 300)}),
            #('view', {'type': 'viewBox', 'pos': ('right', 'File Loader'), 'size': (300,300), 'args': {'lockAspect': True, 'invertY': True}}),
            ('view', {'type': 'imageView', 'pos': ('right', 'File Loader'), 'size': (300,300)}),
            ('normalized', {'type': 'imageView', 'pos': ('right', 'view'), 'size': (300,300)}),
            ('total', {'type': 'plot', 'pos': ('right', 'profiles'), 'size': (300, 100)}),
            ('peak', {'type': 'plot', 'pos': ('bottom', 'total'), 'size': (300, 100)}),
            ('width', {'type': 'plot', 'pos': ('bottom', 'peak'), 'size': (300, 100)}),
            ('ctrl', {'type': 'ctrl', 'object': self.ctrl, 'pos': ('bottom', 'File Loader'), 'size': (100, 20)}),
        ])
        self.initializeElements()
        
        self.image = None
        #self.imageItem = pg.ImageItem()
        self.view = self.getElement('view', create=True)
        #view.addItem(self.imageItem)
        
        self.dataRgn = pg.RectROI(pos=(120,0), size=(100,100), pen=(0,255,0))
        self.dataRgn.addRotateHandle((1,0), (0.5, 0.5))
        self.bgRgn = pg.ROI(pos=(0,0), size=(100,100), pen=(255, 0,0), parent=self.dataRgn)
        self.bgRgn.addRotateHandle((1,0), (0.5, 0.5))
        self.bgRgn.addScaleHandle((1, 0.5), (0, 0.5))
        #self.bgRgn.setParentItem(self.dataRgn)
        self.view.addItem(self.bgRgn)
        self.view.addItem(self.dataRgn)
        
        self.dataRgn.sigRegionChanged.connect(self.updateImage)
        self.bgRgn.sigRegionChanged.connect(self.updateImage)
        #self.dataRgn.sigRegionChangeFinished.connect(self.updateProfiles)
        #self.bgRgn.sigRegionChangeFinished.connect(self.updateProfiles)
        

    def loadFileRequested(self, dh):
        """Called by file loader when a file load is requested."""
        if len(dh) != 1:
            raise Exception("Can only load one file at a time.")
        dh = dh[0]

        if not dh.isFile():
            return
            
        self.fileHandle = dh
        self.image = dh.read()
        self.view.setImage(self.image)
        self.px = dh.info().get('pixelSize', (1,1))
        
        try:
            f2 = dh.parent()[dh.shortName() + "_depthProfile.ma"]
            d2 = f2.read()
            state1 = d2._info[-1]['dataRegion']
            state2 = d2._info[-1]['backgroundRegion']
            self.dataRgn.setState(state1)
            self.bgRgn.setState(state2)
            self.showResults(d2)
        except KeyError:
            raise
            pass
        
        
    def updateImage(self):
        #print "Update image"
        #import traceback
        #traceback.print_stack()
        self.bgRgn.sigRegionChanged.disconnect(self.updateImage)
        try:
            self.bgRgn.setSize([self.bgRgn.size()[0], self.dataRgn.size()[1]+1])
            
            bg = self.bgRgn.getArrayRegion(self.image, self.view.imageItem)
            bg = bg.mean(axis=0)
            data = self.dataRgn.getArrayRegion(self.image, self.view.imageItem)
            data = data.astype(float) / bg[np.newaxis, :data.shape[1]]
            self.normData = data
            norm = self.getElement('normalized')
            norm.setImage(data)
        finally:
            self.bgRgn.sigRegionChanged.connect(self.updateImage)
        
        
    def updateProfiles(self):
        #if not self.analyzeBtn.isChecked():
            #return
        plots = self.getElement('profiles'), self.getElement('profile fits')
        for plot in plots:
            plot.clear()
            plot.setLabel('bottom', 'distance', units='m')
        width, height = self.normData.shape
        xVals = np.linspace(0, self.px[0]*width, width)
        fits = []
        
        def slopeGaussian(v, x):  ## gaussian + slope
            return fn.gaussian(v[:4], x) + v[4] * x
        def gaussError(v, x, y):  ## center-weighted error functionfor sloped gaussian
            err = abs(y-slopeGaussian(v, x))
            v2 = [2.0, v[1], v[2]*0.3, 1.0, 0.0]
            return err * slopeGaussian(v2, x)
        
        with pg.ProgressDialog("Processing..", 0, height-1, cancelText=None) as dlg:
            for i in range(height):
                row = self.normData[:, i]
                guess = [row.max()-row.min(), xVals[int(width/2)], self.px[0]*3, row.max(), 0.0]
                #fit = fn.fitGaussian(xVals=xVals, yVals=row, guess=guess)[0]
                #fit = fn.fit(slopeGaussian, xVals=xVals, yVals=row, guess=guess)[0]
                fit = scipy.optimize.leastsq(gaussError, guess, args=(xVals, row))[0] 
                fit[2] = abs(fit[2])
                dist = fit[1] / (self.px[0] * width / 2.)
                #print fit, dist
                ## sanity check on fit
                if abs(dist-1) > 0.5 or (0.5 < fit[3]/np.median(row) > 2.0):
                    #print "rejected:", fit, fit[3]/np.median(row), self.px[0]*width/2.
                    #fit = guess[:]
                    #fit[0] = 0
                    fit = [0,0,0,0,0]
                else:
                    # round 2: eliminate anomalous points and re-fit
                    fitCurve = slopeGaussian(fit, xVals)
                    diff = row - fitCurve
                    std = diff.std()
                    mask = abs(diff) < std * 1.5
                    x2 = xVals[mask]
                    y2 = row[mask]
                    fit = fn.fit(slopeGaussian, xVals=x2, yVals=y2, guess=fit)[0]
                fits.append(fit)
                dlg += 1
                if dlg.wasCanceled():
                    raise Exception("Processing canceled by user")
        
        for i in range(len(fits)):  ## plot in reverse order
            pen = pg.intColor(height-i, height*1.4)
            plots[0].plot(y=self.normData[:, -1-i], x=xVals, pen=pen)
            plots[1].plot(y=slopeGaussian(fits[-1-i], xVals), x=xVals, pen=pen)

        

        yVals = np.linspace(0, self.px[0]*height, height)
        arr = np.array(fits)
        info = [
                {'name': 'depth', 'units': 'm', 'values': yVals},
                {'name': 'fitParams', 'cols': [
                    {'name': 'Amplitude'},
                    {'name': 'X Offset'},
                    {'name': 'Sigma', 'units': 'm'},
                    {'name': 'Y Offset'},
                    {'name': 'Slope'},                    
                    ]},
                {
                    'sourceImage': self.fileHandle.name(),
                    'dataRegion': self.dataRgn.saveState(),
                    'backgroundRegion': self.bgRgn.saveState(),
                    'description': """
                    The source image was normalized for background fluorescence, then each row was fit to a sloped gaussian function:
                        v[0] * np.exp(-((x-v[1])**2) / (2 * v[2]**2)) + v[3] + v[4] * x
                    The fit parameters v[0..4] for each image row are stored in the columns of this data set.
                    """
                }
            ]
        #print info
        self.data = MetaArray(arr, info=info)
        self.showResults(self.data)
        
    def showResults(self, data):
        plots = self.getElement('total'), self.getElement('peak'), self.getElement('width')
        for p in plots:
            p.clear()
        amp = data['fitParams': 'Amplitude']
        sig = data['fitParams': 'Sigma']
        plots[0].plot(x=data.xvals('depth'), y=amp*sig)
        plots[0].setLabel('left', 'total')
        plots[1].plot(amp)
        plots[2].plot(sig)
        table = self.getElement('result table')
        table.setData(data)
        
    def save(self):
        fn = self.fileHandle.shortName() + "_depthProfile.ma"
        self.fileHandle.parent().writeFile(self.data, fn)
        
        
        