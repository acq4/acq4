from PyQt4 import QtCore, QtGui
from TreeWidget import TreeWidget
from SpinBox import SpinBox
from pyqtgraph.ColorButton import ColorButton
import collections, os, weakref

PARAM_TYPES = {}


def registerParameterType(name, cls):
    global PARAM_TYPES
    PARAM_TYPES[name] = cls

class Parameter(QtCore.QObject):
    ## name, type, limits, etc.
    ## can also carry UI hints (slider vs spinbox, etc.)
    
    sigValueChanged = QtCore.Signal(object, object)  ## value, self
    sigChildAdded = QtCore.Signal(object, object, object)  ## self, child, index
    sigChildRemoved = QtCore.Signal(object, object)  ## self, child
    sigParentChanged = QtCore.Signal(object, object)  ## self, parent
    sigLimitsChanged = QtCore.Signal(object, object)  ## self, limits
    sigNameChanged = QtCore.Signal(object, object)  ## self, name
    
    
    def __new__(cls, *args, **opts):
        try:
            cls = PARAM_TYPES[opts['type']]
        except KeyError:
            pass
        #print "Build new:", cls
        return QtCore.QObject.__new__(cls, *args, **opts)
    
    def __init__(self, **opts):
        QtCore.QObject.__init__(self)
        
        self.opts = opts
        self.childs = []
        self.names = {}
        self.items = weakref.WeakKeyDictionary()
        self._parent = None
        
        if 'value' not in opts:
            opts['value'] = None
        
        if 'name' not in opts or not isinstance(opts['name'], basestring):
            raise Exception("Parameter must have a string name specified in opts.")
        
        for chOpts in opts.get('params', []):
            self.addChild(chOpts)
            
        if 'value' in opts and 'default' not in opts:
            opts['default'] = opts['value']
            
        
            
        
    def name(self):
        return self.opts['name']
    
    def setName(self, name):
        """Attempt to change the name of this parameter; return the actual name. 
        (The parameter may reject the name change or automatically pick a different name)"""
        parent = self.parent()
        if parent is not None:
            name = parent._renameChild(self, name)  ## first ask parent if it's ok to rename
        if self.opts['name'] != name:
            self.opts['name'] = name
            self.sigNameChanged.emit(self, name)
        return name
    
    def setValue(self, value):
        ## return the actual value that was set
        ## (this may be different from the value that was requested)
        #print self, "Set value:", value, self.opts['value'], self.opts['value'] == value
        if self.opts['value'] == value:
            return value
        self.opts['value'] = value
        self.sigValueChanged.emit(value, self)
        return value

    def value(self):
        return self.opts['value']

    def getValues(self):
        """Return a tree of all values that are children of this parameter"""
        vals = collections.OrderedDict()
        for ch in self:
            vals[ch.name()] = (ch.value(), ch.getValues())
        return vals
    
    def saveState(self):
        """Return a structure representing the entire state of the parameter tree."""
        state = self.opts.copy()
        state['params'] = {ch.name(): ch.saveState() for ch in self}
        return state


    def defaultValue(self):
        return self.opts['default']
        
    def setDefault(self, val):
        self.opts['default'] = val

    def setToDefault(self):
        if self.hasDefault():
            self.setValue(self.defaultValue())

    def hasDefault(self):
        return 'default' in self.opts
        
    def valueIsDefault(self):
        return self.value() == self.defaultValue()
        
    def setLimits(self, limits):
        if 'limits' in self.opts and self.opts['limits'] == limits:
            return
        self.opts['limits'] = limits
        self.sigLimitsChanged.emit(self, limits)
        return limits

    def makeTreeItem(self, depth):
        """Return a TreeWidgetItem suitable for displaying/controlling the content of this parameter.
        Most subclasses will want to override this function.
        """
        if hasattr(self, 'itemClass'):
            #print "Param:", self, "Make item from itemClass:", self.itemClass
            return self.itemClass(self, depth)
        else:
            return ParameterItem(self, depth=depth)


    def addChild(self, child):
        """Add another parameter to the end of this parameter's child list."""
        return self.insertChild(len(self.childs), child)
        
    def insertChild(self, pos, child):
        """Insert a new child at pos.
        If pos is a Parameter, then insert at the position of that Parameter.
        If child is a dict, then a parameter is constructed as Parameter(**child)
        """
        if isinstance(child, dict):
            child = Parameter(**child)
        
        name = child.name()
        if name in self.names:
            raise Exception("Already have child named %s" % str(name))
        if isinstance(pos, Parameter):
            pos = self.childs.index(pos)
            
        if child.parent() is not None:
            child.remove()
            
        self.names[name] = child
        self.childs.insert(pos, child)
        
        child.parentChanged(self)
        self.sigChildAdded.emit(self, child, pos)
        
    def removeChild(self, child):
        name = child.name()
        if name not in self.names or self.names[name] is not child:
            raise Exception("Parameter %s is not my child; can't remove." % str(child))
        
        del self.names[name]
        self.childs.pop(self.childs.index(child))
        child.parentChanged(None)
        self.sigChildRemoved.emit(self, child)

    def parentChanged(self, parent):
        self._parent = parent
        self.sigParentChanged.emit(self, parent)
        
    def parent(self):
        return self._parent
        
    def remove(self):
        """Remove self from parent's child list"""
        parent = self.parent()
        if parent is None:
            raise Exception("Cannot remove; no parent.")
        parent.removeChild(self)
        

    def __iter__(self):
        for ch in self.childs:
            yield ch

    def __getitem__(self, *names):
        """Get the value of a child parameter"""
        return self.param(*names).value()

    def __setitem__(self, names, value):
        """Set the value of a child parameter"""
        if isinstance(names, basestring):
            names = (names,)
        return self.param(*names).setValue(value)

    def param(self, *names):
        """Return a child parameter. 
        Accepts the name of the child or a tuple (path, to, child)"""
        try:
            param = self.names[names[0]]
        except KeyError:
            raise Exception("Parameter %s has no child named %s" % (self.name(), names[0]))
        
        if len(names) > 1:
            return param.param(*names[1:])
        else:
            return param
        
    def __repr__(self):
        return "<%s '%s' at 0x%x>" % (self.__class__.__name__, self.name(), id(self))
       
    def _renameChild(self, child, name):
        ## Only to be called from Parameter.rename
        if name in self.names:
            return child.name()
        self.names[name] = child
        del self.names[child.name()]
        return name

    def registerItem(self, item):
        self.items[item] = None
        
       

