# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui

class WidgetGroup(QtCore.QObject):
    """This class takes a list of widgets and keeps an internal record of their state which is always up to date. Allows reading and writing from groups of widgets simultaneously."""
    
    
    def __init__(self, widgetList):
        QtCore.QObject.__init__(self)
        self.widgetList = dict(widgetList)
        self.cache = {}
        for w in self.widgetList:
            self.readWidget(w)
            if type(w) is QtGui.QDoubleSpinBox:
                QtCore.QObject.connect(w, QtCore.SIGNAL('valueChanged(double)'), self.mkChangeCallback(w))
            elif type(w) is QtGui.QSpinBox:
                QtCore.QObject.connect(w, QtCore.SIGNAL('valueChanged(int)'), self.mkChangeCallback(w))
            elif type(w) is QtGui.QCheckBox:
                QtCore.QObject.connect(w, QtCore.SIGNAL('stateChanged(int)'), self.mkChangeCallback(w))
            elif type(w) is QtGui.QSplitter:
                QtCore.QObject.connect(w, QtCore.SIGNAL('splitterMoved(int,int)'), self.mkChangeCallback(w))
            else:
                raise Exception("Widget type %s not supported by WidgetGroup" % type(w))
        
    def mkChangeCallback(self, w):
        return lambda *args: self.widgetChanged(w, *args)
        
    def widgetChanged(self, w, *args):
        n = self.widgetList[w]
        v1 = self.cache[n]
        v2 = self.readWidget(w)
        if v1 != v2:
            #print "widget", n, " = ", v2
            self.emit(QtCore.SIGNAL('changed'), self.widgetList[w], v2)
        
    def state(self):
        return self.cache

    def setState(self, s):
        for w in self.widgetList:
            n = self.widgetList[w]
            if n not in s:
                continue
            self.setWidget(w, s[n])

    def readWidget(self, w):
        if type(w) in [QtGui.QDoubleSpinBox, QtGui.QSpinBox]:
            val = w.value()
        elif type(w) is QtGui.QCheckBox:
            val = w.isChecked()
        elif type(w) is QtGui.QSplitter:
            val = str(w.saveState().toPercentEncoding())
        else:
            raise Exception("Widget type %s not supported by WidgetGroup" % type(w))
        n = self.widgetList[w]
        self.cache[n] = val
        return val

    def setWidget(self, w, v):
        if type(w) in [QtGui.QDoubleSpinBox, QtGui.QSpinBox]:
            w.setValue(v)
        elif type(w) is QtGui.QCheckBox:
            w.setChecked(v)
        elif type(w) is QtGui.QSplitter:
            w.restoreState(QtCore.QByteArray.fromPercentEncoding(v))
        else:
            raise Exception("Widget type %s not supported by WidgetGroup" % type(w))
        #self.readWidget(w)  ## should happen automatically


