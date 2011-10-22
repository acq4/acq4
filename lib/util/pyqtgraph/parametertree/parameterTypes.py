from PyQt4 import QtCore, QtGui
from Parameter import Parameter, registerParameterType
from ParameterItem import ParameterItem
from pyqtgraph.SpinBox import SpinBox
from pyqtgraph.ColorButton import ColorButton
import os

class WidgetParameterItem(ParameterItem):
    """
    ParameterTree item with:
        - label in second column for displaying value
        - simple widget for editing value (displayed instead of label when item is selected)
        - button that resets value to default
        - provides SpinBox, CheckBox, LineEdit, and ColorButton types
    This class can be subclassed by overriding makeWidget() to provide a custom widget.
    """
    def __init__(self, param, depth):
        ParameterItem.__init__(self, param, depth)
        
        self.hideWidget = True  ## hide edit widget, replace with label when not selected
                                ## set this to False to keep the editor widget always visible


        ## build widget into column 1 with a display label and default button.
        w = self.makeWidget()  
        self.widget = w

        opts = self.param.opts
        if 'tip' in opts:
            w.setToolTip(opts['tip'])
        #w.setObjectName(name)
        
        ## now we just avoid displaying the widget
        #if opts.get('readonly', False):
            #w.setEnabled(False)
        
        self.defaultBtn = QtGui.QPushButton()
        self.defaultBtn.setFixedWidth(20)
        self.defaultBtn.setFixedHeight(20)
        modDir = os.path.dirname(__file__)
        self.defaultBtn.setIcon(QtGui.QIcon(os.path.join(modDir, 'default.png')))
        self.defaultBtn.clicked.connect(self.defaultClicked)
        #self.defaultBtn.setEnabled(not self.param.valueIsDefault() )  ## handled in setValue

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
            
        ## update value shown in widget. 
        self.valueChanged(self, opts['value'], force=True)


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
            defs = {
                'value': 0, 'min': None, 'max': None, 'int': True, 
                'step': 1.0, 'minStep': 1.0, 'dec': False, 
                'siPrefix': False, 'suffix': ''
            } 
            defs.update(opts)
            if 'limits' in opts:
                defs['bounds'] = opts['limits']
            w = SpinBox()
            w.setOpts(**defs)
            w.sigChanged = w.sigValueChanging
        elif t == 'float':
            defs = {
                'value': 0, 'min': None, 'max': None, 
                'step': 1.0, 'dec': False, 
                'siPrefix': False, 'suffix': ''
            }
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
            w.value = lambda: unicode(w.text())
            w.setValue = lambda v: w.setText(unicode(v))
        elif t == 'color':
            w = ColorButton()
            w.sigChanged = w.sigColorChanged
            w.value = w.color
            w.setValue = w.setColor
            self.hideWidget = False
            w.setFlat(True)
        else:
            raise Exception("Unknown type '%s'" % unicode(t))
        return w

    def valueChanged(self, param, val, force=False):
        ## called when the parameter's value has changed
        ParameterItem.valueChanged(self, param, val)
        
        self.widget.sigChanged.disconnect(self.widgetValueChanged)
        try:
            if force or val != self.widget.value():
                self.widget.setValue(val)
            self.updateDisplayLabel(val)  ## always make sure label is updated, even if values match!
        finally:
            self.widget.sigChanged.connect(self.widgetValueChanged)
        self.defaultBtn.setEnabled(not self.param.valueIsDefault() and self.param.writable())

    def updateDisplayLabel(self, value=None):
        """Update the display label to reflect the value of the parameter."""
        if value is None:
            value = self.param.value()
        opts = self.param.opts
        if isinstance(self.widget, QtGui.QAbstractSpinBox):
            text = unicode(self.widget.lineEdit().text())
        elif isinstance(self.widget, QtGui.QComboBox):
            text = self.widget.currentText()
        else:
            text = unicode(value)
        self.displayLabel.setText(text)

    def widgetValueChanged(self):
        ## called when the widget's value has been changed by the user
        val = self.widget.value()
        newVal = self.param.setValue(val)
        ## do we need this?
        #self.defaultBtn.setEnabled(not self.param.valueIsDefault() and self.param.writable())
    
    def selected(self, sel):
        """Called when this item has been selected (sel=True) OR deselected (sel=False)"""
        ParameterItem.selected(self, sel)
        
        if self.widget is None:
            return
        if sel and self.param.writable():
            self.widget.show()
            self.displayLabel.hide()
        elif self.hideWidget:
            self.widget.hide()
            self.displayLabel.show()

    def limitsChanged(self, param, limits):
        """Called when the parameter's limits have changed"""
        ParameterTree.limitsChanged(self, param, limits)
        
        t = self.param.opts['type']
        if t == 'int' or t == 'float':
            self.widget.setOpts(bounds=limits)
        else:
            return  ## don't know what to do with any other types..

    def treeChanged(self):
        """Called when this item is added or removed from a tree."""
        ParameterItem.treeChanged(self)
        
        ## add all widgets for this item into the tree
        if self.widget is not None:
            tree = self.treeWidget()
            tree.setItemWidget(self, 1, self.layoutWidget)
            self.displayLabel.hide()
            self.selected(False)            

    def defaultClicked(self):
        self.param.setToDefault()

    def optsChanged(self, param, opts):
        """Called when any options are changed that are not
        name, value, default, or limits"""
        ParameterItem.optsChanged(self, param, opts)
        
        ## If widget is a SpinBox, pass options straight through
        if isinstance(self.widget, SpinBox):
            if 'units' in opts and 'suffix' not in opts:
                opts['suffix'] = opts['units']
            self.widget.setOpts(**opts)
            self.updateDisplayLabel()

