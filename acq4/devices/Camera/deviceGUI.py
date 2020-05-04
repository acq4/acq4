# -*- coding: utf-8 -*-
from __future__ import print_function

import collections
import numpy as np
from pyqtgraph.WidgetGroup import WidgetGroup
from pyqtgraph.parametertree import Parameter, ParameterTree
from acq4.util import Qt


class CameraDeviceGui(Qt.QWidget):
    def __init__(self, dev, win):
        Qt.QWidget.__init__(self)
        self.dev = dev
        self.win = win
        self.layout = Qt.QGridLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.setLayout(self.layout)
        
        self.params = self.dev.listParams()
        self.stateGroup = WidgetGroup([])
        
        params = []
        
        for k, p in self.params.items():
            try:
                val = self.dev.getParam(k)
            except:
                continue
            
            if not p[1]:  ## read-only param
                params.append({'name': k, 'readonly': True, 'value': val, 'type': 'str'})

            else:  ## parameter is writable
                if type(p[0]) is tuple:
                    if len(p[0]) == 3:
                        (mn, mx, step) = p[0]
                    elif len(p[0]) == 2:
                        (mn, mx) = p[0]
                        step = 1
                    else:
                        raise TypeError("Invalid parameter specification for '%s': %s" % (k, repr(p)))
                    if type(mx) in [int, np.long] and type(mn) in [int, np.long]:
                        params.append({'name': k, 'type': 'int', 'value': val, 'limits': (mn, mx), 'step': step})
                    else:
                        params.append({'name': k, 'type': 'float', 'value': val, 'limits': (mn, mx), 'dec': True, 'step': 1})
                        if k == 'exposure':
                            params[-1]['suffix'] = 's'
                            params[-1]['siPrefix'] = True
                            params[-1]['minStep'] = 1e-6
                elif type(p[0]) is list:
                    #print k, val, p
                    params.append({'name': k, 'type': 'list', 'value': val, 'values': p[0]})
                else:
                    print("    Ignoring parameter '%s': %s" % (k, str(p)))
                    continue
        
        self.paramSet = Parameter(name='cameraParams', type='group', children=params)
        self.paramWidget = ParameterTree()
        self.paramWidget.setParameters(self.paramSet, showTop=False)
        self.layout.addWidget(self.paramWidget)
        
        self.paramSet.sigTreeStateChanged.connect(self.stateChanged)
        self.dev.sigParamsChanged.connect(self.paramsChanged)
            
    def stateChanged(self, param, changes):
        #print "tree state changed:"
        ## called when state is changed by user
        vals = collections.OrderedDict()
        for param, change, data in changes:
            if change == 'value':
                #print param.name(), param.value()
                vals[param.name()] = param.value()
        
        self.dev.setParams(vals)    
        
    def paramsChanged(self, params):
        #print "Camera param changed:", params
        ## Called when state of camera has changed
        for p in list(params.keys()):  ## flatten out nested dicts
            if isinstance(params[p], dict):
                for k in params[p]:
                    params[k] = params[p][k]
        
        try:   ## need to ignore tree-change signals while updating it.
            self.paramSet.sigTreeStateChanged.disconnect(self.stateChanged)
            for k, v in params.items():
                self.paramSet[k] = v
                for p2 in self.params[k][3]:    ## Update bounds if needed
                    newBounds = self.dev.listParams([p2])[p2][0]
                    self.paramSet.param(p2).setLimits(newBounds)
        finally:
            self.paramSet.sigTreeStateChanged.connect(self.stateChanged)

    def reconnect(self):
        self.dev.reconnect()
