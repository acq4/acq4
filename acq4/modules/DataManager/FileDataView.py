# -*- coding: utf-8 -*-
from __future__ import print_function

from acq4.util import Qt
from acq4.util.DataManager import *
#import acq4.Manager as Manager
import acq4.pyqtgraph as pg
#from acq4.pyqtgraph.MultiPlotWidget import MultiPlotWidget
#from acq4.pyqtgraph.ImageView import ImageView
from acq4.util.DictView import *
import acq4.util.metaarray as metaarray
import weakref

class FileDataView(Qt.QSplitter):
    def __init__(self, parent):
        Qt.QSplitter.__init__(self, parent)
        #self.manager = Manager.getManager()
        self.setOrientation(Qt.Qt.Vertical)
        self.current = None
        self.currentType = None
        self.widgets = []
        self.dictWidget = None
        #self.plots = []

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
                with pg.BusyCursor():
                    data = file.read()
                if typ == 'ImageFile': 
                    image = True
                elif typ == 'MetaArray':
                    if data.ndim == 2 and not data.axisHasColumns(0) and not data.axisHasColumns(1):
                        image = True
                    elif data.ndim > 2:
                        image = True
                else:
                    return
                        
        
        with pg.BusyCursor():
            if image:
                if self.currentType == 'image' and len(self.widgets) > 0:
                    try:
                        self.widgets[0].setImage(data, autoRange=False)
                    except:
                        print("widget types:", list(map(type, self.widgets)))
                        raise
                else:
                    self.clear()
                    w = pg.ImageView(self)
                    #print "add image:", w.ui.roiPlot.plotItem
                    #self.plots = [weakref.ref(w.ui.roiPlot.plotItem)]
                    self.addWidget(w)
                    w.setImage(data)
                    self.widgets.append(w)
                self.currentType = 'image'
            else:
                self.clear()
                w = pg.MultiPlotWidget(self)
                self.addWidget(w)
                w.plot(data)
                self.currentType = 'plot'
                self.widgets.append(w)
                #print "add mplot:", w.mPlotItem.plots
                
                #self.plots = [weakref.ref(p[0]) for p in w.mPlotItem.plots]
        
        if (hasattr(data, 'implements') and data.implements('MetaArray')):
            if self.dictWidget is None:
                w = DictView(data._info)
                self.dictWidget = w
                #w.setText(str(data._info[-1]))
                self.addWidget(w)
                self.widgets.append(w)
                h = self.size().height()
                self.setSizes([h*0.8, h*0.2])
            else:
                self.dictWidget.setData(data._info)
            
        
    def clear(self):
        for w in self.widgets:
            w.close()
            w.setParent(None)
        self.widgets = []
        self.dictWidget = None
                
