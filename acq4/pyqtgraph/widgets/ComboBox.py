from ..Qt import QtGui, QtCore
from ..SignalProxy import SignalProxy
import sys


class ComboBox(QtGui.QComboBox):
    """Extends QComboBox to add extra functionality.
          - updateList() - updates the items in the comboBox while blocking signals, remembers and resets to the previous values if it's still in the list
    """
    
    
    def __init__(self, parent=None, items=None, default=None):
        QtGui.QComboBox.__init__(self, parent)
        
        #self.value = default
        if 'darwin' in sys.platform: ## because MacOSX can show names that are wider than the comboBox
            self.setSizeAdjustPolicy(QtGui.QComboBox.AdjustToMinimumContentsLength)
            #self.setMinimumContentsLength(10)
        
        if items is not None:
            self.addItems(items)
            if default is not None:
                self.setValue(default)
    
    def setValue(self, value):
        ind = self.findText(value)
        if ind == -1:
            return
        #self.value = value
        self.setCurrentIndex(ind)    
        
    def updateList(self, items):
        prevVal = str(self.currentText())
        try:
            self.blockSignals(True)
            self.clear()
            self.addItems(items)
            self.setValue(prevVal)
            
        finally:
            self.blockSignals(False)
            
        if str(self.currentText()) != prevVal:
            self.currentIndexChanged.emit(self.currentIndex())
        
