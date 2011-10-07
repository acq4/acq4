from PyQt4 import QtCore, QtGui
from TreeWidget import TreeWidget
from SpinBox import SpinBox
from pyqtgraph.ColorButton import ColorButton
import collections, os, weakref, re
#import functions as fn

PARAM_TYPES = {}


def registerParameterType(name, cls):
    global PARAM_TYPES
    PARAM_TYPES[name] = cls

class Parameter(QtCore.QObject):
    """Tree of name=value pairs (modifiable or not)
       - Value may be integer, float, string, bool, color, or list selection
       - Optionally, a custom widget may be specified for a property
       - Any number of extra columns may be added for other purposes
       - Any values may be reset to a default value
       - Parameters may be grouped / nested"""
    ## name, type, limits, etc.
    ## can also carry UI hints (slider vs spinbox, etc.)
    
    sigValueChanged = QtCore.Signal(object, object)  ## value, self
    sigChildAdded = QtCore.Signal(object, object, object)  ## self, child, index
    sigChildRemoved = QtCore.Signal(object, object)  ## self, child
    sigParentChanged = QtCore.Signal(object, object)  ## self, parent
    sigLimitsChanged = QtCore.Signal(object, object)  ## self, limits
    sigNameChanged = QtCore.Signal(object, object)  ## self, name
    sigOptionsChanged = QtCore.Signal(object, object)  ## self, {opt:val, ...}
    
    
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
    
    def setValue(self, value, blockSignal=None):
        ## return the actual value that was set
        ## (this may be different from the value that was requested)
        #print self, "Set value:", value, self.opts['value'], self.opts['value'] == value
        try:
            if blockSignal is not None:
                self.sigValueChanged.disconnect(blockSignal)
            if self.opts['value'] == value:
                return value
            self.opts['value'] = value
            self.sigValueChanged.emit(value, self)
        finally:
            if blockSignal is not None:
                self.sigValueChanged.connect(blockSignal)
            
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


    def setOpts(self, **opts):
        """For setting any arbitrary options."""
        changed = collections.OrderedDict()
        for k in opts:
            if k == 'value':
                self.setValue(opts[k])
            elif k == 'name':
                self.setName(opts[k])
            elif k == 'limits':
                self.setLimits(opts[k])
            elif k == 'default':
                self.setDefault(opts[k])
            elif k not in self.opts or self.opts[k] != opts[k]:
                self.opts[k] = opts[k]
                changed[k] = opts[k]
                
        if len(changed) > 0:
            self.sigOptionsChanged.emit(self, changed)
        

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
            if child.opts.get('autoIncrementName', False):
                name = self.incrementName(name)
                child.setName(name)
            else:
                raise Exception("Already have child named %s" % str(name))
        if isinstance(pos, Parameter):
            pos = self.childs.index(pos)
            
        if child.parent() is not None:
            child.remove()
            
        self.names[name] = child
        self.childs.insert(pos, child)
        
        child.parentChanged(self)
        self.sigChildAdded.emit(self, child, pos)
        
        return child
        
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

    def incrementName(self, name):
        ## return an unused name by adding a number to the name given
        base, num = re.match('(.*)(\d*)', name).groups()
        numLen = len(num)
        if numLen == 0:
            num = 2
            numLen = 1
        else:
            num = int(num)
        while True:
            newName = base + ("%%0%dd"%numLen) % num
            if newName not in self.childs:
                return newName
            num += 1

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
       
    def __getattr__(self, attr):
        try:
            return self.param(attr)
        except KeyError:
            raise AttributeError(attr)
       
    def _renameChild(self, child, name):
        ## Only to be called from Parameter.rename
        if name in self.names:
            return child.name()
        self.names[name] = child
        del self.names[child.name()]
        return name

    def registerItem(self, item):
        self.items[item] = None
        
    def hide(self):
        self.show(False)
        
    def show(self, s=True):
        self.opts['visible'] = s
        self.sigOptionsChanged.emit(self, {'visible': s})

            

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
        self.lastSel = None
        self.setRootIsDecorated(False)
        
    def setParameters(self, param, root=None, depth=0, showTop=True):
        item = param.makeTreeItem(depth=depth)
        if root is None:
            root = self.invisibleRootItem()
            ## Hide top-level item
            if not showTop:
                item.setSizeHint(0, QtCore.QSize(0,0))
                item.setSizeHint(1, QtCore.QSize(0,0))
                depth -= 1
        root.addChild(item)
        item.updateWidgets()
            
        #expand = False
        for ch in param:
            #item = param.makeTreeItem(depth=depth)
            #root.addChild(item)
            #item.updateWidgets()
            self.setParameters(ch, root=item, depth=depth+1)
            #expand = True
        #root.setExpanded(expand)
        
        #self.paramSet = param
        
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
            
    def selectionChanged(self, *args):
        sel = self.selectedItems()
        if len(sel) != 1:
            sel = None
        if self.lastSel is not None:
            self.lastSel.selected(False)
        if sel is None:
            self.lastSel = None
            return
        self.lastSel = sel[0]
        if hasattr(sel[0], 'selected'):
            sel[0].selected(True)
        return TreeWidget.selectionChanged(self, *args)
        


