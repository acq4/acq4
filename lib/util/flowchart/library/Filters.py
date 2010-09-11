# -*- coding: utf-8 -*-
from Node import *
from functions import *
from scipy.signal import detrend
from scipy.ndimage import median_filter, gaussian_filter
from common import *


class Filter(Node):
    """Abstract node for waveform filters having a single input and output"""
    def __init__(self, name):
        Node.__init__(self, name=name, terminals={'In': {'io': 'in'}, 'Out': {'io': 'out'}})
        self.ui = None           ## override these two parameters if you want to use the default implementations
        self.stateGroup = None   ## of ctrlWidget, saveState, and restoreState.
        self.proxy = proxyConnect(self, QtCore.SIGNAL('changed'), self.delayedChange)  ## automatically generate delayedChange signal
    
    def ctrlWidget(self):
        return self.ui
    
    def process(self, In):
        return {'Out': self.processData(In)}
    
    def saveState(self):
        state = Node.saveState(self)
        state['ctrl'] = self.stateGroup.state()
        return state
    
    def restoreState(self, state):
        Node.restoreState(self, state)
        if self.stateGroup is not None:
            self.stateGroup.setState(state.get('ctrl', {}))
        
    def changed(self):
        self.emit(QtCore.SIGNAL('changed'), self)
        self.update()
        
    def delayedChange(self):
        self.emit(QtCore.SIGNAL('delayedChange'), self)
        

def metaArrayWrapper(fn):
    def newFn(self, data, *args, **kargs):
        if isinstance(data, MetaArray):
            d1 = fn(self, data.view(ndarray), *args, **kargs)
            info = data.infoCopy()
            if d1.shape != data.shape:
                for i in range(data.ndim):
                    if 'values' in info[i]:
                        info[i]['values'] = info[i]['values'][:d1.shape[i]]
            return MetaArray(d1, info=info)
        else:
            return fn(self, data, *args, **kargs)
    return newFn


class Downsample(Filter):
    """Downsample by averaging samples together."""
    nodeName = 'Downsample'
    def __init__(self, name, **opts):
        Filter.__init__(self, name)
        self.ui, self.stateGroup, self.ctrls = generateUi([
            ('n', 'intSpin', {'min': 1, 'max': 1000000})
        ])
        self.stateGroup.setState(opts)
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        return downsample(data, self.ctrls['n'].value(), axis=0)

class Subsample(Filter):
    """Downsample by selecting every Nth sample."""
    nodeName = 'Subsample'
    def __init__(self, name, **opts):
        Filter.__init__(self, name)
        self.ui, self.stateGroup, self.ctrls = generateUi([
            ('n', 'intSpin', {'min': 1, 'max': 1000000})
        ])
        self.stateGroup.setState(opts)
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        return data[::self.ctrls['n'].value()]

class Bessel(Filter):
    """Bessel filter. Input data must have time values."""
    nodeName = 'BesselFilter'
    def __init__(self, name, **opts):
        Filter.__init__(self, name)
        self.ui, self.stateGroup, self.ctrls = generateUi([
            ('band', 'combo', {'values': ['lowpass', 'highpass'], 'index': 0}),
            ('cutoff', 'spin', {'value': 1000., 'step': 1, 'dec': True, 'range': [0.0, None], 'suffix': 'Hz', 'siPrefix': True}),
            ('order', 'intSpin', {'value': 4, 'min': 1, 'max': 16}),
            ('bidir', 'check', {'checked': True})
        ])
        self.stateGroup.setState(opts)
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        s = self.stateGroup.state()
        if s['band'] == 'lowpass':
            mode = 'low'
        else:
            mode = 'high'
        return besselFilter(data, bidir=s['bidir'], btype=mode, cutoff=s['cutoff'], order=s['order'])

class Butterworth(Filter):
    """Butterworth filter"""
    nodeName = 'ButterworthFilter'
    def __init__(self, name, **opts):
        Filter.__init__(self, name)
        self.ui, self.stateGroup, self.ctrls = generateUi([
            ('band', 'combo', {'values': ['lowpass', 'highpass'], 'index': 0}),
            ('wPass', 'spin', {'value': 1000., 'step': 1, 'dec': True, 'range': [0.0, None], 'suffix': 'Hz', 'siPrefix': True}),
            ('wStop', 'spin', {'value': 2000., 'step': 1, 'dec': True, 'range': [0.0, None], 'suffix': 'Hz', 'siPrefix': True}),
            ('gPass', 'spin', {'value': 2.0, 'step': 1, 'dec': True, 'range': [0.0, None], 'suffix': 'dB', 'siPrefix': True}),
            ('gStop', 'spin', {'value': 20.0, 'step': 1, 'dec': True, 'range': [0.0, None], 'suffix': 'dB', 'siPrefix': True}),
            ('bidir', 'check', {'checked': True})
        ])
        self.stateGroup.setState(opts)
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        s = self.stateGroup.state()
        if s['band'] == 'lowpass':
            mode = 'low'
        else:
            mode = 'high'
        ret = butterworthFilter(data, bidir=s['bidir'], btype=mode, wPass=s['wPass'], wStop=s['wStop'], gPass=s['gPass'], gStop=s['gStop'])
        return ret

