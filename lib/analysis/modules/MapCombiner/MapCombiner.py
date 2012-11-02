# -*- coding: utf-8 -*-
"""
For combining photostimulation maps across cells and displaying against 3D atlas.


"""
from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
#import os
#from collections import OrderedDict
#import DatabaseGui
from ColorMapper import ColorMapper
import pyqtgraph as pg
import pyqtgraph.parametertree as ptree
import numpy as np
#import lib.analysis.modules.Photostim.Scan as Scan
#from lib.analysis.modules.Photostim.Map import Map
#import lib.analysis.tools.poissonScore as poissonScore
#import flowchart.EventDetection as FCEventDetection
import lib.analysis.atlas.CochlearNucleus as CN
from DatabaseGui.DatabaseQueryWidget import DatabaseQueryWidget

class MapCombiner(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        self.ctrlLayout = pg.LayoutWidget()
        self.ctrl = ptree.ParameterTree(showHeader=False)
        self.ctrlLayout.addWidget(self.ctrl, row=0, col=0)

        ## 3D atlas
        self.atlas = CN.CNAtlasDisplayWidget()
        self.atlas.showLabel('DCN')
        self.atlas.showLabel('AVCN')
        self.atlas.showLabel('PVCN')
        
        modPath = os.path.abspath(os.path.dirname(__file__))
        self.colorMapper = ColorMapper(filePath=os.path.join(modPath, "colorMaps"))
        self._elements_ = OrderedDict([
            #('Database Query', {'type':'ctrl', 'object': DatabaseQueryWidget(self.dataManager()), 'size':(300,200), 'pos': 'left'}),
            ('Options', {'type': 'ctrl', 'object': self.ctrlLayout, 'size': (300, 500), 'pos': ('bottom', 'Database Query')}),
            ('Atlas', {'type': 'ctrl', 'object': self.atlas, 'size': (600,500), 'pos': 'right'}),
            ('Color Mapper', {'type': 'ctrl', 'object': self.colorMapper, 'size': (600,200), 'pos': ('bottom', 'Atlas')}),
        ])
        host.resize(1100, 800)
        self.initializeElements()
        
        
        params = [
            dict(name='Display', type='group', children=[
                dict(name='Cells', type='bool', value=True),
                dict(name='Stimulus Sites', type='bool', value=True),
            ]),
            dict(name='Filters', type='group', children=[
                
                
            ]),
        ]
        
        self.params = ptree.Parameter.create(name='options', type='group', children=params)
        self.ctrl.setParameters(self.params, showTop=False)
        
        #self.params.sigTreeStateChanged.connect(self.invalidate)
        
        #dbq = self.getElement('Database Query', create=True)
        #dbq.sigChanged.connect(self.dbDataChanged)
        #db = dbq.currentDatabase()
        db = self.dataManager().currentDatabase()
        self.tableName = 'map_site_view'
        if not db.hasTable(siteView):
            print "Creating DB views."
            db.createView(siteView, ['map_sites', 'photostim_maps', 'dirtable_cell', 'cochlearnucleus_protocol', 'cochlearnucleus_cell'])
            ## view creation SQL:
            ## select * from map_sites 
                ## inner join photostim_maps on "photostim_maps"."rowid"="map_sites"."map" 
                ## inner join dirtable_cell on "dirtable_cell"."rowid"="photostim_maps"."cell" 
                ## inner join cochlearnucleus_protocol on cochlearnucleus_protocol.protocoldir=map_sites.firstsite
                ## inner join cochlearnucleus_cell on cochlearnucleus_cell.celldir=dirtable_cell.rowid;
        self.reloadData()
        
    def reloadData(self):
        self.data = db.select(self.tableName, toArray=True)
        
        
    def elementChanged(self, element, old, new):
        name = element.name()

    def dbDataChanged(self):
        data = self.getElement('Database Query').table()
        mapper = self.getElement('Color Mapper')
        mapper.setArgList(data.dtype.names)
        
    def update(self):
        data = self.getElement('Database Query').table()
        mapper = self.getElement('Color Mapper')
        colors = mapper.getColor(data)
        pos = np.empty((len(data), 3))
        for i,rec in enumerate(data):
            
        rec = db.select('CochlearNucleus_Cell', where={'CellDir': cell})
        pts = []
        if len(rec) > 0:
            pos = (rec[0]['right'], rec[0]['anterior'], rec[0]['dorsal'])
            pts = [{'pos': pos, 'size': 100e-6, 'color': (0.7, 0.7, 1.0, 1.0)}]
            
        ## show event positions
        evSpots = {}
        for rec in ev:
            p = (rec['right'], rec['anterior'], rec['dorsal'])
            evSpots[p] = None
            
        pos = np.array(evSpots.keys())
        atlasPoints.setData(pos=pos, )
        
class Filter:
    def __init__(self):
        self.keyList = []
        
        self.params = ptree.Parameter.create(name='Data Filter', type='group', addText='Add filter..', addList=self.keyList)
        self.params.addNew = self.addNew
        self.params.treeStateChanged.connect(self.stateChanged)
            
    def addNew(self, typ):
        fp = ptree.Parameter.create(name='Filter', autoIncrementName=True, type='bool', value=True, removable=True, renamable=True, children=[
            dict(name="Field", type='list', value=typ, values=self.keyList),
            dict(name='Min', type='float', value=0.0),
            dict(name='Max', type='float', value=1.0),
            ])
        self.params.addChild(fp)
    
    def parameters(self):
        return self.params
        
    def updateKeys(self, keys):
        self.keyList = list(keys)
        self.keyList.sort()
        self.params.setAddList(keys)
        for fp in self.params:
            fp.param('Field').setLimits(keys)
    
    def process(self, events):
        if len(events) == 0:
            return events
        
        self.updateKeys(events.dtype.names)
        
        
        for fp in self.params:
            if fp.value() is False:
                continue
            key, mn, mx = fp['Field'], fp['Min'], fp['Max']
            vals = events[key]
            mask = (vals >= mn) * (vals < mx)  ## Use inclusive minimum and non-inclusive maximum. This makes it easier to create non-overlapping selections
            events = events[mask]
            
        return events

class FilterElement(ptree.GroupParameter):
    def __init__(self, **opts):
        ptree.GroupParameter.__init__(self, **opts)
        self.field = ptree.Parameter(