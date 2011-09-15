from PyQt4 import QtGui
import sys


class FileDialog(QtGui.QFileDialog):
    
    def __init__(self, *args):
        QtGui.QFileDialog.__init__(self, *args)
        
        if sys.platform == 'darwin': ## For some reason the native dialog doesn't show up when you set AcceptMode to AcceptSave on OS X, so we don't use the native dialog
            self.setOption(QtGui.QFileDialog.DontUseNativeDialog)