# -*- coding: utf-8 -*-

from PyQt4 import QtCore, QtGui
from lib.DataManager import *
import lib.Manager as Manager
import sip
from lib.util.qtgraph.MultiPlotWidget import MultiPlotWidget
from lib.util.qtgraph.ImageView import ImageView

class FileDataView(QtGui.QWidget):
    def __init__(self, parent):
        QtGui.QWidget.__init__(self, parent)
        self.manager = Manager.getManager()
        self.layout = QtGui.QVBoxLayout(self)
        self.current = None
        self.widget = None

    def setCurrentFile(self, file):
        #print "=============== set current file ============"
        if file is self.current:
            return
            
        self.clear()
        
        if file is None:
            self.current = None
            return
            
        if file.isDir():
            ## Sequence or not?
            return
        else:
            typ = file.fileType()
            if typ is None:
                return
            else:
                image = False
                data = file.read()
                if typ == 'ImageFile': 
                    image = True
                elif typ == 'MetaArray':
                    if data.ndim > 2:
                        image = True
                else:
                    return
                        
        
        if image:
            self.widget = ImageView(self)
            self.layout.addWidget(self.widget)
            self.widget.setImage(data)
        else:
            self.widget = MultiPlotWidget(self)
            self.layout.addWidget(self.widget)
            self.widget.plot(data)
        
    def clear(self):
        if self.widget is not None:
            sip.delete(self.widget)
            self.widget = None
