# -*- coding: utf-8 -*-
from __future__ import print_function
"""
For combining photostimulation maps across cells and displaying against 3D atlas.


"""
from acq4.util import Qt
from acq4.analysis.AnalysisModule import AnalysisModule
import os
from collections import OrderedDict
#import DatabaseGui
from acq4.util.ColorMapper import ColorMapper
import acq4.pyqtgraph as pg
import acq4.pyqtgraph.parametertree as ptree
import acq4.pyqtgraph.opengl as gl
import numpy as np
#import acq4.analysis.modules.Photostim.Scan as Scan
#from acq4.analysis.modules.Photostim.Map import Map
#import acq4.analysis.tools.poissonScore as poissonScore
#import flowchart.EventDetection as FCEventDetection
import acq4.analysis.atlas.CochlearNucleus as CN
from acq4.util.DatabaseGui.DatabaseQueryWidget import DatabaseQueryWidget

class MapCombiner(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        self.ctrlLayout = pg.LayoutWidget()
        
        self.reloadBtn = Qt.QPushButton('Reload Data')
        self.ctrlLayout.addWidget(self.reloadBtn)
        self.ctrl = ptree.ParameterTree(showHeader=False)
        self.ctrlLayout.addWidget(self.ctrl, row='next', col=0)
        self.filterBtn = Qt.QPushButton('Filter')
        self.ctrlLayout.addWidget(self.filterBtn, row='next', col=0)
        
        self.cellList = Qt.QListWidget()
        self.cellList.setSelectionMode(self.cellList.ExtendedSelection)
        self.filterText = Qt.QTextEdit("selected = data")
        self.ctrlLayout.addWidget(self.filterText, row='next', col=0)
        self.ctrlLayout.addWidget(self.cellList, row='next', col=0)

        ## 3D atlas
        self.atlas = CN.CNAtlasDisplayWidget()
        self.stimPoints = gl.GLScatterPlotItem()
        self.atlas.addItem(self.stimPoints)
        self.cellPoints = gl.GLScatterPlotItem()
        self.atlas.addItem(self.cellPoints)
        
        modPath = os.path.abspath(os.path.dirname(__file__))
        self.colorMapper = ColorMapper(filePath=os.path.join(modPath, "colorMaps"))
        self._elements_ = OrderedDict([
            #('Database Query', {'type':'ctrl', 'object': DatabaseQueryWidget(self.dataManager()), 'size':(300,200), 'pos': 'left'}),
            ('Options', {'type': 'ctrl', 'object': self.ctrlLayout, 'size': (300, 500), 'pos': 'left'}),
            ('Atlas', {'type': 'ctrl', 'object': self.atlas, 'size': (600,500), 'pos': 'right'}),
            ('Color Mapper', {'type': 'ctrl', 'object': self.colorMapper, 'size': (600,200), 'pos': ('bottom', 'Atlas')}),
        ])
        host.resize(1100, 800)
        self.initializeElements()
        
        
        params = [
            dict(name='Transform', type='group', children=[
                dict(name='Mirror RL', type='bool', value=True),
                dict(name='Cell-centered', type='bool', value=False),
            ]),
            dict(name='Display', type='group', children=[
                dict(name='Cells', type='bool', value=True),
                dict(name='Color by type', type='bool', value=True),
                dict(name='Stimulus Sites', type='bool', value=True),
                dict(name='Atlas', type='bool', value=False),
                dict(name='Grid', type='bool', value=True),
            ]),
            FilterList(name='Filter'),
        ]
        
        self.params = ptree.Parameter.create(name='options', type='group', children=params)
        self.ctrl.setParameters(self.params, showTop=False)
        
        #self.params.sigTreeStateChanged.connect(self.invalidate)
        
        #dbq = self.getElement('Database Query', create=True)
        #dbq.sigChanged.connect(self.dbDataChanged)
        #db = dbq.currentDatabase()
        db = self.dataManager().currentDatabase()
        self.tableName = 'map_site_view'
        if not db.hasTable(self.tableName):
            print("Creating DB views.")
            db.createView(self.tableName, ['map_sites', 'photostim_maps', 'dirtable_cell', 'cochlearnucleus_protocol', 'cochlearnucleus_cell'])
            ## view creation SQL:
            ## select * from map_sites 
                ## inner join photostim_maps on "photostim_maps"."rowid"="map_sites"."map" 
                ## inner join dirtable_cell on "dirtable_cell"."rowid"="photostim_maps"."cell" 
                ## inner join cochlearnucleus_protocol on cochlearnucleus_protocol.protocoldir=map_sites.firstsite
                ## inner join cochlearnucleus_cell on cochlearnucleus_cell.celldir=dirtable_cell.rowid;
        self.reloadData()
        
        self.reloadBtn.clicked.connect(self.reloadData)
        self.filterBtn.clicked.connect(self.refilter)
        self.cellList.itemSelectionChanged.connect(self.selectCells)
        self.colorMapper.sigChanged.connect(self.recolor)
        self.params.param('Display').sigTreeStateChanged.connect(self.updateDisplay)
        self.params.param('Transform').sigTreeStateChanged.connect(self.transform)
        
        self.transform()
        self.refilter()
        
    def reloadData(self):
        db = self.dataManager().currentDatabase()
        self.data = db.select(self.tableName, toArray=True)
        mapper = self.getElement('Color Mapper')
        mapper.setArgList(self.data.dtype.names)
        self.params.param('Filter').setData(self.data)
        
    def updateDisplay(self):
        if not self.params['Display', 'Cells']:
            self.cellPoints.hide()
        else:
            self.cellPoints.show()
        
        if not self.params['Display', 'Stimulus Sites']:
            self.stimPoints.hide()
        else:
            self.stimPoints.show()
        
        if self.params['Display', 'Atlas']:
            self.atlas.showLabel('DCN')
            self.atlas.showLabel('AVCN')
            self.atlas.showLabel('PVCN')
        else:
            self.atlas.showLabel('DCN', False)
            self.atlas.showLabel('AVCN', False)
            self.atlas.showLabel('PVCN', False)
            
        if self.params['Display', 'Grid']:
            self.atlas.grid.show()
        else:
            self.atlas.grid.hide()
        
        self.recolor()
    
    def elementChanged(self, element, old, new):
        name = element.name()

    #def dbDataChanged(self):
        #data = self.getElement('Database Query').table()
        #mapper = self.getElement('Color Mapper')
        #mapper.setArgList(data.dtype.names)
    def transform(self):
        data = self.data.copy()
        if self.params['Transform', 'Mirror RL']:
            data['right'] = np.abs(data['right'])
            data['right:1'] = np.abs(data['right:1'])
            
        if self.params['Transform', 'Cell-centered']:
            r = data['right:1'].mean()
            a = data['anterior:1'].mean()
            d = data['dorsal:1'].mean()
            
            data['right'] += r - data['right:1']
            data['anterior'] += a - data['anterior:1']
            data['dorsal'] += d - data['dorsal:1']
            data['right:1'] = r
            data['anterior:1'] = a
            data['dorsal:1'] = d
        
        self.transformed = data
        self.refilter()
        
        
    def refilter(self):
        data = self.transformed
        
        data = self.params.param('Filter').process(data)
        
        exec(self.filterText.toPlainText())
        self.filtered = selected
        cells = set(self.filtered['cell'])
        self.cellList.clear()
        for c in cells:
            item = Qt.QListWidgetItem(c.name())
            item.dh = c
            self.cellList.addItem(item)
        self.cellList.selectAll()
        self.selectCells()
        
    def selectCells(self):
        if len(self.cellList.selectedItems()) == self.cellList.count():
            self.selected = self.filtered
        else:
            mask = np.zeros(len(self.filtered), dtype=bool)
            for c in self.cellList.selectedItems():
                mask |= (self.filtered['cell'] == c.dh)
            self.selected = self.filtered[mask]
        self.recolor()
        
    def recolor(self):
        #data = self.getElement('Database Query').table()
        if self.selected is None:
            return
            
        data = self.selected
        
        mapper = self.getElement('Color Mapper')
        colors = mapper.getColorArray(data, opengl=True)
        pos = np.empty((len(data), 3))
        pos[:,0] = data['right']
        pos[:,1] = data['anterior']
        pos[:,2] = data['dorsal']
        
        
        self.stimPoints.setData(pos=pos, color=colors, pxMode=False, size=100e-6)
        
        
        cells = set(data['cell'])
        inds = np.array([np.argwhere(data['cell']==c).flatten()[0] for c in cells], dtype=int)
        data = data[inds]
        pos = np.empty((len(data), 3))
        pos[:,0] = data['right:1']
        pos[:,1] = data['anterior:1']
        pos[:,2] = data['dorsal:1']
        
        
        
        if self.params['Display', 'Color by type']:
            typeColors = {
                'B': (0, 0, 1, 1),
                'B?': (0.2, 0.2, 0.7, 1),
                'S': (1, 1, 0, 1),
                'S?': (0.7, 0.7, 0.3, 1),
                'DS': (1, 0, 0, 1),
                'DS?': (1, 0.5, 0, 1),
                'TS': (0, 1, 0, 1),
                'TS?': (0.5, 1, 0, 1),
                '?': (0.5, 0.5, 0.5, 1),
            }
            
            color = np.empty((len(data),4))
            for i in range(len(data)):
                color[i] = typeColors.get(data[i]['CellType:1'], typeColors['?'])
            
        else:
            color = (1,1,1,1)
        
        self.cellPoints.setData(pos=pos, color=color, size=20, pxMode=True)
        
        
        
        
        
class FilterList(ptree.types.GroupParameter):
    def __init__(self, **kwds):
        ptree.types.GroupParameter.__init__(self, addText='Add filter..', **kwds)
        #self.params.addNew = self.addNew
        #self.params.treeStateChanged.connect(self.stateChanged)
            
    def addNew(self):
        ch = FilterItem()
        self.addChild(ch)
        ch.setKeys(self.keyList())
    
    def setData(self, data):
        self.data = data
        keys = self.keyList()
        for ch in self:
            ch.setKeys(keys)
    
    def keyList(self):
        return sorted(list(self.data.dtype.names))
    
    def dataType(self, key):
        kind = self.data.dtype.fields[key][0].kind
        if kind in ('i', 'f'):
            return kind, (self.data[key].min(), self.data[key].max())
        else:
            return kind, sorted(list(set(self.data[key])))
    
    def process(self, data):
        if len(data) == 0:
            return data
        
        for ch in self:
            data = ch.process(data)
        
        return data
        
        #self.updateKeys(events.dtype.names)
        
        
        #for fp in self.params:
            #if fp.value() is False:
                #continue
            #key, mn, mx = fp['Field'], fp['Min'], fp['Max']
            #vals = events[key]
            #mask = (vals >= mn) * (vals < mx)  ## Use inclusive minimum and non-inclusive maximum. This makes it easier to create non-overlapping selections
            #events = events[mask]
            
        #return events
        
        
        

class FilterItem(ptree.types.SimpleParameter):
    def __init__(self, **opts):
        opts['name'] = 'Filter'
        opts['type'] = 'bool'
        opts['value'] = True
        opts['removable'] = True
        opts['renamable'] = True
        opts['autoIncrementName'] = True
        ptree.types.SimpleParameter.__init__(self, **opts)
        
        self.addChild(ptree.Parameter.create(name='Field', type='list'))
        self.param('Field').sigValueChanged.connect(self.updateChildren)

    def setKeys(self, keys):
        self.param('Field').setLimits(keys)
    
    def updateChildren(self):
        for ch in list(self.children()):
            if ch is not self.param('Field'):
                self.removeChild(ch)
        typ, limits = self.parent().dataType(self['Field'])
        self.filterType = typ
        if typ in ('i', 'f'):
            self.addChild(ptree.Parameter.create(name='Min', type='float', value=limits[0]))
            self.addChild(ptree.Parameter.create(name='Max', type='float', value=limits[1]))
        else:
            for x in limits:
                ch = self.addChild(ptree.Parameter.create(name=str(x), type='bool', value=True))
                ch.selectValue = x
    
    def process(self, data):
        if self.value() is False:
            return data
        key = self['Field']
        if self.filterType in ('i', 'f'):
            mask = (data[key] > self['Min']) & (data[key] < self['Max'])
        else:
            mask = np.zeros(len(data), dtype=bool)
            for ch in self:
                if ch is self.param('Field'):
                    continue
                if ch.value() is True:
                    mask |= (data[key] == ch.selectValue)
        return data[mask]
    