# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui

class WidgetGroup(QtCore.QObject):
    def __init__(self, widgetList):
        self.widgetList = widgetList
        self.cache = {}
        for w, n in widgetList:
            QtCore.QObject.connect(w, QtCore.SIGNAL('changed()'), self.mkChangeCallback(w))
        
    def mkChangeCallback(self, w):
        return lambda *args: self.widgetChanged(w, *args)
        
    def widgetChanged(self, w, *args):
        pass
        
    def state(self):
        s = {}
        for w, n in self.widgetList:
            if type(w) is QtGui.QDoubleSpinBox:
                s[n] = w.value()
            elif type(w) is QtGui.QCheckBox:
                s[n] = w.isChecked()
            else:
                raise Exception("Widget type %s not supported by WidgetGroup" % type(w))
        return s

    def setState(self, s):
        for w, n in self.widgetList:
            if n not in s:
                continue
            #print w, n, s[n]
            if type(w) is QtGui.QDoubleSpinBox:
                w.setValue(s[n])
            elif type(w) is QtGui.QCheckBox:
                w.setChecked(s[n])
            else:
                raise Exception("Widget type %s not supported by WidgetGroup" % type(w))
