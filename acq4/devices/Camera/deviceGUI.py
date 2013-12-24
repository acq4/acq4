# -*- coding: utf-8 -*-
#from DevTemplate import Ui_Form
from PyQt4 import QtCore, QtGui
from acq4.pyqtgraph.WidgetGroup import WidgetGroup
from acq4.pyqtgraph.parametertree import * 
import collections

class CameraDeviceGui(QtGui.QWidget):
    def __init__(self, dev, win):
        #pdb.set_trace()
        QtGui.QWidget.__init__(self)
        self.dev = dev
        self.win = win
        #self.cam = self.dev.cam
        #self.ui = Ui_Form()
        #self.ui.setupUi(self)
        self.layout = QtGui.QGridLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.setLayout(self.layout)
        
        self.params = self.dev.listParams()
        self.stateGroup = WidgetGroup([])
        #self.labels = {}
        
        params = []
        
        for k, p in self.params.iteritems():
            try:
                val = self.dev.getParam(k)
            except:
                continue
            
            if not p[1]:  ## read-only param
                params.append({'name': k, 'readonly': True, 'value': val, 'type': 'str'})
                #w = QtGui.QLabel()
                #w.setText(str(val))
                #self.labels[k] = w

            else:  ## parameter is writable
                if type(p[0]) is tuple:
                    if len(p[0]) == 3:
                        (mn, mx, step) = p[0]
                    elif len(p[0]) == 2:
                        (mn, mx) = p[0]
                        step = 1
                    if type(mx) in [int, long] and type(mn) in [int, long]:
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
                #elif 'BOOL' in typ:
                #    w = QtGui.QCheckBox()
                #    w.setChecked(val)
                else:
                    print "    Ignoring parameter '%s': %s" % (k, str(p))
                    continue
            
                #self.stateGroup.addWidget(w, k)
            #self.ui.formLayout_2.addRow(k, w)
        #self.stateGroup.sigChanged.connect(self.stateChanged)
        
        self.paramSet = Parameter(name='cameraParams', type='group', children=params)
        self.paramWidget = ParameterTree()
        self.paramWidget.setParameters(self.paramSet, showTop=False)
        self.layout.addWidget(self.paramWidget)
        
        self.paramSet.sigTreeStateChanged.connect(self.stateChanged)
        #self.ui.reconnectBtn.clicked.connect(self.reconnect)
        self.dev.sigParamsChanged.connect(self.paramsChanged)
        
        
        
        #for k, p in self.params.iteritems():
            ##p = self.params[k]
            ##print p
            ##if not p[1]:
                ##continue
            #try:
                #val = self.dev.getParam(k)
            #except:
                #continue
            
            ##typ = self.cam.getParamTypeName(p)
            #if not p[1]:  ## read-only param
                #w = QtGui.QLabel()
                #w.setText(str(val))
                #self.labels[k] = w

            #else:  ## parameter is writable
                #if type(p[0]) is tuple:
                    #if len(p[0]) == 3:
                        #(mn, mx, step) = p[0]
                    #elif len(p[0]) == 2:
                        #(mn, mx) = p[0]
                        #step = 1
                    #if type(mx) in [int, long] and type(mn) in [int, long]:
                        #w = QtGui.QSpinBox()
                        #intmax = (2**16)-1
                        #if mx is None or mx > intmax:
                            #mx = intmax
                        #mn = int(mn)
                        #mx = int(mx)
                        #step = int(step)
                        #w.setRange(mn, mx)
                        #w.setSingleStep(step)
                        ##print k, "val:", val, type(val)
                        #w.setValue(val)
                    #else:
                        #w = SpinBox()
                        #w.setOpts(value=val, range=(mn, mx), dec=True, step=1)
                    
                #elif type(p[0]) is list:
                    #w = QtGui.QComboBox()
                    ##(opts, vals) = self.cam.getEnumList(p)
                    #for i in range(len(p[0])):
                        #w.addItem(str(p[0][i]))
                        #if p[0][i] == val:
                            #w.setCurrentIndex(i)
                ##elif 'BOOL' in typ:
                ##    w = QtGui.QCheckBox()
                ##    w.setChecked(val)
                #else:
                    #print "    Ignoring parameter '%s': %s" % (k, str(p))
                    #continue
            
                #self.stateGroup.addWidget(w, k)
            #self.ui.formLayout_2.addRow(k, w)
        ##QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.stateChanged)
        #self.stateGroup.sigChanged.connect(self.stateChanged)
        ##QtCore.QObject.connect(self.ui.reconnectBtn, QtCore.SIGNAL('clicked()'), self.reconnect)
        #self.ui.reconnectBtn.clicked.connect(self.reconnect)
        ##QtCore.QObject.connect(self.dev, QtCore.SIGNAL('paramsChanged'), self.paramsChanged)
        #self.dev.sigParamsChanged.connect(self.paramsChanged)
        ##print "Done with UI"
            
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
        for p in params.keys()[:]:  ## flatten out nested dicts
            if isinstance(params[p], dict):
                for k in params[p]:
                    params[k] = params[p][k]
        
        try:   ## need to ignore tree-change signals while updating it.
            self.paramSet.sigTreeStateChanged.disconnect(self.stateChanged)
            for k, v in params.iteritems():
                self.paramSet[k] = v
                for p2 in self.params[k][3]:    ## Update bounds if needed
                    newBounds = self.dev.listParams([p2])[p2][0]
                    self.paramSet.param(p2).setLimits(newBounds)
        finally:
            self.paramSet.sigTreeStateChanged.connect(self.stateChanged)
            
        
        #self.stateGroup.blockSignals(True)
        #self.stateGroup.setState(params)
        #print "State:", self.stateGroup.state()
        
        #for p in params:
            #if not self.params[p][1]:
                #self.labels[p].setText(str(params[p]))  ## Update read-only labels
            #else:
                #for p2 in self.params[p][3]:    ## Update bounds if needed
                    #newBounds = self.dev.listParams([p2])[p2][0]
                    #w = self.stateGroup.findWidget(p2)
                    ##print "Update bounds for %s: %s" % (p2, str(newBounds))
                    #if type(newBounds) is tuple:
                        
                        #(mn, mx, step) = newBounds
                        
                        #if isinstance(w, QtGui.QSpinBox):
                            #intmax = (2**16)-1
                            #if mx is None or mx > intmax:
                                #mx = intmax
                            #mn = int(mn)
                            #mx = int(mx)
                            #step = int(step)
                            #w.setRange(mn, mx)
                            #w.setSingleStep(step)
                        #else:
                            #w.setOpts(range=(mn, mx))
                        
                    ##elif type(newBounds) is list:
                        ##w.clear()
                        ##for i in range(len(newBounds)):
                            ##w.addItem(str(p[0][i]))
                            ##if p[0][i] == val:
                                ##w.setCurrentIndex(i)
                    
                        
        #self.stateGroup.blockSignals(False)
        
        
    def reconnect(self):
        self.dev.reconnect()
        
