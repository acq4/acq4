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
        self.labels = {}
        
        for k in self.params:
            p = self.params[k]
            #print p
            #if not p[1]:
                #continue
            try:
                val = self.dev.getParam(k)
            except:
                continue
            
            #typ = self.cam.getParamTypeName(p)
            if not p[1]:  ## read-only param
                w = QtGui.QLabel()
                w.setText(str(val))
                self.labels[k] = w

            else:  ## parameter is writable
                if type(p[0]) is tuple:
                    if len(p[0]) == 3:
                        (mn, mx, step) = p[0]
                    elif len(p[0]) == 2:
                        (mn, mx) = p[0]
                        step = 1
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
                        #print k, "val:", val, type(val)
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
            
                self.stateGroup.addWidget(w, k)
            self.ui.formLayout_2.addRow(k, w)
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
        #print "State:", self.stateGroup.state()
        
        for p in params:
            if not self.params[p][1]:
                self.labels[p].setText(str(params[p]))  ## Update read-only labels
            else:
                for p2 in self.params[p][3]:    ## Update bounds if needed
                    newBounds = self.dev.listParams([p2])[p2][0]
                    w = self.stateGroup.findWidget(p2)
                    #print "Update bounds for %s: %s" % (p2, str(newBounds))
                    if type(newBounds) is tuple:
                        
                        (mn, mx, step) = newBounds
                        
                        if isinstance(w, QtGui.QSpinBox):
                            intmax = (2**16)-1
                            if mx is None or mx > intmax:
                                mx = intmax
                            mn = int(mn)
                            mx = int(mx)
                            step = int(step)
                            w.setRange(mn, mx)
                            w.setSingleStep(step)
                        else:
                            w.setOpts(range=(mn, mx))
                        
                    #elif type(newBounds) is list:
                        #w.clear()
                        #for i in range(len(newBounds)):
                            #w.addItem(str(p[0][i]))
                            #if p[0][i] == val:
                                #w.setCurrentIndex(i)
                    
                        
        self.stateGroup.blockSignals(False)
        
        
    def reconnect(self):
        self.dev.reconnect()
        
