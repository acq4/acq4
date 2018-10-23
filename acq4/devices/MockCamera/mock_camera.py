# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import with_statement
from acq4.devices.Camera import Camera, CameraTask
from acq4.util import Qt
import six
from six.moves import range
import time, sys, traceback
import acq4.util.ptime as ptime
from acq4.util.Mutex import Mutex
from acq4.util.debug import *
import acq4.util.functions as fn
import numpy as np
import scipy
from collections import OrderedDict
import acq4.pyqtgraph as pg


class MockCamera(Camera):
    
    def __init__(self, manager, config, name):
        self.camLock = Mutex(Mutex.Recursive)  ## Lock to protect access to camera
        self.ringSize = 100
        self.frameId = 0
        self.noise = np.random.normal(size=10000000, loc=100, scale=10)  ## pre-generate noise for use in images
        
        if 'images' in config:
            self.bgData = {}
            self.bgInfo = {}
            for obj, filename in config['images'].items():
                file = manager.fileHandle(filename)
                ma = file.read()
                self.bgData[obj] = ma.asarray()
                self.bgInfo[obj] = file.info().deepcopy()
                self.bgInfo[obj]['depths'] = ma.xvals(0)
        else:
            self.bgData = mandelbrot(w=4000, maxIter=60).astype(np.float32)
            self.bgInfo = None
        
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
            ('triggerMode',     (['Normal', 'TriggerStart'], True, True, [])),
            ('exposure',        ((0.001, 10.), True, True, [])),
            #('binning',         ([range(1,10), range(1,10)], True, True, [])),
            #('region',          ([(0, 511), (0, 511), (1, 512), (1, 512)], True, True, [])),
            ('binningX',        (list(range(1,10)), True, True, [])),
            ('binningY',        (list(range(1,10)), True, True, [])),
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
        
        Camera.__init__(self, manager, config, name)  ## superclass will call setupCamera when it is ready.
        self.acqBuffer = None
        self.frameId = 0
        self.lastIndex = None
        self.lastFrameTime = None
        self.stopOk = False
        
        self.sigGlobalTransformChanged.connect(self.globalTransformChanged)
        
        ## generate list of mock cells
        cells = np.zeros(20, dtype=[('x', float), ('y', float), ('size', float), ('value', float), ('rate', float), ('intensity', float), ('decayTau', float)])
        cells['x'] = np.random.normal(size=cells.shape, scale=100e-6, loc=-1.5e-3)
        cells['y'] = np.random.normal(size=cells.shape, scale=100e-6, loc=4.4e-3)
        cells['size'] = np.random.normal(size=cells.shape, scale=2e-6, loc=10e-6)
        cells['rate'] = np.random.lognormal(size=cells.shape, mean=0, sigma=1) * 1.0
        cells['intensity'] = np.random.uniform(size=cells.shape, low=1000, high=10000)
        cells['decayTau'] = np.random.uniform(size=cells.shape, low=15e-3, high=500e-3)
        self.cells = cells
        
    def setupCamera(self):
        pass
        
    def globalTransformChanged(self):
        self.background = None
    
    def startCamera(self):
        self.cameraStarted = True
        self.lastFrameTime = ptime.time()
        
    def stopCamera(self):
        self.cameraStopped = True
        
    def getNoise(self, shape):
        n = shape[0] * shape[1]
        s = np.random.randint(len(self.noise)-n)
        d = self.noise[s:s+n]
        d.shape = shape
        return np.abs(d)
        
    def getBackground(self):
        if self.background is None:
            w,h = self.params['sensorSize']
            tr = self.globalTransform()
            
            if isinstance(self.bgData, dict):
                # select data based on objective
                obj = self.getObjective()
                data = self.bgData[obj]
                info = self.bgInfo[obj]
                px = info['pixelSize']
                pz = info['depths'][1] - info['depths'][0]
                
                m = Qt.QMatrix4x4()
                pos = info['transform']['pos']
                m.scale(1/px[0], 1/px[1], 1/pz)
                m.translate(-pos[0], -pos[1], -info['depths'][0])
                
                tr2 = m * tr
                origin = tr2.map(pg.Vector(0, 0, 0))
                #print(origin)
                origin = [int(origin.x()), int(origin.y()), origin.z()]
                
                ## slice data
                camRect = Qt.QRect(origin[0], origin[1], w, h)
                dataRect = Qt.QRect(0, 0, data.shape[1], data.shape[2])
                overlap = camRect.intersected(dataRect)
                tl = overlap.topLeft() - camRect.topLeft()
                
                z = origin[2]
                z1 = np.floor(z)
                z2 = np.ceil(z)
                s = (z-z1) / (z2-z1)
                z1 = int(np.clip(z1, 0, data.shape[0]-1))
                z2 = int(np.clip(z2, 0, data.shape[0]-1))
                src1 = data[z1, overlap.left():overlap.left()+overlap.width(), overlap.top():overlap.top()+overlap.height()]
                src2 = data[z2, overlap.left():overlap.left()+overlap.width(), overlap.top():overlap.top()+overlap.height()]
                src = src1 * (1-s) + src2 * s
                
                bg = np.empty((w, h), dtype=data.dtype)
                bg[:] = 100
                bg[tl.x():tl.x()+overlap.width(), tl.y():tl.y()+overlap.height()] = src
                self.background = bg
                #vectors = ([1, 0, 0], [0, 1, 0])
                #self.background = pg.affineSlice(data, (w,h), origin, vectors, (1, 2, 0), order=1)
            else:
                tr = pg.SRTTransform(tr)
                m = Qt.QTransform()
                
                m.scale(3e6, 3e6)
                m.translate(0.0005, 0.0005)
                tr = tr * m
                
                origin = tr.map(pg.Point(0,0))
                x = (tr.map(pg.Point(1,0)) - origin)
                y = (tr.map(pg.Point(0,1)) - origin)
                origin = np.array([origin.x(), origin.y()])
                x = np.array([x.x(), x.y()])
                y = np.array([y.x(), y.y()])
                
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
        prof = pg.debug.Profiler(disabled=True)
        
        now = ptime.time()
        dt = now - self.lastFrameTime
        exp = self.getParam('exposure')
        bin = self.getParam('binning')
        fps = 1.0 / (exp+(40e-3/(bin[0]*bin[1])))
        nf = int(dt * fps)
        if nf == 0:
            return []
        self.lastFrameTime = now + exp
        
        prof()
        region = self.getParam('region') 
        prof()
        bg = self.getBackground()[region[0]:region[0]+region[2], region[1]:region[1]+region[3]]
        prof()
        
        # Start with noise
        shape = region[2:]
        data = self.getNoise(shape)
        #data = np.zeros(shape, dtype=float)
        prof()
        
        # Add specimen
        data += bg * (exp * 10)
        prof()
        
        ## update cells
        spikes = np.random.poisson(min(dt, 0.4) * self.cells['rate'])
        self.cells['value'] *= np.exp(-dt / self.cells['decayTau'])
        self.cells['value'] = np.clip(self.cells['value'] + spikes * 0.2, 0, 1)
        data[data<0] = 0
        
        # draw cells
        px = (self.pixelVectors()[0]**2).sum() ** 0.5
        
        # Generate transform that maps grom global coordinates to image coordinates
        cameraTr = pg.SRTTransform3D(self.inverseGlobalTransform())
        # note we use binning=(1,1) here because the image is downsampled later.
        frameTr = self.makeFrameTransform(region, [1, 1]).inverted()[0]
        tr = pg.SRTTransform(frameTr * cameraTr)
        
        for cell in self.cells:
            w = cell['size'] / px
            pos = pg.Point(cell['x'], cell['y'])
            imgPos = tr.map(pos)
            start = (int(imgPos.x()), int(imgPos.y()))
            stop = (int(start[0]+w), int(start[1]+w))
            val = cell['intensity'] * cell['value'] * self.getParam('exposure')
            data[max(0,start[0]):max(0,stop[0]), max(0,start[1]):max(0,stop[1])] += val
        
        # Binning
        if bin[0] > 1:
            data = fn.downsample(data, bin[0], axis=0)
        if bin[1] > 1:
            data = fn.downsample(data, bin[1], axis=1)
        data = data.astype(np.uint16)
        prof()
        
        self.frameId += 1
        frames = []
        for i in range(nf):
            frames.append({'data': data, 'time': now + (i / fps), 'id': self.frameId})
        prof()
        return frames
            
                
    def quit(self):
        pass
        
    def listParams(self, params=None):
        """List properties of specified parameters, or of all parameters if None"""
        if params is None:
            return self.paramRanges
        else:
            if isinstance(params, six.string_types):
                return self.paramRanges[params]
                
            out = OrderedDict()
            for k in params:
                out[k] = self.paramRanges[k]
            return out

    def setParams(self, params, autoRestart=True, autoCorrect=True):
        dp = []
        ap = {}
        for k in params:
            if k in self.groupParams:
                ap.update(dict(zip(self.groupParams[k], params[k])))
                dp.append(k)
        params.update(ap)
        for k in dp:
            del params[k]
        
        self.params.update(params)
        newVals = params
        restart = True
        if autoRestart and restart:
            self.restart()
        self.sigParamsChanged.emit(newVals)
        return (newVals, restart)

    def getParams(self, params=None):
        if params is None:
            params = list(self.listParams().keys())
        vals = OrderedDict()
        for k in params:
            if k in self.groupParams:
                vals[k] = list(self.getParams(self.groupParams[k]).values())
            else:
                vals[k] = self.params[k]
        return vals

    def setParam(self, param, value, autoRestart=True, autoCorrect=True):
        return self.setParams({param: value}, autoRestart=autoRestart, autoCorrect=autoCorrect)

    def getParam(self, param):
        return self.getParams([param])[param]

    def createTask(self, cmd, parentTask):
        with self.lock:
            return MockCameraTask(self, cmd, parentTask)