class ParameterSet(Parameter):
    """Tree of name=value pairs (modifiable or not)
       - Value may be integer, float, string, bool, color, or list selection
       - Optionally, a custom widget may be specified for a property
       - Any number of extra columns may be added for other purposes
       - Any values may be reset to a default value
       - Parameters may be grouped / nested"""
       
    sigStateChanged = QtCore.Signal(object, object, object)  # self, param, value
    
    def __init__(self, name, params):
        Parameter.__init__(self, name=name, type='group')
        self.watchParam(self)
        for ch in params:
            self.addChild(ch)

    def watchParam(self, param):
        param.sigChildAdded.connect(self.grandchildAdded)
        param.sigChildRemoved.connect(self.grandchildRemoved)
        param.sigValueChanged.connect(self.childValueChanged)
        for ch in param:
            self.watchParam(ch)

    def unwatchParam(self, param):
        param.sigChildAdded.disconnect(self.grandchildAdded)
        param.sigChildRemoved.disconnect(self.grandchildRemoved)
        param.sigValueChanged.disconnect(self.childValueChanged)
        for ch in param:
            self.unwatchParam(ch)

    def grandchildAdded(self, parent, child):
        self.watchParam(child)
        
    def grandchildRemoved(self, parent, child):
        self.unwatchParam(child)
        
    def childValueChanged(self, val, param):
        self.sigStateChanged.emit(self, param, val)
        
    def childPath(self, child):
        path = []
        while child is not self:
            path.insert(0, child.name())
            child = child.parent()
        return path
            

