# -*- coding: utf-8 -*-
from ..Node import Node
from PyQt4 import QtGui, QtCore
from DirTreeWidget import *
import numpy as np
import metaarray
from common import *
from pyqtgraph import graphicsItems

class SubtreeNode(Node):
    """Select files from within a directory. Input must be a DirHandle."""
    nodeName = "Subtree"
    def __init__(self, name):
        Node.__init__(self, name, terminals={'In': {'io': 'in'}})
        self.root = None
        self.files = set()
        self.lastInput = None
        self.fileList = DirTreeWidget(checkState=False, allowMove=False, allowRename=False)
        QtCore.QObject.connect(self.fileList, QtCore.SIGNAL('itemChanged(QTreeWidgetItem*, int)'), self.itemChanged)
        
    def process(self, In, display=True):
        #print "subtree process", In
        self.lastInput = In
        if display:
            if In is not self.root:
                #self.removeAll()
                self.fileList.blockSignals(True)
                self.fileList.setBaseDirHandle(In)
                self.root = In
                for f in self.files:
                    if In.exists(f):
                        fh = In[f]
                        item = self.fileList.item(fh)
                        item.setChecked(True)
                    else:
                        self.files.remove(f)
                
                self.fileList.blockSignals(False)
        out = {}
        for f in self.files:
            f2 = In[f]
            if f2.isFile():
                out[f] = f2.read()
            else:
                out[f] = f2
        return out
        
    def ctrlWidget(self):
        return self.fileList

    def removeAll(self):
        for f in self.files:
            self.removeTerminal(f)
        self.files = set()

    def itemChanged(self, item):
        fname = item.handle.name(relativeTo=self.root)
        if item.checkState(0) == QtCore.Qt.Checked:
            if fname not in self.files:
                self.files.add(fname)
                self.addOutput(fname)
        else:
            if fname in self.files:
                self.files.remove(fname)
                self.removeTerminal(fname)
        self.update()

    def saveState(self):
        state = Node.saveState(self)
        state['selected'] = list(self.files)
        return state
        
    def restoreState(self, state):
        Node.restoreState(self, state)
        self.files = set(state.get('selected', []))
        for f in self.files:
            self.addOutput(f)

class ColumnSelectNode(Node):
    """Select named columns from a record array or MetaArray."""
    nodeName = "ColumnSelect"
    def __init__(self, name):
        Node.__init__(self, name, terminals={'In': {'io': 'in'}})
        self.columns = set()
        #self.lastInput = None
        #self.fileList = DirTreeWidget(defaultFlags=QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled, defaultCheckState=False)
        self.columnList = QtGui.QListWidget()
        self.axis = 0
        QtCore.QObject.connect(self.columnList, QtCore.SIGNAL('itemChanged(QListWidgetItem*)'), self.itemChanged)
        
    def process(self, In, display=True):
        #print "MetaArrayColumn process:"
        #self.lastInput = In
        if display:
            self.updateList(In)
                
        out = {}
        if isinstance(In, metaarray.MetaArray):
            for c in self.columns:
                out[c] = In[self.axis:c]
        elif isinstance(In, np.ndarray) and In.dtype.fields is not None:
            for c in self.columns:
                out[c] = In[c]
        else:
            self.In.setValueAcceptable(False)
            raise Exception("Input must be MetaArray or ndarray with named fields")
            
        return out
        
    def ctrlWidget(self):
        return self.columnList

    def updateList(self, data):
        if isinstance(data, metaarray.MetaArray):
            cols = data.listColumns()
            for ax in cols:  ## find first axis with columns
                if len(cols[ax]) > 0:
                    self.axis = ax
                    cols = set(cols[ax])
                    break
        else:
            cols = data.dtype.fields.keys()
                
        rem = set()
        for c in self.columns:
            if c not in cols:
                self.removeTerminal(c)
                rem.add(c)
        self.columns -= rem
                
        self.columnList.blockSignals(True)
        self.columnList.clear()
        for c in cols:
            item = QtGui.QListWidgetItem(c)
            item.setFlags(QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsUserCheckable)
            if c in self.columns:
                item.setCheckState(QtCore.Qt.Checked)
            else:
                item.setCheckState(QtCore.Qt.Unchecked)
            self.columnList.addItem(item)
        self.columnList.blockSignals(False)
        

    def itemChanged(self, item):
        col = str(item.text())
        if item.checkState() == QtCore.Qt.Checked:
            if col not in self.columns:
                self.columns.add(col)
                self.addOutput(col)
        else:
            if col in self.columns:
                self.columns.remove(col)
                self.removeTerminal(col)
        self.update()
        
    def saveState(self):
        state = Node.saveState(self)
        state['columns'] = list(self.columns)
        return state
    
    def restoreState(self, state):
        Node.restoreState(self, state)
        self.columns = set(state.get('columns', []))
        for c in self.columns:
            self.addOutput(c)



