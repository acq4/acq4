# -*- coding: utf-8 -*-
from __future__ import print_function
if __name__ == '__main__':
    import sys
    sys.path.append('..')
    
from acq4.util import Qt
import acq4.pyqtgraph as pg
from acq4.pyqtgraph import SpinBox
from acq4.pyqtgraph import GradientWidget
import numpy as np
from . import CMTemplate
import os
import acq4.util.configfile as configfile

class ColorMapper(Qt.QWidget):
    
    sigChanged = Qt.Signal()
    
    def __init__(self, parent=None, filePath=None):
        Qt.QWidget.__init__(self, parent)      
        self._signalBlock = 0
        self.ui = CMTemplate.Ui_Form()
        self.ui.setupUi(self)
        
        
        self.ui.tree.setColumnWidth(1, 50)
        self.ui.tree.setColumnWidth(2, 60)
        self.ui.tree.setColumnWidth(3, 60)
        
        self.addBtn = Qt.QPushButton('Add New')
        item = Qt.QTreeWidgetItem()
        self.ui.tree.addTopLevelItem(item)
        self.ui.tree.setItemWidget(item, 0, self.addBtn)
        
        self._argList = []
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

    def blockSignals(self, b):
        self._signalBlock += 1 if b else -1
        Qt.QWidget.blockSignals(self, self._signalBlock > 0)
        
    def event(self, event): ## This is because QComboBox does not emit the editingFinished signal when enter is pressed.
        if event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_Return:
            self.editDone()
            return True
        return False
        

    def refreshFileList(self):
        combo = self.ui.fileCombo
        if self.filePath is None:
            return
        files = ["Load..."]
        if os.path.isdir(self.filePath):
            files += os.listdir(self.filePath)
        
        combo.blockSignals(True)
        try:
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
        finally:
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
        #Qt.QTimer.singleShot(200, self.unblink)
        
    def saveAs(self):
        self.ui.fileCombo.blockSignals(True)
        try:
            self.ui.fileCombo.addItem("New Color Scheme")
            self.ui.fileCombo.setCurrentIndex(self.ui.fileCombo.count()-1)
            self.ui.fileCombo.setEditable(True)
            self.ui.fileCombo.lineEdit().selectAll()
            self.ui.fileCombo.lineEdit().setFocus()
        finally:
            self.ui.fileCombo.blockSignals(False)

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
        #self.emit(Qt.SIGNAL('changed'))
        self.sigChanged.emit()
    
    def setArgList(self, args):
        """Sets the list of variable names available for computing colors"""
        self._argList = args
        prev = []
        try:
            self.blockSignals(True)
            for i in self.items:
                prev.append(i.getParamName())
                i.updateArgList()
        finally:
            self.blockSignals(False)
        current = [i.getParamName() for i in self.items]
        
        if current != prev:
            self.emitChanged()
            
    def getArgList(self):
        return self._argList
        
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
        return Qt.QColor(*color)
    
    def getColorArray(self, data, opengl=False):
        """
        Given a record array, return an array of colors with the same dimensions.
        Returns ubyte format by default; use opengl=True to return float32 0.0-1.0.
        
        """
        colors = np.zeros(data.shape+(4,), dtype=np.float32)
        for item in self.items:
            c = item.getColorArray(data) / 255.
            op = item.getOp()
            if op == '+':
                colors += c
            elif op == '*':
                colors *= c
            colors = np.clip(colors, 0, 1.)
        if not opengl:
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
        state = {'args': self.getArgList(), 'items': [i.saveState() for i in items]}
        return state
        
    def restoreState(self, state):
        self.blockSignals(True)
        try:
            for i in self.items[:]:
                self.remItem(i)
            self.setArgList(state['args'])
            for i in state['items']:
                self.addItem(i)
        finally:
            self.blockSignals(False)
        self.sigChanged.emit()


class ColorMapperItem(Qt.QTreeWidgetItem):
    
    
    def __init__(self, cm):
        self.cm = cm
        Qt.QTreeWidgetItem.__init__(self)
        self.argCombo = pg.ComboBox()
        self.opCombo = pg.ComboBox()
        self.minSpin = SpinBox(value=0.0, dec=True, step=1)
        self.maxSpin = SpinBox(value=1.0, dec=True, step=1)
        self.gradient = GradientWidget()
        self.updateArgList()
        self.opCombo.addItem('+')
        self.opCombo.addItem('*')
        self.remBtn = Qt.QPushButton('Remove')
        self.remBtn.clicked.connect(self.delete)
        
        self.minSpin.sigValueChanged.connect(self.emitChanged)
        self.maxSpin.sigValueChanged.connect(self.emitChanged)
        self.opCombo.currentIndexChanged.connect(self.emitChanged)
        self.argCombo.currentIndexChanged.connect(self.emitChanged)
        self.gradient.sigGradientChangeFinished.connect(self.emitChanged)
        
    def getParamName(self):
        return str(self.argCombo.currentText())
        
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
        #prev = str(self.argCombo.currentText())
        #self.argCombo.clear()
        #for a in self.cm.argList:
            #self.argCombo.addItem(a)
            #if a == prev:
                #self.argCombo.setCurrentIndex(self.argCombo.count()-1)
        self.argCombo.updateList(self.cm.getArgList())
        
    def getColor(self, args):
        arg = str(self.argCombo.currentText())
        if arg not in args:
            raise Exception('Cannot generate color; value "%s" is not present in this data.' % arg)
        val = args[arg]
        if val is None:
            return Qt.QColor(100,100,100,255)
            #raise Exception('Cannot generate color; value "%s" is empty (None).' % arg)
        mn = self.minSpin.value()
        mx = self.maxSpin.value()
        norm = np.clip((val - mn) / (mx - mn), 0.0, 1.0)
        return self.gradient.getColor(norm)

    def getColorArray(self, data):
        arg = str(self.argCombo.currentText())
        vals = data[arg]
        mn = self.minSpin.value()
        mx = self.maxSpin.value()        
        lut = self.gradient.getLookupTable(512, alpha=True)
        scaled = pg.rescaleData(np.clip(vals, mn, mx), lut.shape[0]/(mx-mn), mn, dtype=np.uint16)
        return pg.applyLookupTable(scaled, lut)
        #norm = np.clip((vals - mn) / (mx - mn), 0.0, 1.0)
        #return pg.makeARGB(vals, lut, levels=[mn, mx], useRGBA=True)[0]

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
        if ind != -1:
            self.argCombo.setCurrentIndex(ind)
        ind = self.opCombo.findText(state['op'])
        self.opCombo.setCurrentIndex(ind)
        
        self.minSpin.setValue(state['min'])
        self.maxSpin.setValue(state['max'])

        self.gradient.restoreState(state['gradient'])

if __name__ == '__main__':
    app = Qt.QApplication([])
    win = Qt.QMainWindow()
    w = ColorMapper(filePath='./test')
    win.setCentralWidget(w)
    win.show()
    win.resize(400,400)
    
    w.setArgList(['x', 'y', 'amp', 'tau'])
    app.exec_()
   