class ParameterTree(TreeWidget):
    """Widget used to display or control data from a ParameterSet"""
    
    def __init__(self, parent=None):
        TreeWidget.__init__(self, parent)
        self.setAnimated(False)
        self.setColumnCount(2)
        self.setHeaderLabels(["Parameter", "Value"])
        self.setRootIsDecorated(False)
        self.setAlternatingRowColors(True)
        self.paramSet = None
        self.header().setResizeMode(QtGui.QHeaderView.ResizeToContents)
        self.itemChanged.connect(self.itemChangedEvent)
        
    def setParameters(self, paramSet, root=None, depth=0):
        if root is None:
            root = self.invisibleRootItem()
        #expand = False
        for param in paramSet:
            item = param.makeTreeItem(depth=depth)
            root.addChild(item)
            item.updateWidgets()
            self.setParameters(param, root=item, depth=depth+1)
            #expand = True
        #root.setExpanded(expand)
        
        self.paramSet = paramSet
        
    #def resizeEvent(self):
        #for col in range(self.columnCount()):
            #if self.columnWidth(col) < self.sizeHintForColumn(col):
                #self.resizeColumnToContents(0)

    def contextMenuEvent(self, ev):
        item = self.currentItem()
        if hasattr(item, 'contextMenuEvent'):
            item.contextMenuEvent(ev)
            
    def itemChangedEvent(self, item, col):
        if hasattr(item, 'columnChangedEvent'):
            item.columnChangedEvent(col)


