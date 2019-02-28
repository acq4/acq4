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
from collections import OrderedDict
import json


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

        self._ctrl = PhotoStimulationLogItemCtrlWidget(self, self.headstageCount)
        self.layout.addWidget(self._ctrl, self.layout.rowCount(), 0, 1, 2)

        for pt in self.data.listPoints():
            self.addStimPoint(pt)
        self._ctrl.headstagesCheckChanged() ## trigger params to be hidden until headstages are checked

    @classmethod
    def checkFile(cls, fh):
        name = fh.shortName()
        if name.startswith('PhotoStimulationLog') and name.endswith('.log'):
            return 10
        else:
            return 0

    def addStimPoint(self, pt):
        pt.graphicsItem.setMovable(False)
        pt.graphicsItem.setParentItem(self._graphicsItem)

        children = []
        for i in range(self.headstageCount):
            children.append(dict(name='headstage_%i' % i, type='list', values={'none':0, 'putative inhibitory':1, 
                            'putative excitatory':2, 'mark for later':3, 'no cnx':4}, value=0))


        param = pg.parametertree.Parameter.create(name=pt.name, autoIncrementName=False, type='group', renamable=False, removable=False, children=children)
        self.params.addChild(param)
        param.point = pt



registerItemType(PhotoStimulationLogCanvasItem)


class PhotoStimulationLogItemCtrlWidget(QtGui.QWidget):
    def __init__(self, canvasitem, headstageCount):
        QtGui.QWidget.__init__(self)
        self.canvasitem = weakref.ref(canvasitem)

        self.layout = QtGui.QGridLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        self.headstageGroup = QtGui.QGroupBox("Headstages used:")
        self.layout.addWidget(self.headstageGroup, 0,0, 1,-1)
        self.hsLayout = QtGui.QGridLayout()
        self.hsLayout.setContentsMargins(2,2,2,2)
        self.headstageGroup.setLayout(self.hsLayout)
        self.headstageChecks = {}
        self.headstageLabels = {}
        self.headstageROIs = []
        for i in range(headstageCount):
            w = QtGui.QCheckBox('%i'%i)
            l = QtGui.QLabel("Pos: , Angle: ")
            self.headstageChecks[i] = w
            self.headstageLabels[i] = l
            #row = i
            #column = i%2
            #self.hsLayout.addWidget(w, row, column)
            self.hsLayout.addWidget(w, i, 0)
            self.hsLayout.addWidget(l, i, 1)
            roi = pg.EllipseROI((0,0), (0.00001,0.000015))
            self.headstageROIs.append(roi)
            roi.setParentItem(canvasitem._graphicsItem)
            roi.hide()
            roi.sigRegionChanged.connect(self.headstageROImoved)




        for c in self.headstageChecks.itervalues():
            c.setCheckState(False)
            c.stateChanged.connect(self.headstagesCheckChanged)

        
        self.ptree = pg.parametertree.ParameterTree(showHeader=False)
        self.ptree.setParameters(canvasitem.params)
        self.layout.addWidget(self.ptree, 1, 0, 1, 2)

        self.saveJsonBtn = QtGui.QPushButton('Save Json')
        self.layout.addWidget(self.saveJsonBtn, 2, 0)
        self.saveJsonBtn.clicked.connect(self.saveJson)
        
        #self.copyJsonBtn = QtGui.QPushButton('Copy Json')
        #self.layout.addWidget(self.copyJsonBtn, 1, 0)
        #self.copyJsonBtn.clicked.connect(self.copyJson)

    def headstagesCheckChanged(self):
        for i, hsCheck in self.headstageChecks.iteritems():
            if hsCheck.isChecked():
                self.headstageROIs[i].show()
                self.updatePosLabel(i)
            else:
                self.headstageROIs[i].hide()
                self.clearPosLabel(i)

        for point in self.ptree.topLevelItem(0).param.children():
            for hs in point.children():
                if self.headstageChecks[int(hs.name()[-1])].isChecked():
                    hs.show()
                else:
                    hs.hide()

    def updatePosLabel(self, headstageNumber):
        i = headstageNumber
        pos = self.headstageROIs[i].pos()
        ang = self.headstageROIs[i].angle() + 90. ## +90 is to mimic what Alice did in new_text_ui.py
        self.headstageLabels[i].setText("Pos:%s, Angle:%s"%(str(pos), str(ang)))

    def clearPosLabel(self, headstageNumber):
        i = headstageNumber
        self.headstageLabels[i].setText("Pos: , Angle: ")

    def headstageROImoved(self, roi):
        i = self.headstageROIs.index(roi)
        self.updatePosLabel(i)


    def saveJson(self):
        filename = QtGui.QFileDialog.getSaveFileName(None, "Save connections", "", "JSON files (*.json)")
        if filename == '':
            return
        if not filename.endswith('.json'):
            filename += '.json'

        data = OrderedDict()
        data['version'] = 1
        data['Headstages'] = OrderedDict()
        data['StimulationPoints'] = OrderedDict()

        for hs in self.headstageChecks.keys():
            if not self.headstageChecks[hs].isChecked():
                continue
            data['Headstages']['electrode_%i'%hs] = OrderedDict()
            ### Need to add position info here
            d = {}
            d['x_pos'] = 0.0001
            d['y_pos'] = 0.0002
            d['z_pos'] = 0.0003
            d['angle'] = 75
            data['Headstages']['electrode_%i'%hs].update(d)
            

            data['Headstages']['electrode_%i'%hs]['Connections'] = OrderedDict()


        for point in self.ptree.topLevelItem(0).param.children():
            for hs in point.children():
                if not self.headstageChecks[int(hs.name()[-1])].isChecked():
                    continue
                cx = hs.value()
                if cx == 0:
                    cnx_str = None
                elif cx == 1:
                    cnx_str = 'inhibitory'
                elif cx == 2:
                    cnx_str = 'excitatory'
                elif cx == 3:
                    cnx_str = 'tbd'
                elif cx == 4:
                    cnx_str = 'no cnx'
                data['Headstages']['electrode_%s'%hs.name()[-1]]['Connections'][point.name()] = cnx_str


        #data[point.name()] = point.point.stimulations
            data['StimulationPoints'][point.name()] = point.point.saveState()

        with open(filename, 'w') as outfile:
            json.dump(data, outfile, indent=4)



    #def copyJson(self):
    #    pass

