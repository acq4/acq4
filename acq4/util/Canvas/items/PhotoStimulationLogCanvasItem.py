# -*- coding: utf-8 -*-
#import time, re
import weakref
from PyQt4 import QtCore, QtGui
from CanvasItem import CanvasItem
import acq4.Manager
import acq4.pyqtgraph as pg
import numpy as np
#from .MarkersCanvasItem import MarkersCanvasItem
from .itemtypes import registerItemType


class PhotoStimulationLogCanvasItem(CanvasItem):
    "For displaying photostimulation points from a PhotostimulationLog file."

    _typeName = "Photostimulation Log"

    def __init__(self, handle, **opts):
        opts.pop('viewRect', None)
        
        self.data = handle.read()
        self.headstageCount = 4

        item = pg.ItemGroup()
        o = {'scalable': False, 'rotatable': False, 'movable': False}
        opts.update(o)        
        CanvasItem.__init__(self, item, **opts)

        self.params = pg.parametertree.Parameter.create(name='Stimulation Points', type='group')
        #self.params.addNew = self.addMarker
        #self.params.sigTreeStateChanged.connect(self._paramsChanged)

        self._ctrl = PhotoStimulationLogItemCtrlWidget(self)
        self.layout.addWidget(self._ctrl, self.layout.rowCount(), 0, 1, 2)

        for pt in self.data.listPoints():
            self.addStimPoint(pt)

    @classmethod
    def checkFile(cls, fh):
        name = fh.shortName()
        if name.startswith('PhotoStimulationLog') and name.endswith('.log'):
            return 10
        else:
            return 0

    def addStimPoint(self, pt):
        #pt.graphicsItem.setMovable(False)
        pt.graphicsItem.setParentItem(self._graphicsItem)
        pt.graphicsItem.sigClicked.connect(self.pointClicked)

        children = []
        for i in range(self.headstageCount):
            children.append(dict(name='headstage_%i' % i, type='list', values={'none':0, 'putative inhibitory':1, 
                            'putative excitatory':2, 'mark for later':3, 'no cnx':4}, value=0))


        param = pg.parametertree.Parameter.create(name=pt.name, autoIncrementName=False, type='group', renamable=False, removable=False, children=children)
        self.params.addChild(param)
        pt.graphicsItem.param = weakref.ref(param)


    def pointClicked(self, gItem):
        ## graphicsItem was clicked, highlight its param in paramtree
        self.params.setCurrentItem(gItem.param)

registerItemType(PhotoStimulationLogCanvasItem)


class PhotoStimulationLogItemCtrlWidget(QtGui.QWidget):
    def __init__(self, canvasitem):
        QtGui.QWidget.__init__(self)
        self.canvasitem = weakref.ref(canvasitem)

        self.layout = QtGui.QGridLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)
        
        self.ptree = pg.parametertree.ParameterTree(showHeader=False)
        self.ptree.setParameters(canvasitem.params)
        self.layout.addWidget(self.ptree, 0, 0, 1, 2)

        self.saveJsonBtn = QtGui.QPushButton('Save Json')
        self.layout.addWidget(self.saveJsonBtn, 1, 0)
        self.saveJsonBtn.clicked.connect(self.saveJson)
        
        #self.copyJsonBtn = QtGui.QPushButton('Copy Json')
        #self.layout.addWidget(self.copyJsonBtn, 1, 0)
        #self.copyJsonBtn.clicked.connect(self.copyJson)

    def saveJson(self):
        filename = QtGui.QFileDialog.getSaveFileName(None, "Save markers", path, "JSON files (*.json)")
        if filename == '':
            return
        if not filename.endswith('.json'):
            filename += '.json'

        print "Need to implement saving!"

    #def copyJson(self):
    #    pass

