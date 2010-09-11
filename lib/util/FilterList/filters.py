# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from SignalProxy import *
from WidgetGroup import *
from SpinBox import *
from functions import *
from scipy.signal import detrend
from scipy.ndimage import median_filter, gaussian_filter


class Filter(QtCore.QObject):
    """Abstract filter class. All filters should subclass from here.
    Filters emit the signal "changed" to indicate immediate changes to their settings, and
    "delayedChange" 300ms after the last change."""
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        self.ui = None           ## override these two parameters if you want to use the default implementations
        self.stateGroup = None   ## of getCtrlGui, saveState, and restoreState.
        self.proxy = proxyConnect(self, QtCore.SIGNAL('changed'), self.delayedChange)  ## automatically generate delayedChange signal
    
    def getCtrlGui(self):
        return self.ui
    
    def processData(self, data):
        return data  ## do nothing by default
    
    def saveState(self):
        if self.stateGroup is not None:
            return self.stateGroup.state()
        else:
            return None
    
    def restoreState(self, state):
        if self.stateGroup is not None:
            self.stateGroup.setState(state)
        
    def changed(self):
        self.emit(QtCore.SIGNAL('changed'), self)
        
    def delayedChange(self):
        self.emit(QtCore.SIGNAL('delayedChange'), self)
    
    def generateUi(self, opts):
        """Convenience function for generating common UI types"""
        widget = QtGui.QWidget()
        l = QtGui.QFormLayout()
        l.setSpacing(0)
        widget.setLayout(l)
        ctrls = {}
        for opt in opts:
            k, t, o = opt
            if t == 'intSpin':
                w = QtGui.QSpinBox()
                if 'max' in o:
                    w.setMaximum(o['max'])
                if 'min' in o:
                    w.setMinimum(o['min'])
                if 'value' in o:
                    w.setValue(o['value'])
            elif t == 'doubleSpin':
                w = QtGui.QDoubleSpinBox()
                if 'max' in o:
                    w.setMaximum(o['max'])
                if 'min' in o:
                    w.setMinimum(o['min'])                
                if 'value' in o:
                    w.setValue(o['value'])
            elif t == 'spin':
                w = SpinBox()
                w.setOpts(**o)
            elif t == 'check':
                w = QtGui.QCheckBox()
                if 'checked' in o:
                    w.setChecked(o['checked'])
            elif t == 'combo':
                w = QtGui.QComboBox()
                for i in o['values']:
                    w.addItem(i)
            else:
                raise Exception("Unknown widget type '%s'" % str(t))
            if 'tip' in o:
                w.setTooltip(o['tip'])
            w.setObjectName(k)
            l.addRow(k, w)
            ctrls[k] = w
        group = WidgetGroup(widget)
        return widget, group, ctrls
        
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
    def __init__(self, **opts):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi([
            ('n', 'intSpin', {'min': 1, 'max': 1000000})
        ])
        self.stateGroup.setState(opts)
        self.setObjectName('Downsample')
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        return downsample(data, self.ctrls['n'].value(), axis=0)

class Subsample(Filter):
    """Downsample by selecting every Nth sample."""
    def __init__(self, **opts):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi([
            ('n', 'intSpin', {'min': 1, 'max': 1000000})
        ])
        self.stateGroup.setState(opts)
        self.setObjectName('Subsample')
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        return data[::self.ctrls['n'].value()]

class Bessel(Filter):
    def __init__(self, **opts):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi([
            ('band', 'combo', {'values': ['lowpass', 'highpass'], 'index': 0}),
            ('cutoff', 'spin', {'value': 1000., 'step': 1, 'dec': True, 'range': [0.0, None], 'suffix': 'Hz', 'siPrefix': True}),
            ('order', 'intSpin', {'value': 4, 'min': 1, 'max': 16}),
            ('bidir', 'check', {'checked': True})
        ])
        self.stateGroup.setState(opts)
        self.setObjectName('Bessel')
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        s = self.stateGroup.state()
        if s['band'] == 'lowpass':
            mode = 'low'
        else:
            mode = 'high'
        return besselFilter(data, bidir=s['bidir'], btype=mode, cutoff=s['cutoff'], order=s['order'])

class Butterworth(Filter):
    def __init__(self, **opts):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi([
            ('band', 'combo', {'values': ['lowpass', 'highpass'], 'index': 0}),
            ('wPass', 'spin', {'value': 1000., 'step': 1, 'dec': True, 'range': [0.0, None], 'suffix': 'Hz', 'siPrefix': True}),
            ('wStop', 'spin', {'value': 2000., 'step': 1, 'dec': True, 'range': [0.0, None], 'suffix': 'Hz', 'siPrefix': True}),
            ('gPass', 'spin', {'value': 2.0, 'step': 1, 'dec': True, 'range': [0.0, None], 'suffix': 'dB', 'siPrefix': True}),
            ('gStop', 'spin', {'value': 20.0, 'step': 1, 'dec': True, 'range': [0.0, None], 'suffix': 'dB', 'siPrefix': True}),
            ('bidir', 'check', {'checked': True})
        ])
        self.stateGroup.setState(opts)
        self.setObjectName('Butterworth')
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        s = self.stateGroup.state()
        if s['band'] == 'lowpass':
            mode = 'low'
        else:
            mode = 'high'
        return butterworthFilter(data, bidir=s['bidir'], btype=mode, wPass=s['wPass'], wStop=s['wStop'], gPass=s['gPass'], gStop=s['gStop'])

