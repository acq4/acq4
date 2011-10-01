from PyQt4 import QtCore, QtGui
from ParameterTree import Parameter, ParameterItem, registerParameterType

class ListParameterItem(ParameterItem):
    def __init__(self, param, depth):
        ParameterItem.__init__(self, param, depth)
        
    def makeWidget(self):
        opts = self.param.opts
        t = opts['type']
        w = QtGui.QComboBox()
        for k in opts['values']:
            w.addItem(str(k))
        w.sigChanged = w.currentIndexChanged
        w.value = self.value
        w.setValue = self.setValue
        self.widget = w
        self.setValue(self.param.value())
        return w
        
    def value(self):
        vals = self.param.opts['values']
        key = str(self.widget.currentText())
        if isinstance(vals, dict):
            return vals[key]
        else:
            return key
            
    def setValue(self, val):
        vals = self.param.opts['values']
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
        
class ListParameter(Parameter):
    type = 'list'
    itemClass = ListParameterItem

registerParameterType('list', ListParameter)
        

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
        
    def makeWidget(self):
        return None

class GroupParameter(Parameter):
    type = 'group'
    itemClass = GroupParameterItem

registerParameterType('group', GroupParameter)