class ParameterItem(QtGui.QTreeWidgetItem):
    def __init__(self, param, depth=0):
        self.param = param
        self.param.registerItem(self)  ## let parameter know this item is connected to it (for debugging)
        self.depth = depth
        self.hideWidget = True  ## hide edit widget, replace with label when not selected
        name = param.name()
        QtGui.QTreeWidgetItem.__init__(self, [name, ''])
        
        
        param.sigValueChanged.connect(self.valueChanged)
        param.sigChildAdded.connect(self.childAdded)
        param.sigChildRemoved.connect(self.childRemoved)
        param.sigNameChanged.connect(self.nameChanged)
        param.sigLimitsChanged.connect(self.limitsChanged)
        param.sigOptionsChanged.connect(self.optsChanged)
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
        self.widget = w
        if w is None:
            return

        if 'tip' in opts:
            w.setToolTip(opts['tip'])
        w.setObjectName(name)
        
        if opts.get('readonly', False):
            w.setEnabled(False)
        
        self.defaultBtn = QtGui.QPushButton()
        self.defaultBtn.setFixedWidth(20)
        self.defaultBtn.setFixedHeight(20)
        modDir = os.path.dirname(__file__)
        self.defaultBtn.setIcon(QtGui.QIcon(os.path.join(modDir, 'default.png')))
        self.defaultBtn.clicked.connect(self.defaultClicked)
        self.defaultBtn.setEnabled(not self.param.valueIsDefault())

        self.displayLabel = QtGui.QLabel()

        layout = QtGui.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(w)
        layout.addWidget(self.displayLabel)
        layout.addWidget(self.defaultBtn)
        self.layoutWidget = QtGui.QWidget()
        self.layoutWidget.setLayout(layout)
        
        if w.sigChanged is not None:
            w.sigChanged.connect(self.widgetValueChanged)
            
        self.valueChanged(opts['value'], force=True)
            

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
            w.sigChanged = w.sigValueChanging
        elif t == 'float':
            defs = {'value': 0, 'min': None, 'max': None, 'step': 1.0, 'dec': False, 'siPrefix': False, 'suffix': ''}
            defs.update(opts)
            if 'limits' in opts:
                defs['bounds'] = opts['limits']
            w = SpinBox()
            w.setOpts(**defs)
            w.sigChanged = w.sigValueChanging
        elif t == 'bool':
            w = QtGui.QCheckBox()
            w.sigChanged = w.toggled
            w.value = w.isChecked
            w.setValue = w.setChecked
            self.hideWidget = False
        elif t == 'str':
            w = QtGui.QLineEdit()
            w.sigChanged = w.editingFinished
            w.value = lambda: str(w.text())
            w.setValue = lambda v: w.setText(str(v))
        elif t == 'color':
            w = ColorButton()
            w.sigChanged = w.sigColorChanged
            w.value = w.color
            w.setValue = w.setColor
            self.hideWidget = False
            w.setFlat(True)
        else:
            raise Exception("Unknown type '%s'" % str(t))
        return w


    def widgetValueChanged(self):
        ## called when the widget's value has been changed by the user
        val = self.widget.value()
        newVal = self.param.setValue(val)
        self.defaultBtn.setEnabled(not self.param.valueIsDefault())
            
    def valueChanged(self, val, force=False):
        ## called when the parameter's value has changed
        self.widget.sigChanged.disconnect(self.widgetValueChanged)
        try:
            if force or val != self.widget.value():
                self.widget.setValue(val)
                self.updateDisplayLabel(val)
        finally:
            self.widget.sigChanged.connect(self.widgetValueChanged)
        self.defaultBtn.setEnabled(not self.param.valueIsDefault())

    def updateDisplayLabel(self, value=None):
        if value is None:
            value = self.param.value()
        opts = self.param.opts
        if isinstance(self.widget, QtGui.QAbstractSpinBox):
            text = unicode(self.widget.lineEdit().text())
        elif isinstance(self.widget, QtGui.QComboBox):
            text = self.widget.currentText()
        else:
            text = str(value)
        self.displayLabel.setText(text)

    def updateWidgets(self):
        ## add all widgets for this item into the tree
        if self.widget is not None:
            tree = self.treeWidget()
            tree.setItemWidget(self, 1, self.layoutWidget)
            self.displayLabel.hide()
            self.selected(False)            
        self.setHidden(not self.param.opts.get('visible', True))
        self.setExpanded(self.param.opts.get('expanded', True))
        
    def childAdded(self, param, child, pos):
        item = child.makeTreeItem(depth=self.depth+1)
        self.insertChild(pos, item)
        item.updateWidgets()
        
        for i, ch in enumerate(child):
            item.childAdded(child, ch, i)
        
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

    def optsChanged(self, param, opts):
        ## called when any options are changed that are not
        ## name, value, default, or limits
        #print opts
        if 'visible' in opts:
            self.setHidden(not opts['visible'])
        
        
        if isinstance(self.widget, SpinBox):
            self.widget.setOpts(**opts)
            self.updateDisplayLabel()

    def editName(self):
        self.treeWidget().editItem(self, 0)
        
    def selected(self, sel):
        if self.widget is None:
            return
        if sel:
            self.widget.show()
            self.displayLabel.hide()
        elif self.hideWidget:
            self.widget.hide()
            self.displayLabel.show()




