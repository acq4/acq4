# -*- coding: utf-8 -*-
from __future__ import with_statement
from acq4.devices.Camera import Camera
from PyQt4 import QtCore
import time, sys, traceback
#from metaarray import *
import acq4.util.ptime as ptime
from acq4.util.Mutex import Mutex, MutexLocker
from acq4.util.debug import *
import acq4.util.functions as fn
#from collections import OrderedDict
import numpy as np
import scipy
from collections import OrderedDict
import acq4.pyqtgraph as pg

class MockCamera(Camera):
    
    def __init__(self, *args, **kargs):
        self.camLock = Mutex(Mutex.Recursive)  ## Lock to protect access to camera
        self.ringSize = 100
        self.frameId = 0
        self.noise = np.random.normal(size=10000000, loc=100, scale=50)  ## pre-generate noise for use in images
        self.bgData = mandelbrot(w=1000, maxIter=60).astype(np.float32)
        self.background = None
        
        self.params = OrderedDict([
            ('triggerMode',     'Normal'),
            ('exposure',        0.001),
            #('binning',         (1,1)),
            #('region',          (0, 0, 512, 512)), 
            ('binningX',        1),
            ('binningY',        1),
            ('regionX',         0),
            ('regionY',         0),
            ('regionW',         512),
            ('regionH',         512),
            ('gain',            1.0),
            ('sensorSize',      (512, 512)),
            ('bitDepth',        16),
        ])
            
        self.paramRanges = OrderedDict([
            ('triggerMode',     (['Normal'], True, True, [])),
            ('exposure',        ((0.001, 10.), True, True, [])),
            #('binning',         ([range(1,10), range(1,10)], True, True, [])),
            #('region',          ([(0, 511), (0, 511), (1, 512), (1, 512)], True, True, [])),
            ('binningX',        (range(1,10), True, True, [])),
            ('binningY',        (range(1,10), True, True, [])),
            ('regionX',         ((0, 511), True, True, ['regionW'])),
            ('regionY',         ((0, 511), True, True, ['regionH'])),
            ('regionW',         ((1, 512), True, True, ['regionX'])),
            ('regionH',         ((1, 512), True, True, ['regionY'])),
            ('gain',            ((0.1, 10.0), True, True, [])),
            ('sensorSize',      (None, False, True, [])),
            ('bitDepth',        (None, False, True, [])),
        ])
        
        self.groupParams = {
            'binning':         ('binningX', 'binningY'),
            'region':          ('regionX', 'regionY', 'regionW', 'regionH')
        }
        
        sig = np.random.normal(size=(512, 512), loc=1.0, scale=0.3)
        sig = scipy.ndimage.gaussian_filter(sig, (3, 3))
        sig[20:40, 20:40] += 1
        sig[sig<0] = 0
        self.signal = sig
        
        Camera.__init__(self, *args, **kargs)  ## superclass will call setupCamera when it is ready.
        self.acqBuffer = None
        self.frameId = 0
        self.lastIndex = None
        self.lastFrameTime = None
        self.stopOk = False
        
        self.sigGlobalTransformChanged.connect(self.globalTransformChanged)
        
        ## generate list of mock cells
        cells = np.zeros(20, dtype=[('x', float), ('y', float), ('size', float), ('value', float), ('rate', float), ('intensity', float), ('decayTau', float)])
        cells['x'] = np.random.normal(size=cells.shape, scale=100e-6, loc=100e-6)
        cells['y'] = np.random.normal(size=cells.shape, scale=100e-6)
        cells['size'] = np.random.normal(size=cells.shape, scale=2e-6, loc=10e-6)
        cells['rate'] = np.random.lognormal(size=cells.shape, mean=0, sigma=1) * .3
        cells['intensity'] = np.random.uniform(size=cells.shape, low=1000, high=10000)
        cells['decayTau'] = np.random.uniform(size=cells.shape, low=15e-3, high=500e-3)
        self.cells = cells
        
        
    
    def setupCamera(self):
        pass
        #self.pvc = PVCDriver
        #cams = self.pvc.listCameras()
        #print "Cameras:", cams
        #if len(cams) < 1:
            #raise Exception('No cameras found by pvcam driver')
        
        #if self.camConfig['serial'] is None:  ## Just pick first camera
            #ind = 0
        #else:
            #if self.camConfig['serial'] in cams:
                #ind = cams.index(self.camConfig['serial'])
            #else:
                #raise Exception('Can not find pvcam camera "%s"' % str(self.camConfig['serial']))
        #print "Selected camera:", cams[ind]
        #self.cam = self.pvc.getCamera(cams[ind])
        
    def globalTransformChanged(self):
        self.background = None
    
    def startCamera(self):
        self.cameraStarted = True
        self.lastFrameTime = ptime.time()
        ### Attempt camera start. If the driver complains that it can not allocate memory, reduce the ring size until it works. (Ridiculous driver bug)
        #printRingSize = False
        #self.stopOk = False
        #while True:
            #try:
                #with self.camLock:
                    #self.cam.setParam('ringSize', self.ringSize)
                    #self.acqBuffer = self.cam.start()
                #break
            #except Exception, e:
                #if len(e.args) == 2 and e.args[1] == 15:
                    #printRingSize = True
                    #self.ringSize = int(self.ringSize * 0.9)
                    #if self.ringSize < 2:
                        #raise Exception("Will not reduce camera ring size < 2")
                #else:
                    #raise
        #if printRingSize:
            #print "Reduced camera ring size to %d" % self.ringSize
        
    def stopCamera(self):
        self.cameraStopped = True
        #with self.camLock:
            #if not self.stopOk:      ### If no frames have arrived since starting the camera, then 
                                #### it is not safe to stop the camera immediately--this can hang the (lame) driver
                #time.sleep(1.0)
            #self.cam.stop()
        
    def getNoise(self, shape):
        n = shape[0] * shape[1]
        s = np.random.randint(len(self.noise)-n)
        d = self.noise[s:s+n]
        d.shape = shape
        return d.copy()
        
    def getBackground(self):
        if self.background is None:
            w,h = self.params['sensorSize']
            
            tr = self.globalTransform()
            tr = pg.SRTTransform(tr)
            m = QtGui.QTransform()
            m.scale(2e6, 2e6)
            tr = tr * m
            
            origin = tr.map(pg.Point(0,0))
            x = (tr.map(pg.Point(1,0)) - origin)
            y = (tr.map(pg.Point(0,1)) - origin)
            origin = np.array([origin.x(), origin.y()])
            x = np.array([x.x(), x.y()])
            y = np.array([y.x(), y.y()])
            
            ## render fractal on the fly
            #m = pg.SRTTransform(tr).matrix()
            #tr = np.array([[1,0,0],[0,1,0],[0,0,1]])
            #xy = xy = np.ones((3,w,h))
            #xy[:2] = np.mgrid[0:w, 0:h]
            #xy = np.dot(xy.transpose(1,2,0), m[:,:2])
            #xy = xy.transpose(2,0,1)
            #self.background = mandelbrot(xy)
            
            ## slice fractal from pre-rendered data
            vectors = (x,y)
            self.background = pg.affineSlice(self.bgData, (w,h), origin, vectors, (0,1), order=1)
            
        return self.background
        
    def pixelVectors(self):
        tr = self.globalTransform()
        origin = tr.map(pg.Point(0,0))
        x = (tr.map(pg.Point(1,0)) - origin)
        y = (tr.map(pg.Point(0,1)) - origin)
        origin = np.array([origin.x(), origin.y()])
        x = np.array([x.x(), x.y()])
        y = np.array([y.x(), y.y()])
        
        return x,y
        
    def newFrames(self):
        """Return a list of all frames acquired since the last call to newFrames."""
        now = ptime.time()
        
        dt = now - self.lastFrameTime
        exp = self.getParam('exposure')
        region = self.getParam('region') 
        bg = self.getBackground()[region[0]:region[0]+region[2], region[1]:region[1]+region[3]]
        
        ## update cells
        spikes = np.random.poisson(max(dt, 0.4) * self.cells['rate'])
        self.cells['value'] *= np.exp(-dt / self.cells['decayTau'])
        self.cells['value'] = np.clip(self.cells['value'] + spikes * 0.2, 0, 1)
        
        shape = region[2:]
        bin = self.getParam('binning')
        nf = int(dt / (exp+(40e-3/(bin[0]*bin[1]))))
        if nf > 0:
            self.lastFrameTime = now
            #data = np.random.normal(size=(shape[0], shape[1]), loc=100, scale=50)
            data = self.getNoise(shape)
            data[data<0] = 0
            
            #sig = self.signal[region[0]:region[0]+region[2], region[1]:region[1]+region[3]]
            data += bg * (exp*1000)
            
            ## draw cells
            px = (self.pixelVectors()[0]**2).sum() ** 0.5
            
            ## Generate transform that maps grom global coordinates to image coordinates
            cameraTr = pg.SRTTransform3D(self.inverseGlobalTransform())
            frameTr = self.makeFrameTransform(region, [1, 1]).inverted()[0] # note we use binning=(1,1) here because the image is downsampled later.
            tr = pg.SRTTransform(frameTr * cameraTr)
            
            for cell in self.cells:
                w = cell['size'] / px
                pos = pg.Point(cell['x'], cell['y'])
                imgPos = tr.map(pos)
                start = (int(imgPos.x()), int(imgPos.y()))
                stop = (start[0]+w, start[1]+w)
                val = cell['intensity'] * cell['value'] * self.getParam('exposure')
                data[max(0,start[0]):max(0,stop[0]), max(0,start[1]):max(0,stop[1])] += val
            
            
            data = fn.downsample(data, bin[0], axis=0)
            data = fn.downsample(data, bin[1], axis=1)
            data = data.astype(np.uint16)
            
            
            
            
            self.frameId += 1
            frames = []
            for i in range(nf):
                frames.append({'data': data, 'time': now, 'id': self.frameId})
            return frames
            
        else:
            return []
        
        
        
        #with self.camLock:
            #index = self.cam.lastFrame()
        #now = ptime.time()
        #if self.lastFrameTime is None:
            #self.lastFrameTime = now
            
        #if index is None:  ## no frames available yet
            #return []
        
        #if index == self.lastIndex:  ## no new frames since last check
            #return []
        
        #self.stopOk = True
        
        ### Determine how many new frames have arrived since last check
        #if self.lastIndex is not None:
            #diff = (index - self.lastIndex) % self.ringSize
            #if diff > (self.ringSize / 2):
                #print "Image acquisition buffer is at least half full (possible dropped frames)"
        #else:
            #self.lastIndex = index-1
            #diff = 1
    
        #dt = (now - self.lastFrameTime) / diff
        #frames = []
        #for i in range(diff):
            #fInd = (i+self.lastIndex+1) % self.ringSize
            #frame = {}
            #frame['time'] = self.lastFrameTime + (dt * (i+1))
            #frame['id'] = self.frameId
            #frame['data'] = self.acqBuffer[fInd].copy()
            ##print frame['data']
            #frames.append(frame)
            #self.frameId += 1
                
        #self.lastFrame = frame
        #self.lastFrameTime = now
        #self.lastIndex = index
        #return frames
        
                
    def quit(self):
        pass
        #Camera.quit(self)
        #self.pvc.quit()
        
    def listParams(self, params=None):
        """List properties of specified parameters, or of all parameters if None"""
        if params is None:
            return self.paramRanges
        else:
            if isinstance(params, basestring):
                return self.paramRanges[params]
                
            out = OrderedDict()
            for k in params:
                out[k] = self.paramRanges[k]
            return out
        

    def setParams(self, params, autoRestart=True, autoCorrect=True):
        #print "PVCam: setParams", params
        #with self.camLock:
            #if 'ringSize' in params:
                #self.ringSize = params['ringSize']
            #newVals, restart = self.cam.setParams(params, autoCorrect=autoCorrect)
        ##restart = True  ## pretty much _always_ need a restart with these cameras.
        
        #self.emit(QtCore.SIGNAL('paramsChanged'), newVals)
        dp = []
        ap = {}
        for k in params:
            if k in self.groupParams:
                ap.update(dict(zip(self.groupParams[k], params[k])))
                dp.append(k)
        params.update(ap)
        for k in dp:
            del params[k]
        
        #if 'region' in params:
            #params['regionX'], params['regionY'], params['regionW'], params['regionH'] = params['region']
            #del params['region']
        #if 'binning' in params:
            #params['binningX'], params['binningY'] = params['binning']
            #del params['binning']
        
        self.params.update(params)
        newVals = params
        restart = True
        if autoRestart and restart:
            self.restart()
        self.sigParamsChanged.emit(newVals)
        return (newVals, restart)

    def getParams(self, params=None):
        if params is None:
            params = self.listParams().keys()
        #with self.camLock:
            #return self.cam.getParams(params)
        vals = OrderedDict()
        for k in params:
            if k in self.groupParams:
                vals[k] = self.getParams(self.groupParams[k]).values()
            #if k == 'region':
                #vals[k] = self.getParams(['regionX', 'regionY', 'regionW', 'regionH']).values()
            #elif k == 'binning':
                #vals[k] = self.getParams(['binningX', 'binningY']).values()
            else:
                vals[k] = self.params[k]
        return vals


    def setParam(self, param, value, autoRestart=True, autoCorrect=True):
        return self.setParams({param: value}, autoRestart=autoRestart, autoCorrect=autoCorrect)
        #with self.camLock:
            #newVal, restart = self.cam.setParam(param, value, autoCorrect=autoCorrect)
        ##restart = True  ## pretty much _always_ need a restart with these cameras.
        
        #if autoRestart and restart:
            #self.restart()
        #self.emit(QtCore.SIGNAL('paramsChanged'), {param: newVal})
        #return (newVal, restart)

    def getParam(self, param):
        #with self.camLock:
            #return self.cam.getParam(param)
        return self.getParams([param])[param]


