# -*- coding: utf-8 -*-
from ..Node import Node
from PyQt4 import QtGui, QtCore
from DirTreeWidget import *
import numpy as np
import metaarray
from common import *
from pyqtgraph import graphicsItems
import TreeWidget
import functions

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
        ('stop', 'spin', {'value': 0.1, 'step': 0.1}),
        ('display', 'check', {'value': True}),
        ('movable', 'check', {'value': True}),
    ]
    
    def __init__(self, name):
        self.items = {}
        CtrlNode.__init__(self, name, terminals={
            'data': {'io': 'in'},
            'selected': {'io': 'out'},
            'region': {'io': 'out'},
            'widget': {'io': 'out', 'multi': True}
        })
        self.ctrls['display'].toggled.connect(self.displayToggled)
        self.ctrls['movable'].toggled.connect(self.movableToggled)
        
    def displayToggled(self, b):
        for item in self.items.itervalues():
            item.setVisible(b)
            
    def movableToggled(self, b):
        for item in self.items.itervalues():
            item.setMovable(b)
            
        
    def process(self, data=None, display=True):
        #print "process.."
        s = self.stateGroup.state()
        region = [s['start'], s['stop']]
        
        if display:
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
                    item.setVisible(s['display'])
                    item.setMovable(s['movable'])
                    #print "  new rgn:", c, region
                    #self.items[c].setYRange([0., 0.2], relative=True)
        
        if self.selected.isConnected():
            if data is None:
                sliced = None
            elif isinstance(data, MetaArray):
                sliced = data[0:s['start']:s['stop']]
            else:
                mask = (data['time'] >= s['start']) * (data['time'] < s['stop'])
                sliced = data[mask]
        else:
            sliced = None
            
        return {'selected': sliced, 'widget': self.items, 'region': region}
        
        
    def rgnChanged(self, item):
        region = item.getRegion()
        self.stateGroup.setState({'start': region[0], 'stop': region[1]})
        self.update()
        
        
class EvalNode(Node):
    """Return the output of a string evaluated/executed by the python interpreter.
    The string may be either an expression or a python script, and inputs are accessed as the name of the terminal. 
    For expressions, a single value may be evaluated for a single output, or a dict for multiple outputs.
    For a script, the text will be executed as the body of a function."""
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
            print "eval node update"
            self.update()
        
    def process(self, display=True, **args):
        l = locals()
        l.update(args)
        ## try eval first, then exec
        try:  
            text = str(self.text.toPlainText()).replace('\n', ' ')
            output = eval(text, globals(), l)
        except SyntaxError:
            fn = "def fn(**args):\n"
            run = "\noutput=fn(**args)\n"
            text = fn + "\n".join(["    "+l for l in str(self.text.toPlainText()).split('\n')]) + run
            exec(text)
        return output
        
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
        
class ColumnJoinNode(Node):
    """Concatenates record arrays and/or adds new columns"""
    nodeName = 'ColumnJoin'
    
    def __init__(self, name):
        Node.__init__(self, name, terminals = {
            'output': {'io': 'out'},
        })
        
        #self.items = []
        
        self.ui = QtGui.QWidget()
        self.layout = QtGui.QGridLayout()
        self.ui.setLayout(self.layout)
        
        self.tree = TreeWidget.TreeWidget()
        self.addInBtn = QtGui.QPushButton('+ Input')
        self.remInBtn = QtGui.QPushButton('- Input')
        
        self.layout.addWidget(self.tree, 0, 0, 1, 2)
        self.layout.addWidget(self.addInBtn, 1, 0)
        self.layout.addWidget(self.remInBtn, 1, 1)

        self.addInBtn.clicked.connect(self.addInput)
        self.addInBtn.clicked.connect(self.remInput)
        self.tree.sigItemMoved.connect(self.update)
        
    def ctrlWidget(self):
        return self.ui
        
    def addInput(self):
        term = Node.addInput(self, 'input', renamable=True)
        item = QtGui.QTreeWidgetItem([term.name()])
        item.term = term
        term.joinItem = item
        #self.items.append((term, item))
        self.tree.addTopLevelItem(item)

    def remInput(self):
        sel = self.tree.currentItem()
        term = sel.term
        term.joinItem = None
        sel.term = None
        self.tree.removeTopLevelItem(sel)
        self.removeTerminal(term)
        self.update()

    def process(self, display=True, **args):
        order = self.order()
        vals = []
        for name in order:
            if name not in args:
                continue
            val = args[name]
            if isinstance(val, np.ndarray) and len(val.dtype) > 0:
                vals.append(val)
            else:
                vals.append((name, None, val))
        return {'output': functions.concatenateColumns(vals)}

    def order(self):
        return [str(self.tree.topLevelItem(i).text(0)) for i in range(self.tree.topLevelItemCount())]

    def saveState(self):
        state = Node.saveState(self)
        state['order'] = self.order()
        return state
        
    def restoreState(self, state):
        Node.restoreState(self, state)
        inputs = [inp.name() for inp in self.inputs()]
        for name in inputs:
            if name not in state['order']:
                self.removeTerminal(name)
        for name in state['order']:
            if name not in inputs:
                Node.addInput(self, name, renamable=True)
        
        self.tree.clear()
        for name in state['order']:
            term = self[name]
            item = QtGui.QTreeWidgetItem([name])
            item.term = term
            term.joinItem = item
            #self.items.append((term, item))
            self.tree.addTopLevelItem(item)

    def terminalRenamed(self, term, oldName):
        Node.terminalRenamed(self, term, oldName)
        item = term.joinItem
        item.setText(0, term.name())
        self.update()
        
        