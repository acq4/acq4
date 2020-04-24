# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt

class ComboBox(Qt.QComboBox):
    """Extends QComboBox with some extra functionality:
    - remembers argument to setValue, restores correct selection after contents have been cleared/repopulated
    """

    def __init__(self, *args):
        Qt.QComboBox.__init__(self, *args)
        self.value = None
        self.currentIndexChanged.connect(self.indexChanged)

    def setValue(self, value):
        self.value = value
        ind = self.findText(value)
        if ind == -1:
            return
        self.setCurrentIndex(ind)
        
    def updateItems(self, values):
        """Set the list of items. Restore the last requested value, if possible"""
        val = self.value
        if val in values:
            self.blockSignals(True)  ## value will not ultimately change; don't generate any signals
            
        self.clear()
        self.addItems(values)
            
        if val in values:
            self.setCurrentItem(values.index(val))
            
        self.blockSignals(False)
        self.value = val  ## might have changed while we weren't looking

    def indexChanged(self, ind):
        self.value = self.itemText(ind)
        
        
    def widgetGroupInterface(self):
        return (self.currentIndexChanged, ComboBox.saveState, ComboBox.restoreState)
        
    def saveState(self):
        ind = self.currentIndex()
        data = self.itemData(ind)
        if not data.isValid():
            return self.itemText(ind)
        else:
            return data.toInt()[0]    
        
    def restoreState(w, v):
        if type(v) is int:
            #ind = self.findData(Qt.QVariant(v))
            ind = self.findData(v)
            if ind > -1:
                self.setCurrentIndex(ind)
                return
        self.setCurrentIndex(self.findText(str(v)))
        
        