def mandelbrot(w=500, h=None, maxIter=20, xRange=(-2.0, 1.0), yRange=(-1.2, 1.2)):
    x0,x1 = xRange
    y0,y1 = yRange
    if h is None:
        h = int(w * (y1-y0)/(x1-x0))
        
    x = np.linspace(x0, x1, w).reshape(w,1)
    y = np.linspace(y0, y1, h).reshape(1,h)
    
    ## speed up with a clever initial mask:
    x14 = x-0.25
    y2 = y**2
    q = (x14)**2 + y2
    mask = q * (q + x14) > 0.25 * y2
    mask &= (x+1)**2 + y2 > 1/16.
    mask &= x > -2
    mask &= x < 0.7
    mask &= y > -1.2
    mask &= y < 1.2

    img = np.zeros((w,h), dtype=int)
    xInd, yInd = np.mgrid[0:w, 0:h]
    x = x.reshape(w)[xInd]
    y = y.reshape(h)[yInd]
    z0 = np.empty((w,h), dtype=np.complex64)
    z0.real = x
    z0.imag = y
    z = z0.copy()

    for i in xrange(maxIter):
        z = z[mask]
        z0 = z0[mask]
        xInd = xInd[mask]
        yInd = yInd[mask]
        z *= z
        z += z0
        mask = np.abs(z) < 2.
        img[xInd[mask], yInd[mask]] = i % (maxIter-1)
        
    return img
