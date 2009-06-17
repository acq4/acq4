# -*- coding: utf-8 -*-

from PyQt4 import QtCore, QtGui
from lib.DataManager import *
import lib.Manager as Manager
import sip

class FileDataView(QtGui.QWidget):
    def __init__(self, parent):
        QtGui.QWidget.__init__(self, parent)
        self.manager = Manager.getManager()
        self.current = None
        self.widget = None

    def setCurrentFile(self, file):
        #print "=============== set current file ============"
        if file is self.current:
            return
            
        if file is None:
            self.clear()
            self.current = None
            return
            
        if file.isDir():
            ## Sequence or not?
            pass
        else:
            ## Meta array?
              ## plot?
              ## image?
            ## tiff file?
            pass
        
        
    def clear(self):
        if self.widget is not None:
            sip.delete(self.widget)
            self.widget = None
