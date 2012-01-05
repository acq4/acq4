# -*- coding: utf-8 -*-
from pyqtgraph.Qt import QtGui, QtCore

__all__ = ['ProgressDialog']
class ProgressDialog(QtGui.QProgressDialog):
    """Extends QProgressDialog for use in 'with' statements.
    Arguments:
        labelText   (required)
        cancelText   Text to display on cancel button, or None to disable it.
        minimum
        maximum
        parent       
        wait         Length of time (im ms) to wait before displaying dialog
        busyCursor   If True, show busy cursor until dialog finishes
    
    
    Example:
        with ProgressDialog("Processing..", minVal, maxVal) as dlg:
            # do stuff
            dlg.setValue(i)   ## could also use dlg += 1
            if dlg.wasCanceled():
                raise Exception("Processing canceled by user")
    """
    def __init__(self, labelText, minimum=0, maximum=100, cancelText='Cancel', parent=None, wait=250, busyCursor=False):
        noCancel = False
        if cancelText is None:
            cancelText = ''
            noCancel = True
            
        self.busyCursor = busyCursor
            
        QtGui.QProgressDialog.__init__(self, labelText, cancelText, minimum, maximum, parent)
        self.setMinimumDuration(wait)
        self.setWindowModality(QtCore.Qt.WindowModal)
        self.setValue(self.minimum())
        if noCancel:
            self.setCancelButton(None)
        

    def __enter__(self):
        if self.busyCursor:
            QtGui.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
        return self

    def __exit__(self, exType, exValue, exTrace):
        if self.busyCursor:
            QtGui.QApplication.restoreOverrideCursor()
        self.setValue(self.maximum())
        
    def __iadd__(self, val):
        """Use inplace-addition operator for easy incrementing."""
        self.setValue(self.value()+val)
        return self

