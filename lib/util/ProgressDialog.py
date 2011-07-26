# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui

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
    def __init__(self, labelText, cancelText='Cancel', minimum=0, maximum=100, parent=None, wait=250, busyCursor=False):
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

        #progressDlg = QtGui.QProgressDialog("Computing spot colors (Map %d/%d)" % (n+1,nMax), "Cancel", 0, len(spots))
        ##progressDlg.setWindowModality(QtCore.Qt.WindowModal)
        #progressDlg.setMinimumDuration(250)
        #ops = []
        #try:
            #for i in range(len(spots)):
                #spot = spots[i]
                #fh = self.host.getClampFile(spot.data)
                #stats = self.getStats(fh, signal=False)
                ##print "stats:", stats
                #color = self.host.getColor(stats)
                #ops.append((spot, color))
                #progressDlg.setValue(i+1)
                #QtGui.QApplication.processEvents()
                #if progressDlg.wasCanceled():
                    #raise Exception("Recolor canceled by user.")
        #except:
            #raise
        #finally:
            ### close progress dialog no matter what happens
            #progressDlg.setValue(len(spots))
