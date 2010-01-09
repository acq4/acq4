# -*- coding: utf-8 -*-
from DevTemplate import Ui_Form
from PyQt4 import QtCore, QtGui
from lib.util.WidgetGroup import WidgetGroup
#import pdb

class PVCamDevGui(QtGui.QWidget):
    def __init__(self, dev, win):
        #pdb.set_trace()
        QtGui.QWidget.__init__(self)
        self.dev = dev
        self.win = win
        self.cam = self.dev.cam
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.params = self.cam.listParams()
        self.stateGroup = WidgetGroup([])
        
        
        for p in self.params:
            #print p
            if not self.cam.paramWritable(p):
                continue
            try:
                val = self.cam.getParam(p)
            except:
                continue
            typ = self.cam.getParamTypeName(p)
            if 'INT' in typ or 'UNS' in typ:
                w = QtGui.QSpinBox()
                (mn, mx, step) = self.cam.getParamRange(p)
                intmax = (2**16)-1
                if mx > intmax:
                    mx = intmax
                w.setRange(int(mn), int(mx))
                w.setSingleStep(int(step))
                w.setValue(val)
            elif 'FLT' in typ:
                w = QtGui.QDoubleSpinBox()
                (mn, mx, step) = self.cam.getParamRange(p)
                w.setRange(mn, mx)
                w.setSingleStep(step)
                w.setValue(val)
            elif 'ENUM' in typ:
                w = QtGui.QComboBox()
                (opts, vals) = self.cam.getEnumList(p)
                for i in range(len(opts)):
                    w.addItem(opts[i], QtCore.QVariant(vals[i]))
                    if vals[i] == val:
                        w.setCurrentIndex(i)
            elif 'BOOL' in typ:
                w = QtGui.QCheckBox()
                w.setChecked(val)
            else:
                print "    Ignoring parameter '%s' (%s)" % (p, typ)
                continue
            
            self.ui.formLayout_2.addRow(p, w)
            self.stateGroup.addWidget(w, p)
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.stateChanged)
        QtCore.QObject.connect(self.ui.reconnectBtn, QtCore.SIGNAL('clicked()'), self.reconnect)
        #print "Done with UI"
            
    def stateChanged(self, p, val):
        #typ = self.cam.paramTypeName(p)
        #if 'ENUM' in typ:
            #ind = 
        #if typ[5:8] in ['INT', 'UNS', 'FLT']:
        #print val, type(val)
        self.dev.setParam(p, val)    
        
    def reconnect(self):
        self.dev.reconnect()
        
