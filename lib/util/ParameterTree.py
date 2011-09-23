if __name__ == '__main__':
    import sys,os
    md = os.path.dirname(__file__)
    sys.path.append(md)
    sys.path.append(os.path.join('..', '..', md))
    
from PyQt4 import QtCore, QtGui
from TreeWidget import TreeWidget
from SpinBox import SpinBox
from pyqtgraph.ColorButton import ColorButton
import collections

class Parameter(QtCore.QObject):
    ## name, type, limits, etc.
    ## can also carry UI hints (slider vs spinbox, etc.)
    sigValueChanged = QtCore.Signal(object, object)  ## value, self
    sigChildAdded = QtCore.Signal(object, object, object)  ## self, child, index
    sigChildRemoved = QtCore.Signal(object, object)  ## self, child
    sigParentChanged = QtCore.Signal(object, object)  ## self, parent
    
    def __init__(self, **opts):
        QtCore.QObject.__init__(self)
        self.opts = opts
        self.childs = []
        self.names = {}
        self._parent = None
        
        if 'name' not in opts or not isinstance(opts['name'], basestring):
            raise Exception("Parameter must have a string name specified in opts.")
        
        for chOpts in opts.get('params', []):
            self.addChild(Parameter(**chOpts))
        
    def name(self):
        return self.opts['name']
    
    def setValue(self, value):
        ## return the actual value that was set
        ## (this may be different from the value that was requested)
        self.opts['value'] = value
        self.sigValueChanged.emit(value, self)
        return value

    def value(self):
        return self.opts['value']

    def addChild(self, child):
        self.insertChild(len(self.childs), child)
        
    def insertChild(self, pos, child):
        """Insert a new child at pos.
        If pos is a Parameter, then insert at the position of that Parameter."""
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

    def __getitem__(self, name):
        """Get the value of a child parameter"""
        return self.param(name).value()

    def __setitem__(self, name, value):
        """Set the value of a child parameter"""
        return self.param(name).setValue(value)

    def param(self, name):
        """Return a child parameter. 
        Accepts the name of the child or a tuple (path, to, child)"""
        
        if isinstance(name, tuple):
            if len(name) == 1:
                name = name[0]
            else:
                return self.names[name[0]][name[1:]]
        return self.names[name]
        
    def __repr__(self):
        return "<%s '%s' at 0x%x>" % (self.__class__.__name__, self.name(), id(self))
        

class ParameterSet(Parameter):
    """Tree of name=value pairs (modifiable or not)
       - Value may be integer, float, string, bool, color, or list selection
       - Optionally, a custom widget may be specified for a property
       - Any number of extra columns may be added for other purposes
       - Any values may be reset to a default value
       - Parameters may be grouped / nested"""
       
    sigStateChanged = QtCore.Signal(object)
    
    def __init__(self, name, params):
        Parameter.__init__(self, name=name, type='group')
        self.watchParam(self)
        for ch in params:
            self.addChild(Parameter(**ch))

    def getValues(self):
        pass
    
    def saveState(self):
        pass
    
    def watchParam(self, param):
        param.sigChildAdded.connect(self.watchParam)
        param.sigChildRemoved.connect(self.unwatchParam)
        param.sigValueChanged.connect(self.childValueChanged)
        for ch in param:
            self.watchParam(ch)

    def unwatchParam(self, param):
        param.sigChildAdded.disconnect(self.watchParam)
        param.sigChildRemoved.disconnect(self.unwatchParam)
        param.sigValueChanged.disconnect(self.childValueChanged)
        for ch in param:
            self.unwatchParam(ch)

    def childValueChanged(self, val, param):
        print "Changed: %s = %s" % (str(self.childPath(param)), str(val))
        
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
        self.setColumnCount(2)
        self.setHeaderLabels(["Parameter", "Value"])
        self.setRootIsDecorated(False)
        self.setAlternatingRowColors(True)
        
    def setParameters(self, paramSet, root=None, depth=0):
        if root is None:
            root = self.invisibleRootItem()
        expand = False
        for param in paramSet:
            item = ParameterItem(param, depth=depth)
            root.addChild(item)
            item.updateWidgets(self)
            self.setParameters(param, root=item, depth=depth+1)
            expand = True
        root.setExpanded(expand)



