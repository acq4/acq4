# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from SpinBox import *
from SignalProxy import *
from WidgetGroup import *
from ColorMapper import ColorMapper
from ..Node import Node
import metaarray
import numpy as np
from pyqtgraph.ColorButton import ColorButton

def generateUi(opts):
    """Convenience function for generating common UI types"""
    widget = QtGui.QWidget()
    l = QtGui.QFormLayout()
    l.setSpacing(0)
    widget.setLayout(l)
    ctrls = {}
    for opt in opts:
        if len(opt) == 2:
            k, t = opt
            o = {}
        elif len(opt) == 3:
            k, t, o = opt
        else:
            raise Exception("Widget specification must be (name, type) or (name, type, {opts})")
        if t == 'intSpin':
            w = QtGui.QSpinBox()
            if 'max' in o:
                w.setMaximum(o['max'])
            if 'min' in o:
                w.setMinimum(o['min'])
            if 'value' in o:
                w.setValue(o['value'])
        elif t == 'doubleSpin':
            w = QtGui.QDoubleSpinBox()
            if 'max' in o:
                w.setMaximum(o['max'])
            if 'min' in o:
                w.setMinimum(o['min'])                
            if 'value' in o:
                w.setValue(o['value'])
        elif t == 'spin':
            w = SpinBox()
            w.setOpts(**o)
        elif t == 'check':
            w = QtGui.QCheckBox()
            if 'checked' in o:
                w.setChecked(o['checked'])
        elif t == 'combo':
            w = QtGui.QComboBox()
            for i in o['values']:
                w.addItem(i)
        elif t == 'colormap':
            w = ColorMapper()
        elif t == 'color':
            w = ColorButton()
        else:
            raise Exception("Unknown widget type '%s'" % str(t))
        if 'tip' in o:
            w.setTooltip(o['tip'])
        w.setObjectName(k)
        l.addRow(k, w)
        ctrls[k] = w
    group = WidgetGroup(widget)
    return widget, group, ctrls

#class TerminalEditor(QtGui.QWidget):
    #def __init__(self, node):
        #QtGui.QWidget.__init__(self)
        
        #self.node = node
        
    
        


class CtrlNode(Node):
    """Abstract class for nodes with auto-generated control UI"""
    def __init__(self, name, ui=None, terminals=None):
        if ui is None:
            if hasattr(self, 'uiTemplate'):
                ui = self.uiTemplate
            else:
                ui = []
        if terminals is None:
            terminals = {'In': {'io': 'in'}, 'Out': {'io': 'out', 'bypass': 'In'}}
        Node.__init__(self, name=name, terminals=terminals)
        
        self.ui, self.stateGroup, self.ctrls = generateUi(ui)
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.changed)
       
    def ctrlWidget(self):
        return self.ui
       
    def changed(self):
        self.update()

    def process(self, In, display=True):
        out = self.processData(In)
        return {'Out': out}
    
    def saveState(self):
        state = Node.saveState(self)
        state['ctrl'] = self.stateGroup.state()
        return state
    
    def restoreState(self, state):
        Node.restoreState(self, state)
        if self.stateGroup is not None:
            self.stateGroup.setState(state.get('ctrl', {}))
            
            

#class Filter(Node):
    #"""Abstract node for waveform filters having a single input and output"""
    #def __init__(self, name):
        #Node.__init__(self, name=name, terminals={'In': {'io': 'in'}, 'Out': {'io': 'out'}})
        #self.ui = None           ## override these two parameters if you want to use the default implementations
        #self.stateGroup = None   ## of ctrlWidget, saveState, and restoreState.
        #self.proxy = proxyConnect(self, QtCore.SIGNAL('changed'), self.delayedChange)  ## automatically generate delayedChange signal
    
    #def ctrlWidget(self):
        #return self.ui
    
    #def process(self, In):
        #return {'Out': self.processData(In)}
    
    #def saveState(self):
        #state = Node.saveState(self)
        #state['ctrl'] = self.stateGroup.state()
        #return state
    
    #def restoreState(self, state):
        #Node.restoreState(self, state)
        #if self.stateGroup is not None:
            #self.stateGroup.setState(state.get('ctrl', {}))
        
    #def changed(self):
        #self.emit(QtCore.SIGNAL('changed'), self)
        #self.update()
        
    #def delayedChange(self):
        #self.emit(QtCore.SIGNAL('delayedChange'), self)
        

def metaArrayWrapper(fn):
    def newFn(self, data, *args, **kargs):
        if isinstance(data, metaarray.MetaArray):
            d1 = fn(self, data.view(np.ndarray), *args, **kargs)
            info = data.infoCopy()
            if d1.shape != data.shape:
                for i in range(data.ndim):
                    if 'values' in info[i]:
                        info[i]['values'] = info[i]['values'][:d1.shape[i]]
            return metaarray.MetaArray(d1, info=info)
        else:
            return fn(self, data, *args, **kargs)
    return newFn

