# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.pyqtgraph.flowchart.Node import Node
from acq4.util import Qt
import numpy as np
import acq4.util.metaarray as metaarray
from acq4.pyqtgraph.flowchart.library.common import *
import acq4.util.functions as functions


class ExpDeconvolve(CtrlNode):
    """Exponential deconvolution filter."""
    nodeName = 'ExpDeconvolve'
    uiTemplate = [
        ('tau', 'spin', {'value': 10e-3, 'step': 1, 'minStep': 100e-6, 'dec': True, 'bounds': [0.0, None], 'suffix': 's', 'siPrefix': True})
    ]
    
    def processData(self, data):
        tau = self.ctrls['tau'].value()
        return functions.expDeconvolve(data, tau)
        #dt = 1
        #if (hasattr(data, 'implements') and data.implements('MetaArray')):
            #dt = data.xvals(0)[1] - data.xvals(0)[0]
        #d = data[:-1] + (self.ctrls['tau'].value() / dt) * (data[1:] - data[:-1])
        #if (hasattr(data, 'implements') and data.implements('MetaArray')):
            #info = data.infoCopy()
            #if 'values' in info[0]:
                #info[0]['values'] = info[0]['values'][:-1]
            #return MetaArray(d, info=info)
        #else:
            #return d

class ExpReconvolve(CtrlNode):
    """Exponential reconvolution filter. Only works with MetaArrays that were previously deconvolved."""
    nodeName = 'ExpReconvolve'
    #uiTemplate = [
        #('tau', 'spin', {'value': 10e-3, 'step': 1, 'minStep': 100e-6, 'dec': True, 'bounds': [0.0, None], 'suffix': 's', 'siPrefix': True})
    #]
    
    def processData(self, data):
        return functions.expReconvolve(data)

class Tauiness(CtrlNode):
    """Sliding-window exponential fit"""
    nodeName = 'Tauiness'
    uiTemplate = [
        ('window', 'intSpin', {'value': 100, 'min': 3, 'max': 1000000}),
        ('skip', 'intSpin', {'value': 10, 'min': 0, 'max': 10000000})
    ]
    
    def processData(self, data):
        return functions.tauiness(data, self.ctrls['window'].value(), self.ctrls['skip'].value())
        
        