class Mean(Filter):
    """Filters data by taking the mean of a sliding window"""
    nodeName = 'MeanFilter'
    def __init__(self, name, **opts):
        Filter.__init__(self, name)
        self.ui, self.stateGroup, self.ctrls = generateUi([
            ('n', 'intSpin', {'min': 1, 'max': 1000000})
        ])
        self.stateGroup.setState(opts)
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    @metaArrayWrapper
    def processData(self, data):
        n = self.ctrls['n'].value()
        return rollingSum(data, n) / n

class Median(Filter):
    """Filters data by taking the median of a sliding window"""
    nodeName = 'MedianFilter'
    def __init__(self, name, **opts):
        Filter.__init__(self, name)
        self.ui, self.stateGroup, self.ctrls = generateUi([
            ('n', 'intSpin', {'min': 1, 'max': 1000000})
        ])
        self.stateGroup.setState(opts)
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    @metaArrayWrapper
    def processData(self, data):
        return median_filter(data, self.ctrls['n'].value())

class Denoise(Filter):
    """Removes anomalous spikes from data, replacing with nearby values"""
    nodeName = 'DenoiseFilter'
    def __init__(self, name, **opts):
        Filter.__init__(self, name)
        self.ui, self.stateGroup, self.ctrls = generateUi([
            ('radius', 'intSpin', {'value': 2, 'min': 0, 'max': 1000000}),
            ('threshold', 'doubleSpin', {'value': 4.0, 'min': 0, 'max': 1000})
        ])
        self.stateGroup.setState(opts)
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        s = self.stateGroup.state()
        return denoise(data, **s)

class Gaussian(Filter):
    """Gaussian smoothing filter."""
    nodeName = 'GaussianFilter'
    def __init__(self, name, **opts):
        Filter.__init__(self, name)
        self.ui, self.stateGroup, self.ctrls = generateUi([
            ('sigma', 'doubleSpin', {'min': 0, 'max': 1000000})
        ])
        self.stateGroup.setState(opts)
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)

    @metaArrayWrapper
    def processData(self, data):
        return gaussian_filter(data, self.ctrls['sigma'].value())

class Derivative(Filter):
    """Returns the pointwise derivative of the input"""
    nodeName = 'DerivativeFilter'
    def __init__(self, name, **opts):
        Filter.__init__(self, name)
        #self.stateGroup.setState(opts)
        
    def processData(self, data):
        if isinstance(data, MetaArray):
            info = data.infoCopy()
            if 'values' in info[0]:
                info[0]['values'] = info[0]['values'][:-1]
            return MetaArray(data[1:] - data[:-1], info=info)
        else:
            return data[1:] - data[:-1]

class Integral(Filter):
    """Returns the pointwise integral of the input"""
    nodeName = 'IntegralFilter'
    def __init__(self, name, **opts):
        Filter.__init__(self, name)
        #self.stateGroup.setState(opts)
        
    @metaArrayWrapper
    def processData(self, data):
        data[1:] += data[:-1]
        return data

class Detrend(Filter):
    """Removes linear trend from the data"""
    nodeName = 'DetrendFilter'
    def __init__(self, name, **opts):
        Filter.__init__(self, name)
        #self.stateGroup.setState(opts)
        
    @metaArrayWrapper
    def processData(self, data):
        return detrend(data)

class AdaptiveDetrend(Filter):
    """Removes baseline from data, ignoring anomalous events"""
    nodeName = 'AdaptiveDetrend'
    def __init__(self, name, **opts):
        Filter.__init__(self, name)
        self.ui, self.stateGroup, self.ctrls = generateUi([
            ('threshold', 'doubleSpin', {'value': 3.0, 'min': 0, 'max': 1000000})
        ])
        self.stateGroup.setState(opts)
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        return adaptiveDetrend(data, threshold=self.ctrls['threshold'].value())

#class SubtractMedian(Filter):
    #""""""
    #nodeName = 'DerivativeFilter'
    #def __init__(self, **opts):
        #Filter.__init__(self)
        #self.ui, self.stateGroup, self.ctrls = generateUi([
            #('width', 'spin', {'value': 0.1, 'step': 1, 'minStep': 100e-6, 'dec': True, 'range': [0.0, None], 'suffix': 's', 'siPrefix': True})
        #])
        #self.stateGroup.setState(opts)
        #QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    #def processData(self, data):
        #return subtractMedian(data, time=self.ctrls['width'].value())



class ExpDeconvolve(Filter):
    """Exponential deconvolution filter."""
    nodeName = 'ExpDeconvolve'
    def __init__(self, name, **opts):
        Filter.__init__(self, name)
        self.ui, self.stateGroup, self.ctrls = generateUi([
            ('tau', 'spin', {'value': 10e-3, 'step': 1, 'minStep': 100e-6, 'dec': True, 'range': [0.0, None], 'suffix': 's', 'siPrefix': True})
        ])
        self.stateGroup.setState(opts)
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)

    def processData(self, data):
        dt = 1
        if isinstance(data, MetaArray):
            dt = data.xvals(0)[1] - data.xvals(0)[0]
        d = data[:-1] + (self.ctrls['tau'].value() / dt) * (data[1:] - data[:-1])
        if isinstance(data, MetaArray):
            info = data.infoCopy()
            if 'values' in info[0]:
                info[0]['values'] = info[0]['values'][:-1]
            return MetaArray(d, info=info)
        else:
            return d
