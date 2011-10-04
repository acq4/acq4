from PyQt4 import QtCore, QtGui
from ParameterTree import Parameter, ParameterItem, registerParameterType


class GroupParameterItem(ParameterItem):
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
            ParameterItem.addChild(self, self.addItem)
            
    def addClicked(self):
        self.param.addNew()

    def addChanged(self):
        if self.addWidget.currentIndex() == 0:
            return
        typ = str(self.addWidget.currentText())
        self.param.addNew(typ)
        self.addWidget.setCurrentIndex(0)

    def makeWidget(self):
        return None

    def updateWidgets(self):
        ParameterItem.updateWidgets(self)
        if self.addItem is not None:
            self.treeWidget().setItemWidget(self.addItem, 0, self.addWidget)
        
    def addClicked(self):
        self.param.addNew()

    def addChild(self, child):  ## make sure added childs are actually inserted before add btn
        if self.addItem is not None:
            ParameterItem.insertChild(self, self.childCount()-1, child)
        else:
            ParameterItem.addChild(self, child)

    def valueChanged(self, val):
        pass  ## override default behavior to avoid setting text in column 1

class GroupParameter(Parameter):
    type = 'group'
    itemClass = GroupParameterItem

    def addNew(self, typ=None):
        raise Exception("Must override this function in subclass.")

registerParameterType('group', GroupParameter)





class ListParameterItem(ParameterItem):
    def __init__(self, param, depth):
        ParameterItem.__init__(self, param, depth)
        
    def makeWidget(self):
        opts = self.param.opts
        t = opts['type']
        w = QtGui.QComboBox()
        w.setMaximumHeight(20)  ## set to match height of spin box and line edit
        for k in opts['limits']:
            w.addItem(str(k))
        w.sigChanged = w.currentIndexChanged
        w.value = self.value
        w.setValue = self.setValue
        self.widget = w
        self.setValue(self.param.value())
        return w
        
    def value(self):
        vals = self.param.opts['limits']
        key = str(self.widget.currentText())
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
            key = str(val)
        ind = self.widget.findText(key)
        self.widget.setCurrentIndex(ind)

    def limitsChanged(self, param, limits):
        try:
            self.widget.blockSignals(True)
            val = str(self.widget.currentText())
            self.widget.clear()
            for k in self.param.opts['limits']:
                self.widget.addItem(str(k))
                if str(k) == val:
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
        



class ParameterSet(GroupParameter):
    """Parameter that keeps track of every item in its tree, emitting signals when anything changes."""
    sigStateChanged = QtCore.Signal(object, object, object)  # self, param, value
    
    def __init__(self, name, params):
        GroupParameter.__init__(self, name=name, type='group')
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
