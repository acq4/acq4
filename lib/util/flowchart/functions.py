# -*- coding: utf-8 -*-
from Node import *
from advancedTypes import OrderedDict
from DirTreeWidget import *

class SubtreeNode(Node):
    """Selects files from a DirHandle"""
    nodeName = "Subtree"
    desc = "Select files from within a directory. Input must be a DirHandle."
    def __init__(self, name):
        Node.__init__(self, name, terminals={'In': ('in',)})
        self.root = None
        self.files = set()
        self.lastInput = None
        self.fileList = DirTreeWidget(defaultFlags=QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled, defaultCheckState=False)
        QtCore.QObject.connect(self.fileList, QtCore.SIGNAL('itemChanged(QTreeWidgetItem*, int)'), self.itemChanged)
        
    def process(self, In, display=True):
        #print "subtree process", In
        self.lastInput = In
        if display:
            if In is not self.root:
                self.removeAll()
                self.fileList.setRoot(In)
                self.root = In
                
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
        fname = item.handle().name(relativeTo=self.root)
        if item.checkState(0) == QtCore.Qt.Checked:
            if fname not in self.files:
                self.files.add(fname)
                self.addOutput(fname)
        else:
            if fname in self.files:
                self.files.remove(fname)
                self.removeTerminal(fname)
        self.update()
            
class MetaArrayColumnNode(Node):
    nodeName = "MetaArrayColumn"
    desc = "Select named columns from a MetaArray."
    def __init__(self, name):
        Node.__init__(self, name, terminals={'In': ('in',)})
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
        for c in self.columns:
            out[c] = In[self.axis:c]
        return out
        
    def ctrlWidget(self):
        return self.columnList

    def updateList(self, data):
        cols = data.listColumns()
        for ax in cols:  ## find first axis with columns
            if len(cols[ax]) > 0:
                self.axis = ax
                cols = set(cols[ax])
                break
                
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
    

class UniOpNode(Node):
    """Generic node for performing any operation like Out = In.fn()"""
    def __init__(self, name, fn):
        self.fn = fn
        Node.__init__(self, name, terminals={
            'In': ('in',),
            'Out': ('out',)
        })
        
    def process(self, **args):
        return {'Out': getattr(args['In'], self.fn)()}

class BinOpNode(Node):
    """Generic node for performing any operation like A.fn(B)"""
    def __init__(self, name, fn):
        self.fn = fn
        Node.__init__(self, name, terminals={
            'A': ('in',),
            'B': ('in',),
            'Out': ('out',)
        })
        
    def process(self, **args):
        fn = getattr(args['A'], self.fn)
        out = fn(args['B'])
        if out is NotImplemented:
            raise Exception("Operation %s not implemented between %s and %s" % (fn, str(type(args['A'])), str(type(args['B']))))
        #print "     ", fn, out
        return {'Out': out}

class AbsNode(UniOpNode):
    nodeName = 'Abs'
    desc = 'Returns abs(Inp). Does not check input types.'
    def __init__(self, name):
        UniOpNode.__init__(self, name, '__abs__')

class AddNode(BinOpNode):
    nodeName = 'Add'
    desc = 'Returns A + B. Does not check input types.'
    def __init__(self, name):
        BinOpNode.__init__(self, name, '__add__')

class SubtractNode(BinOpNode):
    nodeName = 'Subtract'
    desc = 'Returns A - B. Does not check input types.'
    def __init__(self, name):
        BinOpNode.__init__(self, name, '__sub__')

class MultiplyNode(BinOpNode):
    nodeName = 'Multiply'
    desc = 'Returns A * B. Does not check input types.'
    def __init__(self, name):
        BinOpNode.__init__(self, name, '__mul__')

class DivideNode(BinOpNode):
    nodeName = 'Divide'
    desc = 'Returns A / B. Does not check input types.'
    def __init__(self, name):
        BinOpNode.__init__(self, name, '__div__')










NODE_LIST = []
for o in locals().values():
    if type(o) is type(AddNode) and issubclass(o, Node) and o is not Node and hasattr(o, 'nodeName'):
            NODE_LIST.append((o.nodeName, o))
NODE_LIST.sort(lambda a,b: cmp(a[0], b[0]))
NODE_LIST = OrderedDict(NODE_LIST)