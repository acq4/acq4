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
        return self.stateGroup.state()
    
    def restoreState(self, state):
        self.stateGroup.setState(state)
        
    def changed(self):
        self.emit(QtCore.SIGNAL('changed'), self)
        
    def delayedChange(self):
        self.emit(QtCore.SIGNAL('delayedChange'), self)
    
    def generateUi(self, opts):
        """Convenience function for generating common UI types"""
        widget = QtGui.QWidget()
        l = QtGui.QFormLayout()
        widget.setLayout(l)
        ctrls = {}
        for k in opts:
            t, o = opts[k]
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
    def __init__(self):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi({
            'n': ('intSpin', {'min': 1, 'max': 1000000})
        })
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        return downsample(data, self.ctrls['n'].value(), axis=0)

class Subsample(Filter):
    """Downsample by selecting every Nth sample."""
    def __init__(self):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi({
            'n': ('intSpin', {'min': 1, 'max': 1000000})
        })
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        return data[::self.ctrls['n'].value()]

class Bessel(Filter):
    def __init__(self):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi({
            'band': ('combo', {'values': ['lowpass', 'highpass'], 'index': 0}),
            'cutoff': ('spin', {'value': 1000., 'step': 1, 'dec': True, 'range': [0.0, None], 'suffix': 'Hz', 'siPrefix': True}),
            'order': ('intSpin', {'value': 4, 'min': 1, 'max': 16}),
            'bidir': ('check', {'checked': True})
        })
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        s = self.stateGroup.state()
        if s['band'] == 'lowpass':
            mode = 'low'
        else:
            mode = 'high'
        return besselFilter(data, bidir=s['bidir'], btype=mode, cutoff=s['cutoff'], order=s['order'])

class Butterworth(Filter):
    def __init__(self):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi({
            'band': ('combo', {'values': ['lowpass', 'highpass'], 'index': 0}),
            'wPass': ('spin', {'value': 1000., 'step': 1, 'dec': True, 'range': [0.0, None], 'suffix': 'Hz', 'siPrefix': True}),
            'wStop': ('spin', {'value': 2000., 'step': 1, 'dec': True, 'range': [0.0, None], 'suffix': 'Hz', 'siPrefix': True}),
            'gPass': ('spin', {'value': 2.0, 'step': 1, 'dec': True, 'range': [0.0, None], 'suffix': 'dB', 'siPrefix': True}),
            'gStop': ('spin', {'value': 20.0, 'step': 1, 'dec': True, 'range': [0.0, None], 'suffix': 'dB', 'siPrefix': True}),
            'bidir': ('check', {'checked': True})
        })
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        s = self.stateGroup.state()
        if s['band'] == 'lowpass':
            mode = 'low'
        else:
            mode = 'high'
        return butterworthFilter(data, bidir=s['bidir'], btype=mode, wPass=s['wPass'], wStop=s['wStop'], gPass=s['gPass'], gStop=s['gStop'])

class Mean(Filter):
    def __init__(self):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi({
            'n': ('intSpin', {'min': 1, 'max': 1000000})
        })
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    @metaArrayWrapper
    def processData(self, data):
        n = self.ctrls['n'].value()
        return rollingSum(data, n) / n

class Median(Filter):
    def __init__(self):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi({
            'n': ('intSpin', {'min': 1, 'max': 1000000})
        })
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    @metaArrayWrapper
    def processData(self, data):
        return median_filter(data, self.ctrls['n'].value())

class Denoise(Filter):
    def __init__(self):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi({
            'radius': ('intSpin', {'value': 2, 'min': 0, 'max': 1000000}),
            'threshold': ('doubleSpin', {'value': 4.0, 'min': 0, 'max': 1000})
        })
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
        
    def processData(self, data):
        s = self.stateGroup.state()
        return denoise(data, **s)

class Gaussian(Filter):
    def __init__(self):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi({
            'sigma': ('doubleSpin', {'min': 0, 'max': 1000000})
        })
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)

    @metaArrayWrapper
    def processData(self, data):
        return gaussian_filter(data, self.ctrls['sigma'].value())

class Derivative(Filter):
    def __init__(self):
        Filter.__init__(self)
        
    def processData(self, data):
        if isinstance(data, MetaArray):
            info = data.infoCopy()
            if 'values' in info[0]:
                info[0]['values'] = info[0]['values'][:-1]
            return MetaArray(data[1:] - data[:-1], info=info)
        else:
            return data[1:] - data[:-1]

class Integral(Filter):
    def __init__(self):
        Filter.__init__(self)
        
    @metaArrayWrapper
    def processData(self, data):
        data[1:] += data[:-1]
        return data

class Detrend(Filter):
    def __init__(self):
        Filter.__init__(self)
        
    @metaArrayWrapper
    def processData(self, data):
        return detrend(data)

class ExpDeconvolve(Filter):
    def __init__(self):
        Filter.__init__(self)
        self.ui, self.stateGroup, self.ctrls = self.generateUi({
            'tau': ('spin', {'value': 10e-3, 'step': 1, 'minStep': 100e-6, 'dec': True, 'range': [0.0, None], 'suffix': 's', 'siPrefix': True})
        })
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


## Collect list of filters
FILTER_LIST = {}
for n in dir():
    obj = locals()[n]
    try:
        if obj is not Filter and issubclass(obj, Filter):
            FILTER_LIST[n] = obj
    except TypeError:
        pass