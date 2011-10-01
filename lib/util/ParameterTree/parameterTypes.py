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
        

