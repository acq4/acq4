# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from lib.util.generator.StimGenerator import StimGenerator

## Bug workaround; splitters do not report their own state correctly.
def splitterState(w):
    s = w.sizes()
    if len(s) < w.count():
        s.extend([1]*(w.count()-len(s)))
    if sum(s) == 0:
        s = [1]*len(s)
    #print "%s: %d %s" % (w.objectName(), w.count(), str(s))
    return s
        

class WidgetGroup(QtCore.QObject):
    """This class takes a list of widgets and keeps an internal record of their state which is always up to date. Allows reading and writing from groups of widgets simultaneously."""
    
    ## List of widget types which can be handled by WidgetGroup.
    ## the value for each type is a tuple (change signal, get function, set function)
    classes = {
        QtGui.QSpinBox: 
            ('valueChanged(int)', 
            QtGui.QSpinBox.value, 
            QtGui.QSpinBox.setValue),
        QtGui.QDoubleSpinBox: 
            ('valueChanged(double)', 
            QtGui.QDoubleSpinBox.value, 
            QtGui.QDoubleSpinBox.setValue),
        QtGui.QSplitter: 
            ('splitterMoved(int,int)', 
            splitterState,
            #QtGui.QSplitter.sizes,
            QtGui.QSplitter.setSizes),
            #lambda w: str(w.saveState().toPercentEncoding()),
            #splitterState,
            #lambda w,v: w.restoreState(QtCore.QByteArray.fromPercentEncoding(v))),
        QtGui.QCheckBox: 
            ('stateChanged(int)',
            QtGui.QCheckBox.isChecked,
            QtGui.QCheckBox.setChecked),
        StimGenerator:
            ('changed',
            StimGenerator.saveState,
            StimGenerator.loadState),
        QtGui.QComboBox:
            ('currentIndexChanged(int)',
            lambda w: int(w.itemData(w.currentIndex())),
            lambda w,v: w.setCurrentIndex(w.findData(QtCore.QVariant(v)))
    }
    
    
    def __init__(self, widgetList):
        QtCore.QObject.__init__(self)
        self.widgetList = {}
        self.scales = {}
        self.cache = {}
        if isinstance(widgetList, QtCore.QObject):
            self.autoAdd(widgetList)
        elif isinstance(widgetList, list):
            for w in widgetList:
                self.addWidget(*w)
        else:
            raise Exception("Wrong argument type %s" % type(widgetList))
        
    def addWidget(self, w, name=None, scale=None):
        if name is None:
            name = str(w.objectName())
        self.widgetList[w] = name
        self.scales[w] = scale
        self.readWidget(w)
        if not self.acceptsType(w):
            raise Exception("Widget type %s not supported by WidgetGroup" % type(w))
            
        signal = WidgetGroup.classes[type(w)][0]
        QtCore.QObject.connect(w, QtCore.SIGNAL(signal), self.mkChangeCallback(w))
            
    def autoAdd(self, obj):
        ## Find all children of this object and add them if possible.
        if self.acceptsType(obj):
            #print "%s  auto add %s" % (self.objectName(), obj.objectName())
            self.addWidget(obj)
        for c in obj.children():
            self.autoAdd(c)

    def acceptsType(self, obj):
        for c in WidgetGroup.classes:
            if isinstance(obj, c):
                return True
        return False
        #return (type(obj) in WidgetGroup.classes)

    def setScale(self, widget, scale):
        val = self.readWidget(widget)
        self.scales[widget] = scale
        self.setWidget(widget, val)
        #print "scaling %f to %f" % (val, self.readWidget(widget))
        

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
        return self.cache.copy()

    def setState(self, s):
        #print "SET STATE", self, s
        for w in self.widgetList:
            n = self.widgetList[w]
            #print "  restore %s?" % n
            if n not in s:
                continue
            #print "    restore state", w, n, s[n]
            self.setWidget(w, s[n])

    def readWidget(self, w):
        getFunc = WidgetGroup.classes[type(w)][1]
        val = getFunc(w)
        if self.scales[w] is not None:
            val /= self.scales[w]
        if isinstance(val, QtCore.QString):
            val = str(val)
        n = self.widgetList[w]
        self.cache[n] = val
        return val

    def setWidget(self, w, v):
        if self.scales[w] is not None:
            v *= self.scales[w]
        setFunc = WidgetGroup.classes[type(w)][2]
        setFunc(w, v)

        
        