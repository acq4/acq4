# -*- coding: utf-8 -*-

from PyQt4 import QtCore, QtGui
from lib.DataManager import *
import lib.Manager as Manager
import sip
from lib.util.pyqtgraph.MultiPlotWidget import MultiPlotWidget
from lib.util.pyqtgraph.ImageView import ImageView
from DictView import *

class FileDataView(QtGui.QSplitter):
    def __init__(self, parent):
        QtGui.QWidget.__init__(self, parent)
        self.manager = Manager.getManager()
        self.setOrientation(QtCore.Qt.Vertical)
        self.current = None
        self.currentType = None
        self.widgets = []

    def setCurrentFile(self, file):
        #print "=============== set current file ============"
        if file is self.current:
            return
            
        ## What if we just want to update the data display?
        #self.clear()
        
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
            if self.currentType == 'image':
                try:
                    self.widgets[0].setImage(data, autoRange=False)
                except:
                    print "widget type:", type(self.widgets[0])
                    raise
            else:
                self.clear()
                w = ImageView(self)
                self.addWidget(w)
                w.setImage(data)
                self.widgets.append(w)
            self.currentType = 'image'
        else:
            self.clear()
            w = MultiPlotWidget(self)
            self.addWidget(w)
            w.plot(data)
            self.currentType = 'plot'
            self.widgets.append(w)
        
        if isinstance(data, MetaArray):
            w = DictView(data._info)
            #w.setText(str(data._info[-1]))
            self.addWidget(w)
            self.widgets.append(w)
            h = self.size().height()
            self.setSizes([h*0.8, h*0.2])
            
        
    def clear(self):
        for w in self.widgets:
            sip.delete(w)
        self.widgets = []
        
