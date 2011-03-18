# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui

class ProgressDialog(QtGui.QProgressDialog):
    """Extends QProgressDialog for use in 'with' statements.
    Example:
        with ProgressDialog("Processing..", "Cancel", minVal, maxVal) as dlg:
            # do stuff
            dlg.setValue(i)
            if dlg.wasCanceled():
                raise Exception("Processing canceled by user")
    """
    def __init__(self, *args, **kargs):
        QtGui.QProgressDialog.__init__(self, *args, **kargs)
        self.setMinimumDuration(250)
        self.setWindowModality(QtCore.Qt.WindowModal)

    def __enter__(self):
        return self

    def __exit__(self, exType, exValue, exTrace):
        self.setValue(self.maximum())

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