class ParameterItem(QtGui.QTreeWidgetItem):
    def __init__(self, param, depth=0):
        self.param = param
        name = param.name()
        QtGui.QTreeWidgetItem.__init__(self, [name, ''])
        
        param.sigValueChanged.connect(self.valueChanged)
        
        opts = param.opts
        t = opts['type']
        if t == 'group':
            if depth == 0:
                for c in [0,1]:
                    self.setBackground(c, QtGui.QBrush(QtGui.QColor(100,100,100)))
                    self.setForeground(c, QtGui.QBrush(QtGui.QColor(220,220,255)))
                    font = self.font(c)
                    font.setBold(True)
                    font.setPointSize(font.pointSize()+1)
                    self.setFont(c, font)
                    self.setSizeHint(0, QtCore.QSize(0, 25))
            else:
                for c in [0,1]:
                    self.setBackground(c, QtGui.QBrush(QtGui.QColor(220,220,220)))
                    font = self.font(c)
                    font.setBold(True)
                    #font.setPointSize(font.pointSize()+1)
                    self.setFont(c, font)
                    self.setSizeHint(0, QtCore.QSize(0, 20))
            return
        
        elif t == 'int':
            w = QtGui.QSpinBox()
            if 'max' in opts:
                w.setMaximum(opts['max'])
            if 'min' in opts:
                w.setMinimum(opts['min'])
            if 'value' in opts:
                w.setValue(opts['value'])
            w.sigChanged = w.valueChanged
        elif t == 'float':
            defs = {'value': 0, 'min': None, 'max': None, 'step': 1.0, 'dec': False, 'siPrefix': False, 'suffix': ''}
            defs.update(opts)
            w = SpinBox()
            w.setOpts(**defs)
            w.sigChanged = w.valueChanged
        elif t == 'bool':
            w = QtGui.QCheckBox()
            w.setChecked(opts.get('value', False))
            w.sigChanged = w.toggled
            w.value = w.isChecked
            w.setValue = w.setChecked
        elif t == 'str':
            w = QtGui.QLineEdit()
            w.setText(opts['value'])
            w.sigChanged = w.editingFinished
            w.value = w.text
            w.setValue = w.setText
        elif t == 'list':
            w = QtGui.QComboBox()
            w.setEditable(False)
            for i in opts['values']:
                w.addItem(str(i))
            w.sigChanged = w.currentIndexChanged
            w.value = w.currentIndex
            w.setValue = w.setCurrentIndex
        #elif t == 'colormap':
            #w = ColorMapper()
        elif t == 'color':
            w = ColorButton()
            if 'value' in opts:
                w.setColor(opts['value'])
            w.sigChanged = w.sigColorChanged
            w.value = w.color
            w.setValue = w.setColor
        else:
            raise Exception("Unknown type '%s'" % str(t))
        
        if 'tip' in opts:
            w.setToolTip(opts['tip'])
        w.setObjectName(name)
        
        #w.setFrame(False)
        #l.addRow(k, w)
        #if o.get('hidden', False):
            #w.hide()
            #label = l.labelForField(w)
            #label.hide()
            
        #ctrls[k] = w
        #w.rowNum = row
        #row += 1
        
        self.widget = w
        w.sigChanged.connect(self.widgetValueChanged)
        
        
        
    def widgetValueChanged(self):
        ## called when the widget's value has been changed by the user
        val = self.widget.value()
        newVal = self.param.setValue(val)
        if val != newVal:
            self.valueChanged(newVal)
            
    def valueChanged(self, val):
        ## called when the parameter's value has changed
        self.widget.sigChanged.disconnect(self.widgetValueChanged)
        try:
            self.widget.setValue(val)
        finally:
            self.widget.sigChanged.connect(self.widgetValueChanged)
        
    def updateWidgets(self, tree):
        ## add all widgets for this item into the tree
        if hasattr(self, 'widget'):
            tree.setItemWidget(self, 1, self.widget)



if __name__ == '__main__':
    import collections
    app = QtGui.QApplication([])
    params = [
        {'name': 'Group 0', 'type': 'group', 'params': [
            {'name': 'Param 1', 'type': 'int', 'value': 10},
            {'name': 'Param 2', 'type': 'float', 'value': 10},
        ]},
        {'name': 'Group 1', 'type': 'group', 'params': [
            {'name': 'Param 1.1', 'type': 'float', 'value': 1.2e-6, 'dec': True, 'siPrefix': True, 'suffix': 'V'},
            {'name': 'Param 1.2', 'type': 'float', 'value': 1.2e6, 'dec': True, 'siPrefix': True, 'suffix': 'Hz'},
            {'name': 'Group 1.3', 'type': 'group', 'params': [
                {'name': 'Param 1.3.1', 'type': 'int', 'value': 11, 'max': 15, 'min': -7},
                {'name': 'Param 1.3.2', 'type': 'float', 'value': 1.2e6, 'dec': True, 'siPrefix': True, 'suffix': 'Hz'},
            ]},
            {'name': 'Param 1.4', 'type': 'str', 'value': "hi"},
            {'name': 'Param 1.5', 'type': 'list', 'values': [1,2,3]},
        ]},
        {'name': 'Param 5', 'type': 'bool', 'value': True, 'tip': "This is a checkbox"},
        {'name': 'Param 6', 'type': 'color', 'value': "FF0", 'tip': "This is a checkbox"},
    ]
    
    p = ParameterSet("params", params)
    
    t = ParameterTree()
    t.setParameters(p)
    t.show()
    t.resize(400,600)
    
    