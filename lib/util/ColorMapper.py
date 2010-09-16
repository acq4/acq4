# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
from SpinBox import SpinBox
from pyqtgraph.GradientWidget import GradientWidget
import numpy as np

class ColorMapper(QtGui.QWidget):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.layout = QtGui.QGridLayout()
        self.addBtn = QtGui.QPushButton('+')
        self.remBtn = QtGui.QPushButton('-')
        self.tree = QtGui.QTreeWidget()
        self.setLayout(self.layout)
        self.layout.addWidget(self.tree, 0, 0, 1, 2)
        self.layout.addWidget(self.addBtn, 1, 0)
        self.layout.addWidget(self.remBtn, 1, 1)
        self.layout.setSpacing(0)
        
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(['  ', 'arg', 'op', 'min', 'max', 'colors'])
        self.tree.setColumnWidth(0, 5)
        self.tree.setColumnWidth(2, 35)
        self.tree.setColumnWidth(3, 45)
        self.tree.setColumnWidth(4, 45)
        
        self.argList = []
        self.items = []
        
        self.connect(self.addBtn, QtCore.SIGNAL('clicked()'), self.addClicked)
        self.connect(self.remBtn, QtCore.SIGNAL('clicked()'), self.remClicked)
        
    def widgetGroupInterface(self):
        return (None, ColorMapper.saveState, ColorMapper.restoreState)
        
    def emitChanged(self):
        self.emit(QtCore.SIGNAL('changed'))
    
    def setArgList(self, args):
        """Sets the list of variable names available for computing colors"""
        self.argList = args
        for i in self.items:
            i.updateArgList()
        
    def getColor(self, args):
        color = np.array([0.,0.,0.,1.])
        for item in self.items:
            c = item.getColor(args)
            c = np.array([c.red(), c.green(), c.blue(), c.alpha()], dtype=float) / 255.
            op = item.getOp()
            if op == '+':
                color += c
            elif op == '*':
                color *= c
            color = np.clip(color, 0, 1.)
            #print color, c
        color = np.clip(color*255, 0, 255).astype(int)
        return QtGui.QColor(*color)

    def addClicked(self):
        self.addItem()
        self.emitChanged()
        
    def addItem(self, state=None):
        item = ColorMapperItem(self)
        self.tree.addTopLevelItem(item)
        item.postAdd()
        self.items.append(item)
        if state is not None:
            item.restoreState(state)
        
        
    def remClicked(self):
        item = self.tree.currentItem()
        if item is None:
            return
        self.remItem(item)
        self.emitChanged()

    def remItem(self, item):
        index = self.tree.indexOfTopLevelItem(item)
        self.tree.takeTopLevelItem(index)
        self.items.remove(item)

    def saveState(self):
        state = {'args': self.argList, 'items': [i.saveState() for i in self.items]}
        return state
        
    def restoreState(self, state):
        for i in self.items[:]:
            self.remItem(i)
        self.setArgList(state['args'])
        for i in state['items']:
            self.addItem(i)


class ColorMapperItem(QtGui.QTreeWidgetItem):
    def __init__(self, cm):
        self.cm = cm
        QtGui.QTreeWidgetItem.__init__(self)
        self.argCombo = QtGui.QComboBox()
        self.opCombo = QtGui.QComboBox()
        self.minSpin = SpinBox(value=0.0)
        self.maxSpin = SpinBox(value=1.0)
        self.gradient = GradientWidget()
        self.updateArgList()
        self.opCombo.addItem('+')
        self.opCombo.addItem('*')

    def postAdd(self):
        t = self.treeWidget()
        t.setItemWidget(self, 1, self.argCombo)
        t.setItemWidget(self, 2, self.opCombo)
        t.setItemWidget(self, 3, self.minSpin)
        t.setItemWidget(self, 4, self.maxSpin)
        t.setItemWidget(self, 5, self.gradient)

    def updateArgList(self):
        prev = str(self.argCombo.currentText())
        self.argCombo.clear()
        for a in self.cm.argList:
            self.argCombo.addItem(a)
            if a == prev:
                self.argCombo.setCurrentIndex(self.argCombo.count()-1)

    def getColor(self, args):
        arg = str(self.argCombo.currentText())
        val = args[arg]
        mn = self.minSpin.value()
        mx = self.maxSpin.value()
        norm = np.clip((val - mn) / (mx - mn), 0.0, 1.0)
        return self.gradient.getColor(norm)

    def getOp(self):
        return self.opCombo.currentText()

    def saveState(self):
        state = {
            'arg': str(self.argCombo.currentText()),
            'op': str(self.opCombo.currentText()),
            'min': self.minSpin.value(),
            'max': self.maxSpin.value(),
            'gradient': self.gradient.saveState()
        }
        return state
        
    def restoreState(self, state):
        ind = self.argCombo.findText(state['arg'])
        self.argCombo.setCurrentIndex(ind)
        ind = self.opCombo.findText(state['op'])
        self.opCombo.setCurrentIndex(ind)
        
        self.minSpin.setValue(state['min'])
        self.maxSpin.setValue(state['max'])

        self.gradient.restoreState(state['gradient'])

if __name__ == '__main__':
    app = QtGui.QApplication([])
    win = QtGui.QMainWindow()
    w = ColorMapper()
    win.setCentralWidget(w)
    win.show()
    win.resize(400,400)
    
    w.setArgList(['x', 'y', 'amp', 'tau'])
    #app.exec_()