from __future__ import print_function
from acq4.util import Qt
import acq4.pyqtgraph as pg
from acq4.pyqtgraph.widgets.SpinBox import SpinBox
from acq4.pyqtgraph.widgets.ColorButton import ColorButton
from . import ContourPlotterTemplate




class ContourPlotter(Qt.QWidget):
    
    sigChanged = Qt.Signal()

    def __init__(self, canvas=None, host=None):
        Qt.QWidget.__init__(self)
        
        self.canvas = canvas
        self.ui = ContourPlotterTemplate.Ui_Form()
        self.ui.setupUi(self)
        
        self.addBtn = Qt.QPushButton('Add New')
        item = Qt.QTreeWidgetItem()
        self.ui.tree.addTopLevelItem(item)
        self.ui.tree.setItemWidget(item, 0, self.addBtn) 
        self.ui.drawBtn.hide()
 
        self.argList=[]
        self.items = []
        self.parentItem = None
        self.data = None
        
        self.addBtn.clicked.connect(self.addItem)
        
    def setCanvas(self, canvas):
        self.canvas = canvas
        
    def emitChanged(self):
        self.adjustContours()
        self.sigChanged.emit()
        
    def addItem(self):
        item = ContourItem(self)
        self.ui.tree.insertTopLevelItem(self.ui.tree.topLevelItemCount()-1, item)
        item.postAdd()
        self.items.append(item) 
        item.updateParamCombo(self.argList)
        self.canvas.addGraphicsItem(item.curveItem)
       
    def remClicked(self, item):
        #item = self.ui.tree.currentItem()
        if item is None:
            return
        self.remItem(item)
        #self.emitChanged()

    def remItem(self, item):
        index = self.ui.tree.indexOfTopLevelItem(item)
        self.ui.tree.takeTopLevelItem(index)
        self.items.remove(item) 
        self.canvas.removeItem(item.curveItem)

    def setArgList(self, args):
        """Sets the list of variable names available for computing contours"""
        self.argList = args
        for i in self.items:
            i.updateParamCombo(self.argList)  
            
    def addParamArg(self, arg):
        if arg not in self.argList:
            self.argList.append(arg)
        self.setArgList(self.argList)
      
    def adjustContours(self, data=None, parentItem=None):
        #print "adjustContours called."
        if data is not None:
            self.data = data
        if parentItem is not None:
            self.parentItem = parentItem
        if self.data is not None:
            for i in self.items:
                i.updateContour(self.data, parentItem=self.parentItem)
            

    
class ContourItem(Qt.QTreeWidgetItem):
    def __init__(self, cp, parentImage=None):
        self.cp = cp
        Qt.QTreeWidgetItem.__init__(self)
        self.paramCombo = pg.ComboBox()
        self.thresholdSpin = pg.SpinBox(value=0.98, dec=True, step=0.1)
        self.maxCheck = Qt.QCheckBox()
        self.colorBtn = ColorButton(color=(255,255,255))
        self.remBtn = Qt.QPushButton('Remove')
        self.curveItem = pg.IsocurveItem()
        self.curveItem.setParentItem(parentImage)
        
        
        self.paramCombo.currentIndexChanged.connect(self.emitChanged)
        self.thresholdSpin.valueChanged.connect(self.emitChanged)
        self.maxCheck.stateChanged.connect(self.emitChanged)
        
        self.colorBtn.sigColorChanged.connect(self.setPen)
        self.remBtn.clicked.connect(self.delete)
       
    def setPen(self, btn):
        self.curveItem.setPen(btn.color())
       
    def emitChanged(self):
        self.cp.emitChanged()
        
    def postAdd(self):
        t = self.treeWidget()
        #self.setText(0, "-")
        t.setItemWidget(self, 0, self.paramCombo)
        t.setItemWidget(self, 1, self.thresholdSpin)
        t.setItemWidget(self, 2, self.maxCheck)
        t.setItemWidget(self, 3, self.colorBtn)
        #t.setItemWidget(self, 4, self.gradient)
        t.setItemWidget(self, 4, self.remBtn)
        
    def delete(self):
        self.cp.remClicked(self)
        
    def updateParamCombo(self, paramList):
        #prev = str(self.paramCombo.currentText())
        #self.paramCombo.clear()
        #for p in paramList:
            #self.paramCombo.addItem(p)
            #if p == prev:
                #self.paramCombo.setCurrentIndex(self.paramCombo.count()-1) 
        self.paramCombo.updateList(paramList)
 
    def updateContour(self, data, parentItem):
        #print "updateContour called."
        param = str(self.paramCombo.currentText())
        #print param
        if param == '':
            return
        #if param == 'Probability': ## fix for compatability with Spatial correlator
         #   param = 'prob'
        data = data[param]
        if self.maxCheck.isChecked():
            level = self.thresholdSpin.value()*data.max()
        else:
            level = self.thresholdSpin.value()
        pen = self.colorBtn.color()
        self.curveItem.setPen(pen)
        self.curveItem.updateLines(data, level)
        #print "boundingrect:", self.curveItem.boundingRect()
        #print data.min(), data.max()
        if hasattr(parentItem, 'graphicsItem'):
            self.curveItem.setParentItem(parentItem.graphicsItem())
        else:
            self.curveItem.setParentItem(parentItem)
        