class SimpleParameter(Parameter):
    itemClass = WidgetParameterItem
    
registerParameterType('int', SimpleParameter)
registerParameterType('float', SimpleParameter)
registerParameterType('bool', SimpleParameter)
registerParameterType('str', SimpleParameter)
registerParameterType('color', SimpleParameter)




class GroupParameterItem(ParameterItem):
    """
    Group parameters are used mainly as a generic parent item that holds (and groups!) a set
    of child parameters. It also provides a simple mechanism for displaying a button or combo
    that can be used to add new parameters to the group.
    """
    def __init__(self, param, depth):
        ParameterItem.__init__(self, param, depth)
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
                
        self.addItem = None
        if 'addText' in param.opts:
            addText = param.opts['addText']
            if 'addList' in param.opts:
                self.addWidget = QtGui.QComboBox()
                self.addWidget.addItem(addText)
                for t in param.opts['addList']:
                    self.addWidget.addItem(t)
                self.addWidget.currentIndexChanged.connect(self.addChanged)
            else:
                self.addWidget = QtGui.QPushButton(addText)
                self.addWidget.clicked.connect(self.addClicked)
            self.addItem = QtGui.QTreeWidgetItem([])
            self.addItem.setFlags(QtCore.Qt.ItemIsEnabled)
            ParameterItem.addChild(self, self.addItem)
            
    def addClicked(self):
        """Called when "add new" button is clicked
        The parameter MUST have an 'addNew' method defined.
        """
        self.param.addNew()

    def addChanged(self):
        """Called when "add new" combo is changed
        The parameter MUST have an 'addNew' method defined.
        """
        if self.addWidget.currentIndex() == 0:
            return
        typ = unicode(self.addWidget.currentText())
        self.param.addNew(typ)
        self.addWidget.setCurrentIndex(0)

    def treeChanged(self):
        ParameterItem.treeChanged(self)
        if self.addItem is not None:
            self.treeWidget().setItemWidget(self.addItem, 0, self.addWidget)
        
    def addChild(self, child):  ## make sure added childs are actually inserted before add btn
        if self.addItem is not None:
            ParameterItem.insertChild(self, self.childCount()-1, child)
        else:
            ParameterItem.addChild(self, child)

class GroupParameter(Parameter):
    """
    Group parameters are used mainly as a generic parent item that holds (and groups!) a set
    of child parameters. It also provides a simple mechanism for displaying a button or combo
    that can be used to add new parameters to the group.
    """
    type = 'group'
    itemClass = GroupParameterItem

    def addNew(self, typ=None):
        raise Exception("Must override this function in subclass.")

registerParameterType('group', GroupParameter)





class ListParameterItem(WidgetParameterItem):
    """
    WidgetParameterItem subclass providing comboBox that lets the user select from a list of options.
    
    """
    def __init__(self, param, depth):
        WidgetParameterItem.__init__(self, param, depth)
        
    def makeWidget(self):
        opts = self.param.opts
        t = opts['type']
        w = QtGui.QComboBox()
        w.setMaximumHeight(20)  ## set to match height of spin box and line edit
        for k in opts['limits']:
            w.addItem(unicode(k))
        w.sigChanged = w.currentIndexChanged
        w.value = self.value
        w.setValue = self.setValue
        self.widget = w
        self.setValue(self.param.value())
        return w
        
    def value(self):
        vals = self.param.opts['limits']
        key = unicode(self.widget.currentText())
        if isinstance(vals, dict):
            return vals[key]
        else:
            return key
            
    def setValue(self, val):
        vals = self.param.opts['limits']
        if isinstance(vals, dict):
            key = None
            for k,v in vals.iteritems():
                if v == val:
                    key = k
            if key is None:
                raise Exception("Value '%s' not allowed." % val)
        else:
            key = unicode(val)
        ind = self.widget.findText(key)
        self.widget.setCurrentIndex(ind)

    def limitsChanged(self, param, limits):
        try:
            self.widget.blockSignals(True)
            val = unicode(self.widget.currentText())
            self.widget.clear()
            for k in self.param.opts['limits']:
                self.widget.addItem(unicode(k))
                if unicode(k) == val:
                    self.widget.setCurrentIndex(self.widget.count()-1)
            
        finally:
            self.widget.blockSignals(False)
            


class ListParameter(Parameter):
    type = 'list'
    itemClass = ListParameterItem

    def __init__(self, **opts):
        if 'values' in opts:
            opts['limits'] = opts['values']
        Parameter.__init__(self, **opts)

registerParameterType('list', ListParameter)
        