class ParameterItem(QtGui.QTreeWidgetItem):
    def __init__(self, param, depth=0):
        self.param = param
        self.param.registerItem(self)  ## let parameter know this item is connected to it
        self.depth = depth
        name = param.name()
        QtGui.QTreeWidgetItem.__init__(self, [name, ''])
        
        
        param.sigValueChanged.connect(self.valueChanged)
        param.sigChildAdded.connect(self.childAdded)
        param.sigChildRemoved.connect(self.childRemoved)
        param.sigNameChanged.connect(self.nameChanged)
        param.sigLimitsChanged.connect(self.limitsChanged)
        self.ignoreNameColumnChange = False
        
        
        opts = param.opts
        
        self.contextMenu = QtGui.QMenu()
        self.contextMenu.addSeparator()
        flags = QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
        if opts.get('renamable', False):
            flags |= QtCore.Qt.ItemIsEditable
            self.contextMenu.addAction('Rename').triggered.connect(self.editName)
        if opts.get('removable', False):
            self.contextMenu.addAction("Remove").triggered.connect(self.param.remove)
        
        if opts.get('movable', False):
            flags |= QtCore.Qt.ItemIsDragEnabled
        if opts.get('dropEnabled', False):
            flags |= QtCore.Qt.ItemIsDropEnabled
        self.setFlags(flags)
        
        ## If this item type provides a widget, build it into column 1 with a default button.
        w = self.makeWidget()  
        if w is None:
            return

        w.setValue(opts['value'])

        if 'tip' in opts:
            w.setToolTip(opts['tip'])
        w.setObjectName(name)
        
        if opts.get('readonly', False):
            w.setEnabled(False)
        
        layout = QtGui.QHBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(2)
        layout.addWidget(w)

        self.defaultBtn = QtGui.QPushButton()
        self.defaultBtn.setFixedWidth(20)
        self.defaultBtn.setFixedHeight(20)
        #sp = self.defaultBtn.sizePolicy()
        #sp.setHorizontalPolicy(QtGui.QSizePolicy.Fixed)
        #self.defaultBtn.setSizePolicy(sp)
        #self.defaultBtn.setSizeHint(16, 16)
        modDir = os.path.dirname(__file__)
        self.defaultBtn.setIcon(QtGui.QIcon(os.path.join(modDir, 'default.png')))
        layout.addWidget(self.defaultBtn)
        self.defaultBtn.clicked.connect(self.defaultClicked)
        self.defaultBtn.setEnabled(not self.param.valueIsDefault())

        self.layoutWidget = QtGui.QWidget()
        self.layoutWidget.setLayout(layout)
        
        self.widget = w
        if w.sigChanged is not None:
            w.sigChanged.connect(self.widgetValueChanged)
            
            

    def makeWidget(self):
        """
        Return a single widget that should be placed in the second tree column.
        The widget must be given three attributes:
            sigChanged -- a signal that is emitted when the widget's value is changed
            value -- a function that returns the value
            setValue -- a function that sets the value
        This is a good function to override in subclasses.
        """
        opts = self.param.opts
        t = opts['type']
        if t == 'int':
            defs = {'value': 0, 'min': None, 'max': None, 'step': 1.0, 'minStep': 1.0, 'dec': False, 'siPrefix': False, 'suffix': ''}
            defs.update(opts)
            if 'limits' in opts:
                defs['bounds'] = opts['limits']
            w = SpinBox()
            w.setOpts(**defs)
            w.sigChanged = w.valueChanged
            #w = SpinBox()
            #if 'max' in opts:
                #w.setMaximum(opts['max'])
            #if 'min' in opts:
                #w.setMinimum(opts['min'])
            #if 'value' in opts:
                #w.setValue(opts['value'])
            #w.sigChanged = w.valueChanged
        elif t == 'float':
            defs = {'value': 0, 'min': None, 'max': None, 'step': 1.0, 'dec': False, 'siPrefix': False, 'suffix': ''}
            defs.update(opts)
            if 'limits' in opts:
                defs['bounds'] = opts['limits']
            w = SpinBox()
            w.setOpts(**defs)
            w.sigChanged = w.valueChanged
        elif t == 'bool':
            w = QtGui.QCheckBox()
            #w.setChecked(opts.get('value', False))
            w.sigChanged = w.toggled
            w.value = w.isChecked
            w.setValue = w.setChecked
        elif t == 'str':
            w = QtGui.QLineEdit()
            #w.setText(opts['value'])
            w.sigChanged = w.editingFinished
            w.value = lambda: str(w.text())
            w.setValue = w.setText
        #elif t == 'list':
            #w = QtGui.QComboBox()
            #w.setEditable(False)
            #for i in opts['values']:
                #w.addItem(str(i))
            #w.sigChanged = w.currentIndexChanged
            #w.value = w.currentIndex
            #w.setValue = w.setCurrentIndex
        #elif t == 'colormap':
            #w = ColorMapper()
        elif t == 'color':
            w = ColorButton()
            #if 'value' in opts:
                #w.setColor(opts['value'])
            w.sigChanged = w.sigColorChanged
            w.value = w.color
            w.setValue = w.setColor
        else:
            raise Exception("Unknown type '%s'" % str(t))
        return w


    def widgetValueChanged(self):
        ## called when the widget's value has been changed by the user
        val = self.widget.value()
        newVal = self.param.setValue(val)
        #if val != newVal:
            #self.valueChanged(newVal)  ## should be handled automatically.
        self.defaultBtn.setEnabled(not self.param.valueIsDefault())
            
    def valueChanged(self, val):
        ## called when the parameter's value has changed
        self.widget.sigChanged.disconnect(self.widgetValueChanged)
        try:
            if val != self.widget.value():
                self.widget.setValue(val)
        finally:
            self.widget.sigChanged.connect(self.widgetValueChanged)
        self.defaultBtn.setEnabled(not self.param.valueIsDefault())
        
    def updateWidgets(self):
        ## add all widgets for this item into the tree
        if hasattr(self, 'widget'):
            tree = self.treeWidget()
            tree.setItemWidget(self, 1, self.layoutWidget)
        self.setExpanded(self.param.opts.get('expanded', True))

    def childAdded(self, param, child, pos):
        item = child.makeTreeItem(depth=self.depth+1)
        #print "param:", param, "param item:", self, "add child:", child, "item:", item
        self.insertChild(pos, item)
        item.updateWidgets()
        
    def childRemoved(self, param, child):
        for i in range(self.childCount()):
            item = self.child(i)
            if item.param is child:
                self.takeChild(i)
                break
                
    def defaultClicked(self):
        self.param.setToDefault()

    def contextMenuEvent(self, ev):
        if not self.param.opts.get('removable', False) and not self.param.opts.get('renamable', False):
            return
            
        self.contextMenu.popup(ev.globalPos())
        
    def columnChangedEvent(self, col):
        """Called when the text in a column has been edited."""
        if col == 0:
            if self.ignoreNameColumnChange:
                return
            newName = self.param.setName(str(self.text(col)))
            try:
                self.ignoreNameColumnChange = True
                self.nameChanged(self, newName)  ## If the parameter rejects the name change, we need to set it back.
            finally:
                self.ignoreNameColumnChange = False
                
    def nameChanged(self, param, name):
        ## called when the parameter's name has changed.
        self.setText(0, name)

    def limitsChanged(self, param, limits):
        t = self.param.opts['type']
        if t == 'int' or t == 'float':
            self.widget.setOpts(bounds=limits)
        else:
            return  ## don't know what to do with any other types..
            
    def editName(self):
        self.treeWidget().editItem(self, 0)