# -*- coding: utf-8 -*-
from DevTemplate import Ui_Form
from PyQt4 import QtCore, QtGui
from lib.util.WidgetGroup import WidgetGroup
from SpinBox import *
#import pdb

class CameraDeviceGui(QtGui.QWidget):
    def __init__(self, dev, win):
        #pdb.set_trace()
        QtGui.QWidget.__init__(self)
        self.dev = dev
        self.win = win
        #self.cam = self.dev.cam
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.params = self.dev.listParams()
        self.stateGroup = WidgetGroup([])
        
        
        for k in self.params:
            p = self.params[k]
            #print p
            if not p[1]:
                continue
            try:
                val = self.dev.getParam(k)
            except:
                continue
            
            #typ = self.cam.getParamTypeName(p)
            if type(p[0]) is tuple:
                (mn, mx, step) = p[0]
                if step == 1:
                    w = QtGui.QSpinBox()
                    intmax = (2**16)-1
                    if mx is None or mx > intmax:
                        mx = intmax
                    mn = int(mn)
                    mx = int(mx)
                    step = int(step)
                    w.setRange(mn, mx)
                    w.setSingleStep(step)
                    w.setValue(val)
                else:
                    w = SpinBox()
                    w.setOpts(value=val, range=(mn, mx), dec=True, step=1)
                    
                    
            elif type(p[0]) is list:
                w = QtGui.QComboBox()
                #(opts, vals) = self.cam.getEnumList(p)
                for i in range(len(p[0])):
                    w.addItem(str(p[0][i]))
                    if p[0][i] == val:
                        w.setCurrentIndex(i)
            #elif 'BOOL' in typ:
            #    w = QtGui.QCheckBox()
            #    w.setChecked(val)
            else:
                print "    Ignoring parameter '%s': %s" % (k, str(p))
                continue
            
            self.ui.formLayout_2.addRow(k, w)
            self.stateGroup.addWidget(w, k)
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.stateChanged)
        QtCore.QObject.connect(self.ui.reconnectBtn, QtCore.SIGNAL('clicked()'), self.reconnect)
        QtCore.QObject.connect(self.dev, QtCore.SIGNAL('paramsChanged'), self.paramsChanged)
        #print "Done with UI"
            
    def stateChanged(self, p, val):
        #typ = self.cam.paramTypeName(p)
        #if 'ENUM' in typ:
            #ind = 
        #if typ[5:8] in ['INT', 'UNS', 'FLT']:
        #print val, type(val)
        self.dev.setParam(p, val)    
        
    def paramsChanged(self, params):
        for p in params.keys()[:]:  ## flatten out nested dicts
            if isinstance(params[p], dict):
                for k in params[p]:
                    params[k] = params[p][k]
        #print "Change:", params
        self.stateGroup.blockSignals(True)
        self.stateGroup.setState(params)
        self.stateGroup.blockSignals(False)
        #print "State:", self.stateGroup.state()
        
    def reconnect(self):
        self.dev.reconnect()
        
