# -*- coding: utf-8 -*-
if __name__ == '__main__':
    import sys
    sys.path.append('..')
    
from PyQt4 import QtCore, QtGui
import pyqtgraph as pg
from pyqtgraph import SpinBox
from pyqtgraph import GradientWidget
import numpy as np
import CMTemplate
import os
import configfile

class ColorMapper(QtGui.QWidget):
    
    sigChanged = QtCore.Signal()
    
    def __init__(self, parent=None, filePath=None):
        QtGui.QWidget.__init__(self, parent)      
        
        self.ui = CMTemplate.Ui_Form()
        self.ui.setupUi(self)
        
        
        self.ui.tree.setColumnWidth(1, 50)
        self.ui.tree.setColumnWidth(2, 60)
        self.ui.tree.setColumnWidth(3, 60)
        
        self.addBtn = QtGui.QPushButton('Add New')
        item = QtGui.QTreeWidgetItem()
        self.ui.tree.addTopLevelItem(item)
        self.ui.tree.setItemWidget(item, 0, self.addBtn)
        
        self.argList = []
        self.items = []
        self.loadedFile = None
        self.filePath = filePath
        self.deleteState = 0
        
        self.refreshFileList()
        
        self.addBtn.clicked.connect(self.addClicked)
        self.ui.saveBtn.clicked.connect(self.saveClicked)
        self.ui.fileCombo.lineEdit().editingFinished.connect(self.editDone)
        self.ui.fileCombo.setEditable(False)
        self.ui.saveAsBtn.clicked.connect(self.saveAs)
        self.ui.deleteBtn.clicked.connect(self.deleteClicked)
        self.ui.fileCombo.currentIndexChanged[int].connect(self.load)

    def event(self, event): ## This is because QComboBox does not emit the editingFinished signal when enter is pressed.
        if event.type() == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Return:
            self.editDone()
            return True
        return False
        

    def refreshFileList(self):
        combo = self.ui.fileCombo
        if self.filePath is None:
            return
        files = ["Load..."] + os.listdir(self.filePath)
        combo.blockSignals(True)
        combo.clear()
        ind = 0
        #print files
        #print self.loadedFile
        for i in range(len(files)):
            f = files[i]
            combo.addItem(f)
            if f == self.loadedFile:
                ind = i
        combo.setCurrentIndex(ind)
        combo.blockSignals(False)
        
    def load(self, ind):
        #print "Index changed to:", ind
        if ind == 0:
            return
        name = str(self.ui.fileCombo.currentText())
        file = os.path.join(self.filePath, name)
        if not os.path.isfile(file):
            return
        state = configfile.readConfigFile(file)
        self.restoreState(state)
        self.loadedFile = name

    def editDone(self):
        if self.save():
            self.ui.saveAsBtn.success("Saved.")
        else:
            self.ui.saveAsBtn.failure("Error.")
        
    def saveClicked(self):
        if self.save():
            self.ui.saveBtn.success("Saved.")
        
            
    def save(self):
        try:
            if self.ui.fileCombo.isEditable():
                #self.ui.fileCombo.lineEdit().releaseKeyboard()
                self.ui.fileCombo.setEditable(False)
    
            #print 'save clicked'
            name = str(self.ui.fileCombo.currentText())
            if name == 'Load...':
                self.saveAs()
                return
            file = os.path.join(self.filePath, name)
            #print "save:", file
            state = self.saveState()
            configfile.writeConfigFile(state, file)
            self.loadedFile = str(name)
            self.refreshFileList()
            return True
        except:
            self.ui.saveBtn.failure("Error.")
            raise
        #self.origStyle = self.ui.fileCombo.styleSheet()
        #self.ui.fileCombo.setStyleSheet("QComboBox {background-color: #0F0}")
        #QtCore.QTimer.singleShot(200, self.unblink)
        
    def saveAs(self):
        self.ui.fileCombo.currentIndexChanged[int].disconnect(self.load)
        self.ui.fileCombo.addItem("New Color Scheme")
        self.ui.fileCombo.setCurrentIndex(self.ui.fileCombo.count()-1)
        self.ui.fileCombo.setEditable(True)
        self.ui.fileCombo.lineEdit().selectAll()
        self.ui.fileCombo.lineEdit().setFocus()
        self.ui.fileCombo.currentIndexChanged[int].connect(self.load)

    #def unblink(self):
        #self.ui.fileCombo.setStyleSheet(self.origStyle)
        

    #def delete(self):
        #if self.ui.fileCombo.currentIndex() == 0:
            #return
        #file = os.path.join(self.filePath, self.loadedFile)
        ##print "delete", file
        #os.remove(file)
        #self.loadedFile = None
        #self.refreshFileList()
        
    def deleteClicked(self):
        ## Delete button must be clicked twice.
        if self.deleteState == 0:
            self.ui.deleteBtn.setText('Really?')
            self.deleteState = 1
        elif self.deleteState == 1:
            try:
                if self.ui.fileCombo.currentIndex() == 0:
                    return
                file = os.path.join(self.filePath, self.loadedFile)
                #print "delete", file
                os.remove(file)
                self.loadedFile = None
                self.refreshFileList()
            except:
                printExc('Error while deleting color scheme:')
                return
            finally:
                self.deleteState = 0
                self.ui.deleteBtn.setText('Delete')

    def widgetGroupInterface(self):
        return (None, ColorMapper.saveState, ColorMapper.restoreState)
        
    def emitChanged(self):
        #self.emit(QtCore.SIGNAL('changed'))
        self.sigChanged.emit()
    
    def setArgList(self, args):
        """Sets the list of variable names available for computing colors"""
        self.argList = args
        for i in self.items:
            i.updateArgList()
        
    def getColor(self, args):
        color = np.array([0.,0.,0.,0.])
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
    
    def getColorArray(self, data):
        colors = np.zeros(data.shape+(4,), dtype=float)
        for item in self.items:
            c = item.getColorArray(data) / 255.
            op = item.getOp()
            if op == '+':
                colors += c
            elif op == '*':
                colors *= c
            colors = np.clip(colors, 0, 1.)
        colors = np.clip(colors*255, 0, 255).astype(int)
        return colors
    
    def addClicked(self):
        self.addItem()
        self.emitChanged()
        
    def addItem(self, state=None):
        item = ColorMapperItem(self)
        self.ui.tree.insertTopLevelItem(self.ui.tree.topLevelItemCount()-1, item)
        item.postAdd()
        self.items.append(item)
        if state is not None:
            item.restoreState(state)
        
        
    def remClicked(self, item):
        #item = self.ui.tree.currentItem()
        if item is None:
            return
        self.remItem(item)
        self.emitChanged()

    def remItem(self, item):
        index = self.ui.tree.indexOfTopLevelItem(item)
        self.ui.tree.takeTopLevelItem(index)
        self.items.remove(item)

    def saveState(self):
        items = [self.ui.tree.topLevelItem(i) for i in range(self.ui.tree.topLevelItemCount()-1)]
        state = {'args': self.argList, 'items': [i.saveState() for i in items]}
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
        self.minSpin = SpinBox(value=0.0, dec=True, step=1)
        self.maxSpin = SpinBox(value=1.0, dec=True, step=1)
        self.gradient = GradientWidget()
        self.updateArgList()
        self.opCombo.addItem('+')
        self.opCombo.addItem('*')
        self.remBtn = QtGui.QPushButton('Remove')
        self.remBtn.clicked.connect(self.delete)
        
        self.minSpin.sigValueChanged.connect(self.emitChanged)
        self.maxSpin.sigValueChanged.connect(self.emitChanged)
        self.opCombo.currentIndexChanged.connect(self.emitChanged)
        self.argCombo.currentIndexChanged.connect(self.emitChanged)
        self.gradient.sigGradientChanged.connect(self.emitChanged)
        
    def emitChanged(self):
        self.cm.emitChanged()
    
    def postAdd(self):
        t = self.treeWidget()
        #self.setText(0, "-")
        t.setItemWidget(self, 0, self.argCombo)
        t.setItemWidget(self, 1, self.opCombo)
        t.setItemWidget(self, 2, self.minSpin)
        t.setItemWidget(self, 3, self.maxSpin)
        t.setItemWidget(self, 4, self.gradient)
        t.setItemWidget(self, 5, self.remBtn)
        
    def delete(self):
        self.cm.remClicked(self)

    def updateArgList(self):
        prev = str(self.argCombo.currentText())
        self.argCombo.clear()
        for a in self.cm.argList:
            self.argCombo.addItem(a)
            if a == prev:
                self.argCombo.setCurrentIndex(self.argCombo.count()-1)

    def getColor(self, args):
        arg = str(self.argCombo.currentText())
        if arg not in args:
            raise Exception('Cannot generate color; value "%s" is not present in this data.' % arg)
        val = args[arg]
        if val is None:
            raise Exception('Cannot generate color; value "%s" is empty (None).' % arg)
        mn = self.minSpin.value()
        mx = self.maxSpin.value()
        norm = np.clip((val - mn) / (mx - mn), 0.0, 1.0)
        return self.gradient.getColor(norm)

    def getColorArray(self, data):
        arg = str(self.argCombo.currentText())
        vals = data[arg]
        mn = self.minSpin.value()
        mx = self.maxSpin.value()        
        #norm = np.clip((vals - mn) / (mx - mn), 0.0, 1.0)
        return pg.makeARGB(vals, self.gradient.getLookupTable(512), levels=[mn, mx], useRGBA=True)[0]

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
    w = ColorMapper(filePath='./test')
    win.setCentralWidget(w)
    win.show()
    win.resize(400,400)
    
    w.setArgList(['x', 'y', 'amp', 'tau'])
    app.exec_()
   