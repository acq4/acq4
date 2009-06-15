# -*- coding: utf-8 -*-
from DevTemplate import Ui_Form
from PyQt4 import QtCore, QtGui

class PVCamDevGui(QtGui.QWidget):
    def __init__(self, dev):
        QtGui.QWidget.__init__(self)
        self.dev = dev
        self.cam = self.dev.cam
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.params = self.cam.listParams()
        self.stateGroup = WidgetGroup([])
        
        for p in self.params:
            typ = self.cam.paramTypeName(p)
            if 'INT' in typ or 'UNS' in typ:
                w = QtGui.QSpinBox()
                (mn, mx, step) = self.cam.getParamRange(p)
                w.setRange(mn, mx)
                w.setSingleStep(step)
            elif 'FLT' in typ:
                w = QtGui.QDoubleSpinBox()
                (mn, mx, step) = self.cam.getParamRange(p)
                w.setRange(mn, mx)
                w.setSingleStep(step)
            elif 'ENUM' in typ:
                w = QtGui.QComboBox()
                (opts, vals) = self.cam.getEnumList(p)
                for i in range(len(opts)):
                    w.addItem(opts[i], QtCore.QVariant(vals[i]))
            else:
                print "    Ignoring parameter '%s' (%s)" % (p, typ)
                continue
            
            self.ui.fileInfoLayout.addRow(p, widget)
            self.stateGroup.addWidget(widget, p)
            
    def stateChanged(self, p, val):
        #typ = self.cam.paramTypeName(p)
        #if 'ENUM' in typ:
            #ind = 
        #if typ[5:8] in ['INT', 'UNS', 'FLT']:
        self.dev.setParam(p, val)    
        
        
        