class Mean(Filter):
    def __init__(self, **opts):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi([
            ('n', 'intSpin', {'min': 1, 'max': 1000000})
        ])
        self.stateGroup.setState(opts)
        self.setObjectName('Mean')
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    @metaArrayWrapper
    def processData(self, data):
        n = self.ctrls['n'].value()
        return rollingSum(data, n) / n

class Median(Filter):
    def __init__(self, **opts):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi([
            ('n', 'intSpin', {'min': 1, 'max': 1000000})
        ])
        self.stateGroup.setState(opts)
        self.setObjectName('Median')
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    @metaArrayWrapper
    def processData(self, data):
        return median_filter(data, self.ctrls['n'].value())

class Denoise(Filter):
    def __init__(self, **opts):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi([
            ('radius', 'intSpin', {'value': 2, 'min': 0, 'max': 1000000}),
            ('threshold', 'doubleSpin', {'value': 4.0, 'min': 0, 'max': 1000})
        ])
        self.stateGroup.setState(opts)
        self.setObjectName('Denoise')
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        s = self.stateGroup.state()
        return denoise(data, **s)

class Gaussian(Filter):
    def __init__(self, **opts):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi([
            ('sigma', 'doubleSpin', {'min': 0, 'max': 1000000})
        ])
        self.stateGroup.setState(opts)
        self.setObjectName('Gaussian')
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)

    @metaArrayWrapper
    def processData(self, data):
        return gaussian_filter(data, self.ctrls['sigma'].value())

class Derivative(Filter):
    def __init__(self, **opts):
        Filter.__init__(self)
        self.setObjectName('Derivative')
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
    def __init__(self, **opts):
        Filter.__init__(self)
        self.setObjectName('Integral')
        #self.stateGroup.setState(opts)
        
    @metaArrayWrapper
    def processData(self, data):
        data[1:] += data[:-1]
        return data

class Detrend(Filter):
    def __init__(self, **opts):
        Filter.__init__(self)
        self.setObjectName('Detrend')
        #self.stateGroup.setState(opts)
        
    @metaArrayWrapper
    def processData(self, data):
        return detrend(data)

class AdaptiveDetrend(Filter):
    def __init__(self, **opts):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi([
            ('threshold', 'doubleSpin', {'value': 3.0, 'min': 0, 'max': 1000000})
        ])
        self.stateGroup.setState(opts)
        self.setObjectName('AdaptiveDetrend')
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        return adaptiveDetrend(data, threshold=self.ctrls['threshold'].value())

class SubtractMedian(Filter):
    def __init__(self, **opts):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi([
            ('width', 'spin', {'value': 0.1, 'step': 1, 'minStep': 100e-6, 'dec': True, 'range': [0.0, None], 'suffix': 's', 'siPrefix': True})
        ])
        self.stateGroup.setState(opts)
        self.setObjectName('SubtractMedian')
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        return subtractMedian(data, time=self.ctrls['width'].value())



class ExpDeconvolve(Filter):
    def __init__(self, **opts):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi([
            ('tau', 'spin', {'value': 10e-3, 'step': 1, 'minStep': 100e-6, 'dec': True, 'range': [0.0, None], 'suffix': 's', 'siPrefix': True})
        ])
        self.stateGroup.setState(opts)
        self.setObjectName('ExpDeconvolve')
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        self.dt = None

    def processData(self, data):
        self.dt = 1
        if isinstance(data, MetaArray):
            self.dt = data.xvals(0)[1] - data.xvals(0)[0]
        d = data[:-1] + (self.ctrls['tau'].value() / self.dt) * (data[1:] - data[:-1])
        if isinstance(data, MetaArray):
            info = data.infoCopy()
            if 'values' in info[0]:
                info[0]['values'] = info[0]['values'][:-1]
            return MetaArray(d, info=info)
        else:
            return d
        
    def reconvolve(self, data):
        d = zeros(len(data)+600, dtype=float)
        d[100:len(data)+100] = data
        tau = self.ctrls['tau'].value()
        r = zeros(len(d), dtype=float)
        for i in range(len(r)-1):
            r[i+1] = r[i] + self.dt*((d[i]-r[i])/tau)
        return r
    
class ExpReconvolve(Filter):
    def __init__(self, **opts):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi([
            ('tau', 'spin', {'value': 10e-3, 'step': 1, 'minStep': 100e-6, 'dec': True, 'range': [0.0, None], 'suffix': 's', 'siPrefix': True})
        ])
        self.stateGroup.setState(opts)
        self.setObjectName('ExpReconvolve')
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        self.dt = None

    def processData(self, data):
        self.dt = 1
        if isinstance(data, MetaArray):
            self.dt = data.xvals(0)[1] - data.xvals(0)[0]
        tau = self.ctrls['tau'].value()
        r = zeros(len(data), dtype=float)
        for i in range(len(r)-1):
            r[i+1] = r[i] + self.dt*((data[i]-r[i])/tau)
        r = r[:-1]
        if isinstance(data, MetaArray):
            info = data.infoCopy()
            if 'values' in info[0]:
                info[0]['values'] = info[0]['values'][:-1]
            return MetaArray(r, info=info)
        else:
            return r
        


## Collect list of filters
FILTER_LIST = {}
for n in dir():
    obj = locals()[n]
    try:
        if obj is not Filter and issubclass(obj, Filter):
            FILTER_LIST[n] = obj
    except TypeError:
        pass