class RegionSelectNode(CtrlNode):
    """Returns a slice from a 1-D array. Connect the 'widget' output to a plot to display a region-selection widget."""
    nodeName = "RegionSelect"
    uiTemplate = [
        ('start', 'spin', {'value': 0, 'step': 0.1}),
        ('stop', 'spin', {'value': 0.1, 'step': 0.1})
    ]
    
    def __init__(self, name):
        self.items = {}
        CtrlNode.__init__(self, name, terminals={
            'data': {'io': 'in'},
            'selected': {'io': 'out'},
            'widget': {'io': 'out', 'multi': True}
        })
        
    def process(self, data, display=True):
        #print "process.."
        s = self.stateGroup.state()
        region = [s['start'], s['stop']]
        conn = self['widget'].connections()
        for c in conn:
            plot = c.node().getPlot()
            if plot is None:
                continue
            if c in self.items:
                item = self.items[c]
                item.setRegion(region)
                #print "  set rgn:", c, region
                #item.setXVals(events)
            else:
                item = graphicsItems.LinearRegionItem(plot, vals=region)
                self.items[c] = item
                item.connect(item, QtCore.SIGNAL('regionChanged'), self.rgnChanged)
                #print "  new rgn:", c, region
                #self.items[c].setYRange([0., 0.2], relative=True)
                
        if isinstance(data, MetaArray):
            sliced = data[0:s['start']:s['stop']]
        else:
            mask = (data['time'] >= s['start']) * (data['time'] < s['stop'])
            sliced = data[mask]
        return {'selected': sliced, 'widget': self.items}
        
        
    def rgnChanged(self, item):
        region = item.getRegion()
        self.stateGroup.setState({'start': region[0], 'stop': region[1]})
        self.update()
        
        
class EvalNode(Node):
    """Return the output of a string evaluated by the python interpreter."""
    nodeName = 'PythonEval'
    
    def __init__(self, name):
        Node.__init__(self, name, terminals = {
            'input': {'io': 'in', 'renamable': True},
            'output': {'io': 'out', 'renamable': True},
        })
        
        self.ui = QtGui.QWidget()
        self.layout = QtGui.QGridLayout()
        self.addInBtn = QtGui.QPushButton('+Input')
        self.addOutBtn = QtGui.QPushButton('+Output')
        self.text = QtGui.QTextEdit()
        self.layout.addWidget(self.addInBtn, 0, 0)
        self.layout.addWidget(self.addOutBtn, 0, 1)
        self.layout.addWidget(self.text, 1, 0, 1, 2)
        self.ui.setLayout(self.layout)
        
        QtCore.QObject.connect(self.addInBtn, QtCore.SIGNAL('clicked()'), self.addInput)
        QtCore.QObject.connect(self.addOutBtn, QtCore.SIGNAL('clicked()'), self.addOutput)
        self.ui.focusOutEvent = lambda ev: self.focusOutEvent(ev)
        self.lastText = None
        
    def ctrlWidget(self):
        return self.ui
        
        
    def addInput(self):
        Node.addInput(self, 'input', renamable=True)
        
    def addOutput(self):
        Node.addOutput(self, 'output', renamable=True)
        
    def focusOutEvent(self, ev):
        text = str(self.text.toPlainText())
        if text != self.lastText:
            self.lastText = text
            self.update()
        
    def process(self, display=False, **args):
        l = locals()
        l.update(args)
        text = str(self.text.toPlainText()).replace('\n', ' ')
        out = eval(text, globals(), l)
        return {'output': out}
        
    def saveState(self):
        state = Node.saveState(self)
        state['text'] = str(self.text.toPlainText())
        state['terminals'] = self.saveTerminals()
        return state
        
    def restoreState(self, state):
        Node.restoreState(self, state)
        self.text.clear()
        self.text.insertPlainText(state['text'])
        self.restoreTerminals(state['terminals'])
        self.update()
        