class MockCameraTask(CameraTask):
    """Generate exposure waveform when recording with mockcamera.
    """
    def __init__(self, dev, cmd, parentTask):
        CameraTask.__init__(self, dev, cmd, parentTask)
        self._DAQCmd['exposure']['lowLevelConf'] = {'mockFunc': self.makeExpWave}
        self.frameTimes = []
        
    def makeExpWave(self):
        ## Called by DAQGeneric to simulate a read-from-DAQ
        # first look up the DAQ configuration so we know the sample rate / number
        daq = self.dev.listChannels()['exposure']['device']
        cmd = self.parentTask().tasks[daq].cmd
        start = self.parentTask().startTime
        sampleRate = cmd['rate']
        
        data = np.zeros(cmd['numPts'], dtype=np.uint8)
        for f in self.frames:
            t = f.info()['time']
            exp = f.info()['exposure']
            i0 = int((t - start) * sampleRate)
            i1 = i0 + int((exp-0.1e-3) * sampleRate)
            data[i0:i1] = 1
            
        return data
        

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

    for i in range(maxIter):
        z = z[mask]
        z0 = z0[mask]
        xInd = xInd[mask]
        yInd = yInd[mask]
        z *= z
        z += z0
        mask = np.abs(z) < 2.
        img[xInd[mask], yInd[mask]] = i % (maxIter-1)
        
    return img
