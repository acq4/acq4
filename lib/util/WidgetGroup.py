# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from lib.util.generator.StimGenerator import StimGenerator
#from lib.util.PlotWidget import PlotWidget

## Bug workaround; splitters do not report their own state correctly.
def splitterState(w):
    s = w.sizes()
    if len(s) < w.count():
        s.extend([1]*(w.count()-len(s)))
    if sum(s) == 0:
        s = [1]*len(s)
    #print "%s: %d %s" % (w.objectName(), w.count(), str(s))
    return s
        
def comboState(w):
    ind = w.currentIndex()
    data = w.itemData(ind)
    if not data.isValid():
        return w.itemText(ind)
    else:
        return data.toInt()[0]    
    
def setComboState(w, v):
    if type(v) is int:
        w.setCurrentIndex(w.findData(QtCore.QVariant(v)))    
    elif isinstance(v, basestring):
        w.setCurrentIndex(w.findText(v))
        

class WidgetGroup(QtCore.QObject):
    """This class takes a list of widgets and keeps an internal record of their state which is always up to date. Allows reading and writing from groups of widgets simultaneously."""
    
    ## List of widget types which can be handled by WidgetGroup.
    ## the value for each type is a tuple (change signal, get function, set function, [auto-add children])
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
            QtGui.QSplitter.setSizes,
            True),
        QtGui.QCheckBox: 
            ('stateChanged(int)',
            QtGui.QCheckBox.isChecked,
            QtGui.QCheckBox.setChecked),
        QtGui.QComboBox:
            ('currentIndexChanged(int)',
            comboState,
            setComboState),
        QtGui.QGroupBox:
            ('clicked(bool)',
            QtGui.QGroupBox.isChecked,
            QtGui.QGroupBox.setChecked,
            True),
        StimGenerator:
            ('changed',
            StimGenerator.saveState,
            StimGenerator.loadState),
        #PlotWidget:
            #(None,
            #PlotWidget.saveState,
            #PlotWidget.restoreState),
        QtGui.QLineEdit:
            ('editingFinished()',
            lambda w: str(w.text()),
            QtGui.QLineEdit.setText),
        QtGui.QRadioButton:
            ('toggled(bool)',
            QtGui.QRadioButton.isChecked,
            QtGui.QRadioButton.setChecked),
        QtGui.QSlider:
            ('valueChanged(int)',
            QtGui.QSlider.value,
            QtGui.QSlider.setValue),
    }
    
    
    def __init__(self, widgetList):
        QtCore.QObject.__init__(self)
        self.widgetList = {}
        self.scales = {}
        self.cache = {}
        self.uncachedWidgets = []
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
            
        if type(w) in WidgetGroup.classes:
            signal = WidgetGroup.classes[type(w)][0]
        else:
            signal = w.widgetGroupInterface()[0]
            
        if signal is not None:
            QtCore.QObject.connect(w, QtCore.SIGNAL(signal), self.mkChangeCallback(w))
        else:
            self.uncachedWidgets.append(w)
       
    def interface(self, obj):
        t = type(obj)
        if t in WidgetGroup.classes:
            return WidgetGroup.classes[t]
        else:
            return obj.widgetGroupInterface()

    def checkForChildren(self, obj):
        """Return true if we should automatically search the children of this object for more."""
        iface = self.interface(obj)
        return (len(iface) > 3 and iface[3])
       
    def autoAdd(self, obj):
        ## Find all children of this object and add them if possible.
        accepted = self.acceptsType(obj)
        if accepted:
            #print "%s  auto add %s" % (self.objectName(), obj.objectName())
            self.addWidget(obj)
            
        if not accepted or self.checkForChildren(obj):
            for c in obj.children():
                self.autoAdd(c)

    def acceptsType(self, obj):
        for c in WidgetGroup.classes:
            if isinstance(obj, c):
                return True
        if hasattr(obj, 'widgetGroupInterface'):
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
        for w in self.uncachedWidgets:
            self.readWidget(w)
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
        if type(w) in WidgetGroup.classes:
            getFunc = WidgetGroup.classes[type(w)][1]
        else:
            getFunc = w.widgetGroupInterface()[1]
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
        
        if type(w) in WidgetGroup.classes:
            setFunc = WidgetGroup.classes[type(w)][2]
        else:
            setFunc = w.widgetGroupInterface()[2]
        setFunc(w, v)

        
        