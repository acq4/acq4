# -*- coding: utf-8 -*-
#import time, re
import weakref
from PyQt4 import QtCore, QtGui
from CanvasItem import CanvasItem
import acq4.Manager
import acq4.pyqtgraph as pg
import acq4.util.DataManager
import numpy as np
#from .MarkersCanvasItem import MarkersCanvasItem
from .itemtypes import registerItemType
from collections import OrderedDict
import json
import copy


class PhotoStimulationLogCanvasItem(CanvasItem):
    "For displaying photostimulation points from a PhotostimulationLog file."

    _typeName = "Photostimulation Log"

    def __init__(self, handle=None, **opts):
        opts.pop('viewRect', None)
        self.reloadFromCnx = False

        if handle is None:
            self.reloadFromCnx = True
            handle = self.alertUserBadMosaic()

        self.data = handle.read()
        self.headstageCount = 4

        item = pg.ItemGroup()
        o = {'scalable': False, 'rotatable': False, 'movable': False, 'handle':handle}
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

    def userPicksFile(self):
        """Used for loading old .mosiac files where the filehandle of the photostimLog wasn't saved. Raises a dialog and returns a filehandle picked by the user."""
        dh = acq4.Manager.getManager().getCurrentDir()
        #self.dialog = pg.FileDialog(caption='PhotostimLog filename was not specified in .mosaic. Please pick a PhotostimLog to load.', directory=dh.name())
        #self.dialog.
        filename = QtGui.QFileDialog.getOpenFileName(caption='PhotoStimulationLog filename was not specified in .mosaic. Please pick a PhotoStimulationLog to load.', directory=dh.name(), filter='Photostim Log File (*.log)')
        return acq4.util.DataManager.getHandle(filename)

    def alertUserBadMosaic(self):
        text = 'There is no PhotoStimulationLog filename stored in the .mosaic file. Would you like to select a PhotoStimulationLog.log file and a connections.json file to load?'
        self.messageBox = QtGui.QMessageBox(QtGui.QMessageBox.Question, '', text, buttons=QtGui.QMessageBox.Ok|QtGui.QMessageBox.Cancel)
        #self.messageBox.show()
        res = self.messageBox.exec_()
        #res = self.messageBox.result()

        if res == QtGui.QMessageBox.Ok:
            print("result okay")
            return self.userPicksFile()
        elif res == QtGui.QMessageBox.Cancel:
            raise Exception("Can't reload PhotoStimulationLog from .mosaic. No filename saved in .mosaic")

    def attemptConnectionDataRescue(self):
        """Return a dict with 'points' and 'headstageChecks', with the same info stored in newer .mosaics. Used for reloading data from connections.json files (from befor data was saved in .mosaic)."""
        self.reloadFromCnx = False ## only try this once

        ## get connection file 
        dh = acq4.Manager.getManager().getCurrentDir()
        filename = QtGui.QFileDialog.getOpenFileName(caption='Please select a connection.json file to reload connection data from.', directory=dh.name(), filter='JSON files (*.json)')

        with open(filename,'r') as f:
            exp_json=json.load(f)

        cnxs = {"tbd": 3, 
                "no cnx": 4, 
                "none": 0, 
                "inhibitory": 1, 
                "excitatory": 2,
                None:0
                }
        headstageDefaults = {
                                "expanded": True, 
                                #"name": "headstage_0", 
                                "limits": {
                                    "mark for later": 3, 
                                    "no cnx": 4, 
                                    "none": 0, 
                                    "putative inhibitory": 1, 
                                    "putative excitatory": 2
                                }, 
                                "strictNaming": False, 
                                "default": 0, 
                                "enabled": True, 
                                "title": None, 
                                "renamable": False, 
                                #"value": 0, 
                                "visible": True, 
                                "readonly": False, 
                                "values": {
                                    "mark for later": 3, 
                                    "no cnx": 4, 
                                    "none": 0, 
                                    "putative inhibitory": 1, 
                                    "putative excitatory": 2
                                }, 
                                "removable": False, 
                                "type": "list"
                            }
        ## points[name]['param']['children'][headstage_name]['value'] = int
        points = {}
        headstage_checks = {'0':False, '1':False, '2':False, '3':False}
        for headstage, v in exp_json['Headstages'].items():
            for point, conn_call in v['Connections'].items():
                if points.get(point) == None:
                    #print "1"
                    points[point]={}
                if points[point].get('param') == None:
                    #print "2"
                    points[point]['param'] = {'children':{}}
                if points[point]['param']['children'].get(headstage) == None:
                    #print "3"
                    points[point]['param']['children'][headstage]=copy.deepcopy(headstageDefaults)
                points[point]['param']['children'][headstage]['value'] = cnxs[conn_call]
                #print("C:", point, headstage, points[point]['param']['children'][headstage].get('name', 'None'))
                points[point]['param']['children'][headstage]['name'] = 'headstage_'+headstage[-1]
                #print("D:", point, headstage, points[point]['param']['children'][headstage]['name'])

            #print('A:', {k:v['name'] for k, v in points['Point 1']['param']['children'].items()})
            headstage_checks[headstage[-1]] = True





        #raise Exception('stop')
        #print('B:', {k:v['name'] for k, v in points['Point 1']['param']['children'].items()})
        return {'points':points, 'headstageChecks':headstage_checks}




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

    def saveState(self, relativeTo=None):
        state = CanvasItem.saveState(self, relativeTo)
        #state['filename'] = self.handle
        state['points'] = {}
        for param in self.params.children():
            d = param.point.saveState()
            d['param'] = param.saveState()
            state['points'][param.name()] = d
        state['headstageChecks'] = {k:v.isChecked() for k,v in self._ctrl.headstageChecks.items()}
        return state

    def restoreState(self, state):
        if self.reloadFromCnx:
            reloaded=True
            #state.update(self.attemptConnectionDataRescue())
            res = self.attemptConnectionDataRescue()
            points = res['points']
            #print('RESTORE STATE 1:', {k:v['name'] for k, v in points['Point 1']['param']['children'].items()})
            headstageChecks = res['headstageChecks']
        else:
            points = state.pop('points')
            headstageChecks = state.pop('headstageChecks')
        CanvasItem.restoreState(self, state)

        #for param in self.params.children():
        #    self.params.removeChild(param)
        #    param.point.graphicsItem.scene().removeItem(param.point.graphicsItem)

        for param in self.params.children():
            #print('restoring param 2:', {k: v['name'] for k, v in points[param.name()]['param']['children'].items()})
            param.restoreState(points[param.name()]['param'])

        for k, chk in self._ctrl.headstageChecks.items():
            chk.setChecked(headstageChecks[str(k)])



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
        #self.headstageLabels = {}
        #self.headstageROIs = []
        for i in range(headstageCount):
            w = QtGui.QCheckBox('%i'%i)
            #l = QtGui.QLabel("Pos: , Angle: ")
            self.headstageChecks[i] = w
            #self.headstageLabels[i] = l
            row = i/2
            column = i%2
            self.hsLayout.addWidget(w, row, column)
            #self.hsLayout.addWidget(w, i, 0)
            #self.hsLayout.addWidget(l, i, 1)
            #roi = pg.EllipseROI((0,0), (0.00001,0.000015))
            #self.headstageROIs.append(roi)
            #roi.setParentItem(canvasitem._graphicsItem)
            #roi.hide()
            #roi.sigRegionChanged.connect(self.headstageROImoved)




        for c in self.headstageChecks.itervalues():
            c.setCheckState(False)
            c.stateChanged.connect(self.headstagesCheckChanged)

        
        self.ptree = pg.parametertree.ParameterTree(showHeader=False)
        self.ptree.setParameters(canvasitem.params)
        self.layout.addWidget(self.ptree, 1, 0, 1, 2)

        self.saveOldJsonBtn = QtGui.QPushButton('Save Old Json')
        self.layout.addWidget(self.saveOldJsonBtn, 2, 0)
        self.saveOldJsonBtn.clicked.connect(self.saveOldJson)

        self.saveNewJsonBtn = QtGui.QPushButton('Save New Json')
        self.layout.addWidget(self.saveNewJsonBtn, 2, 1)
        self.saveNewJsonBtn.clicked.connect(self.saveNewJson)
        
        #self.copyJsonBtn = QtGui.QPushButton('Copy Json')
        #self.layout.addWidget(self.copyJsonBtn, 1, 0)
        #self.copyJsonBtn.clicked.connect(self.copyJson)

    def headstagesCheckChanged(self):
        # for i, hsCheck in self.headstageChecks.iteritems():
        #     if hsCheck.isChecked():
        #         self.headstageROIs[i].show()
        #         self.updatePosLabel(i)
        #     else:
        #         self.headstageROIs[i].hide()
        #         self.clearPosLabel(i)

        for point in self.ptree.topLevelItem(0).param.children():
            for hs in point.children():
                if self.headstageChecks[int(hs.name()[-1])].isChecked():
                    hs.show()
                else:
                    hs.hide()

    # def updatePosLabel(self, headstageNumber):
    #     i = headstageNumber
    #     pos = self.headstageROIs[i].pos()
    #     ang = self.headstageROIs[i].angle() + 90. ## +90 is to mimic what Alice did in new_text_ui.py
    #     self.headstageLabels[i].setText("Pos:%s, Angle:%s"%(str(pos), str(ang)))

    # def clearPosLabel(self, headstageNumber):
    #     i = headstageNumber
    #     self.headstageLabels[i].setText("Pos: , Angle: ")

    # def headstageROImoved(self, roi):
    #     i = self.headstageROIs.index(roi)
    #     self.updatePosLabel(i)


    def saveOldJson(self):
        filename = QtGui.QFileDialog.getSaveFileName(None, "Save connections", "", "JSON files (*.json)")
        if filename == '':
            return
        if not filename.endswith('.json'):
            filename += '.json'

        data = OrderedDict()
        data['version'] = 1
        data['Headstages'] = OrderedDict()
        data['StimulationPoints'] = OrderedDict()

        cells = self.getCellPositions()
        angle = self.getCortexMarkerState()['sliceAngle']

        for hs in self.headstageChecks.keys():
            if not self.headstageChecks[hs].isChecked():
                continue
            data['Headstages']['electrode_%i'%hs] = OrderedDict()
            ### Need to add position info here
            d = OrderedDict()
            d['cellName'] = cells[hs][0]
            d['x_pos'] = cells[hs][1][0]
            d['y_pos'] = cells[hs][1][1]
            d['z_pos'] = cells[hs][1][2]
            d['angle'] = angle
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

    def getCellPositions(self):
        markers = []
        for item in self.canvasitem().canvas.items:
            if item._typeName == "Markers":
                markers.append(item)

        if len(markers) == 0:
            raise Exception("Could not find any cell markers. Please load a MultiPatchLog and create Markers.")
        elif len(markers) > 1:
            raise Exception("Found %i markers items. Not sure which one to use." % len(markers))
        else:
            return markers[0].saveState()['markers']

    def getCortexMarker(self):
        items = []
        for item in self.canvasitem().canvas.items:
            if item._typeName == "CortexMarker":
                items.append(item)

        if len(items) == 0:
            raise Exception("Could not find a CortexMarker used to measure angle. Please add one.")
        elif len(items) > 1:
            raise Exception("Found %i CortexMarker items. Not sure which to use.")
        else:
            return items[0]

    def getCortexMarkerState(self):
        """Return a dict with 'piaPos', 'wmPos', 'sliceAngle'."""
        marker = self.getCortexMarker()
        state = marker.saveState()
        return {'sliceAngle':state['sliceAngle'],
                'piaPos': state['piaPos'],
                'wmPos':state['wmPos'],
                'layers':state['roiState']['layers'],
                'layerBoundPositions':state['roiState']['handles'][1:], ## first handle is a scale
                'layerBounds_percentDepth':state['roiState']['layerBounds_percentDepth']
                }

    def findTargetLayer(self, percentDepth, layer_dict):
        layers = [] 
        for l, v in layer_dict.items():
            if (percentDepth > v[0]) and (percentDepth < v[1]):
                layers.append(l)

        if len(layers) != 1:
            raise Exception("Found %i layers for depth of %i. layers: %s" %(len(layers), percentDepth, str(layers)))
        return layers[0]


    def saveNewJson(self):
        filename = QtGui.QFileDialog.getSaveFileName(None, "Save connections", "", "JSON files (*.json)")
        if filename == '':
            return
        if not filename.endswith('.json'):
            filename += '.json'

        data = OrderedDict()
        data['version'] = 3
        data['Headstages'] = OrderedDict()
        data['StimulationPoints'] = OrderedDict()
        data['CortexMarker'] = self.getCortexMarkerState()


        cells = self.getCellPositions()
        cortexROI = self.getCortexMarker().graphicsItem()

        for hs in self.headstageChecks.keys():
            if not self.headstageChecks[hs].isChecked():
                continue
            data['Headstages']['electrode_%i'%hs] = OrderedDict()
            ### Need to add position info here
            d = OrderedDict()
            d['cellName'] = cells[hs][0]
            d['x_pos'] = cells[hs][1][0]
            d['y_pos'] = cells[hs][1][1]
            d['z_pos'] = cells[hs][1][2]
            d['angle'] = data['CortexMarker']['sliceAngle']
            d['percent_depth'] = (cortexROI.mapFromParent(pg.Point(d['x_pos'], d['y_pos']))/cortexROI.size()).y()
            d['target_layer'] = self.findTargetLayer(d['percent_depth'], data['CortexMarker']['layerBounds_percentDepth'])
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
            d = point.point.saveState()
            d['stimulations'] = point.point.stimulations
            d['images'] = list(set([x[x.keys()[0]]['prairieImage'] for x in d['stimulations']]))
            d['percent_depth'] = (cortexROI.mapFromParent(pg.Point(d['position'][0], d['position'][1]))/cortexROI.size()).y()
            d['target_layer'] = self.findTargetLayer(d['percent_depth'], data['CortexMarker']['layerBounds_percentDepth'])


            data['StimulationPoints'][point.name()] = d


        with open(filename, 'w') as outfile:
            json.dump(data, outfile, indent=4)


    # def saveNewJson(self):
    #      #### VERSION 2
    #     filename = QtGui.QFileDialog.getSaveFileName(None, "Save connections", "", "JSON files (*.json)")
    #     if filename == '':
    #         return
    #     if not filename.endswith('.json'):
    #         filename += '.json'

    #     data = OrderedDict()
    #     data['version'] = 2
    #     data['Headstages'] = OrderedDict()
    #     data['StimulationPoints'] = OrderedDict()
    #     data['CortexMarker'] = self.getCortexMarkerState()


    #     cells = self.getCellPositions()

    #     for hs in self.headstageChecks.keys():
    #         if not self.headstageChecks[hs].isChecked():
    #             continue
    #         data['Headstages']['electrode_%i'%hs] = OrderedDict()
    #         ### Need to add position info here
    #         d = OrderedDict()
    #         d['cellName'] = cells[hs][0]
    #         d['x_pos'] = cells[hs][1][0]
    #         d['y_pos'] = cells[hs][1][1]
    #         d['z_pos'] = cells[hs][1][2]
    #         d['angle'] = data['CortexMarker']['sliceAngle']
    #         data['Headstages']['electrode_%i'%hs].update(d)
            

    #         data['Headstages']['electrode_%i'%hs]['Connections'] = OrderedDict()


    #     for point in self.ptree.topLevelItem(0).param.children():
    #         for hs in point.children():
    #             if not self.headstageChecks[int(hs.name()[-1])].isChecked():
    #                 continue
    #             cx = hs.value()
    #             if cx == 0:
    #                 cnx_str = None
    #             elif cx == 1:
    #                 cnx_str = 'inhibitory'
    #             elif cx == 2:
    #                 cnx_str = 'excitatory'
    #             elif cx == 3:
    #                 cnx_str = 'tbd'
    #             elif cx == 4:
    #                 cnx_str = 'no cnx'
    #             data['Headstages']['electrode_%s'%hs.name()[-1]]['Connections'][point.name()] = cnx_str


    #     #data[point.name()] = point.point.stimulations
    #         d = point.point.saveState()
    #         d['stimulations'] = point.point.stimulations
    #         d['images'] = list(set([x[x.keys()[0]]['prairieImage'] for x in d['stimulations']]))
    #         data['StimulationPoints'][point.name()] = d


    #     with open(filename, 'w') as outfile:
    #         json.dump(data, outfile, indent=4)

    # #def copyJson(self):
    # #    pass


    # #def copyJson(self):
    # #    pass

