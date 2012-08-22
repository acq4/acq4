"""
Description:
    
Input: event / site data previously analyzed by photostim
Output: 
    - per-event probability of being direct / evoked / spont
    - per-site probability of having evoked / direct input
    - per-cell measurements of direct and presynaptic area

Whereas photostim largely operates on a single stimulation (or a single stimulation site)
at a time, mapper operates on complete mapping datasets--multiple scans within a cell

Ideally, this module should replace the 'stats' and 'map' functionality in photostim
as well as integrate megan's map analysis, but I would really like it 
to be an independent module (and if it's not too difficult, it should _also_ be possible
to integrate it with photostim)


Features:

    - tracks spontaneous event rate over the timecourse of a cell as well as the prevalence
    of specific event features -- amplitude, shape, etc. This data is used to 
    determine:
        - For each event, the probability that it is evoked / spontaneous / direct
            - If we can get a good measure of this, we should also be able to formulate
              a distribution describing spontaneous events. We can then ask how much of the 
              actual distribution exceeds this and automatically partition events into evoked / spont.
        - For each site, the probability that it contains evoked and/or direct events
    This should have no notion of 'episodes' -- events at the beginning of one trace
    may have been evoked by the previous stim.
    - can report total number of evoked presynaptic sites per atlas region, total area of direct activation
    
    - display colored maps in 3d atlas
    
    - event-explorer functionality:    (perhaps this should stay separate)
        - display scatter plots of events based on various filtering criteria
        - mark regions of events within scatter plot as being invalid
        - filter generator: filter down events one criteria at a time, use lines / rois to control limits
            eg: plot by amplitude, tau; select a population of events that are known to be too large / fast
                replot by relative error and length/tau ratio; select another subset
                once a group is selected / deselected, tag the set (new column in events table)
                


Changes to event detector:
    - Ability to manually adjust PSP fits, particularly for direct responses (this goes into event detector?)
    - Ability to decrease sensitivity after detecting a direct event
    - Move region selection out of event detector entirely; should be part of mapper
    (the mapper can add columns to the event table if we want..)
    
"""


# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
import os
from collections import OrderedDict
import DatabaseGui
from ColorMapper import ColorMapper
import pyqtgraph as pg
import pyqtgraph.parametertree as ptree
import numpy as np
import lib.analysis.modules.Photostim.Scan as Scan
from lib.analysis.modules.Photostim.Map import Map



class MapAnalyzer(AnalysisModule):
    
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        
        self.ctrl = ptree.ParameterTree()
        
        self.loader = Loader(host=self, dm=host.dataManager())
        
        
        modPath = os.path.abspath(os.path.dirname(__file__))
        self.colorMapper = ColorMapper(filePath=os.path.join(modPath, "colorMaps"))
        self._elements_ = OrderedDict([
            ('Map Loader', {'type': 'ctrl', 'object': self.loader, 'size': (300, 300)}),
            ('Canvas', {'type': 'canvas', 'pos': ('right', 'Map Loader'), 'size': (800, 400)}),
            ('Color Mapper', {'type':'ctrl', 'object': self.colorMapper, 'size': (800,200), 'pos':('top', 'Canvas')}),
            ('Options', {'type': 'ctrl', 'object': self.ctrl, 'size': (300, 500), 'pos': ('bottom', 'Map Loader')}),
            ('Data Plot', {'type': 'plot', 'pos': ('bottom', 'Canvas'), 'size': (800, 300)}),
            ('Score Histogram', {'type': 'plot', 'pos': ('below', 'Data Plot'), 'size': (800, 300)}),
            ('Timeline', {'type': 'plot', 'pos': ('below', 'Data Plot'), 'size': (800, 300)}),
            ('Stats Table', {'type': 'table', 'pos': ('below', 'Data Plot'), 'size': (800,300)}),
        ])
        host.resize(1100, 800)
        self.initializeElements()
        
        
        self.filterStage = EventFilter()
        self.spontRateStage = SpontRateAnalyzer(plot=self.getElement('Timeline', create=True))
        self.statsStage = EventStatisticsAnalyzer()
        self.stages = [self.filterStage, self.spontRateStage, self.statsStage]
        
        params = [
            dict(name='Time Ranges', type='group', children=[
                dict(name='Direct Start', type='float', value='0.498', suffix='s', step=0.001, siPrefix=True),
                dict(name='Post Start', type='float', value='0.503', suffix='s', step=0.001, siPrefix=True),
                dict(name='Post End', type='float', value='0.700', suffix='s', step=0.001, siPrefix=True),
            ]),
        ]
        
        ## each processing stage comes with its own set of parameters
        for stage in self.stages:
            params.append(stage.parameters())
        
        self.params = ptree.Parameter(name='options', type='group', children=params)
        self.ctrl.setParameters(self.params, showTop=False)
        
        self.params.sigTreeStateChanged.connect(self.update)
        
    def elementChanged(self, element, old, new):
        name = element.name()

    def loadMap(self, rec):
        self.getElement('Canvas').clear()
        self.currentMap = Map(self, rec)
        self.currentMap.loadStubs()
        self.getElement('Canvas').addGraphicsItem(self.currentMap.sPlotItem)
                
    def loadScan(self, dh):
        ## called by Map objects to load scans
        scans = Scan.loadScanSequence(dh, self)
        if len(scans) > 1:
            raise Exception("Scan sequences not supported yet.")
        for scan in scans:
            ci = scan.canvasItem()
            self.getElement('Canvas').addItem(ci)
            ci.hide()
        return scans
        
    def loadScanFromDB(self, sourceDir):
        ## Called by Scan as it is loading
        statTable = self.loader.dbGui.getTableName('Photostim.sites')
        eventTable = self.loader.dbGui.getTableName('Photostim.events')
        db = self.loader.dbGui.getDb()
        stats = db.select(statTable, '*', where={'ProtocolSequenceDir': sourceDir})
        events = db.select(eventTable, '*', where={'ProtocolSequenceDir': sourceDir}, toArray=True)
        return events, stats
        
    def getColor(self, data):
        ## return the color to represent this data
        return pg.mkColor(200,200,255)
        
    def update(self):
        map = self.currentMap
        scans = map.scans
        events = np.concatenate([s.getAllEvents().copy() for s in scans])
        
        filtered = self.filterStage.process(events)
        
        ## Get a list of all stimulations in the map and their times.
        sites = []
        for s in scans:
            sites.extend(s.getTimes())
        sites.sort(key=lambda i: i[1])
            
        ## set up table of per-stimulation data
        spontRates = np.empty(len(sites), dtype=[('ProtocolDir', object), ('start', float), ('stop', float), ('spontRate', float), ('filteredSpontRate', float)])
        spontRates[:] = [s+(0,0) for s in sites] ## fill with data
        
        ## compute spontaneous rates
        sr = self.spontRateStage.process(spontRates, filtered)
        spontRates['spontRate'] = sr['spontRate']
        spontRates['filteredSpontRate'] = sr['filteredSpontRate']
        
        #output = self.statsStage.process(spontRate)
        
        
        
class EventFilter:
    def __init__(self):
        self.params = ptree.Parameter(name='Event Selection', type='group', children=[
                dict(name='Amplitude Sign', type='list', values=['+', '-'], value='+'),
            ])
    
    def parameters(self):
        return self.params
    
    def process(self, events):
        if self.params['Amplitude Sign'] == '+':
            return events[events['fitAmplitude'] > 0]
        else:
            return events[events['fitAmplitude'] < 0]

class SpontRateAnalyzer:
    def __init__(self, plot=None):
        self.plot = plot
        self.spontRatePlot = plot.plot(pen=0.5)
        self.filterPlot = plot.plot(pen='g')
        self.timeMarker = TimelineMarker()
        plot.addItem(self.timeMarker)
        
        self.params = ptree.Parameter(name='Spontaneous Rate', type='group', children=[
                dict(name='Stimulus Time', type='float', value=0.495, suffix='s', siPrefix=True, step=0.005),
                dict(name='Method', type='list', values=['Constant', 'Constant (Mean)', 'Constant (Median)', 'Mean Window', 'Median Window', 'Gaussian Window'], value='Gaussian Window'),
                dict(name='Constant Rate', type='float', value=0, suffix='Hz', siPrefix=True),
                dict(name='Filter Window', type='float', value=20., suffix='s', siPrefix=True),
            ])
        self.params.sigTreeStateChanged.connect(self.paramsChanged)
    
    def parameters(self):
        return self.params
        
    def paramsChanged(self, param, changes):
        for param, change, info in changes:
            if param is self.params.param('Method'):
                method = self.params['Method']
                const = self.params.param('Constant Rate')
                window = self.params.param('Filter Window')
                if method.startswith('Constant'):
                    const.show()
                    const.setReadonly(method != 'Constant')
                    window.hide()
                else:
                    const.hide()
                    window.show()
        
    def process(self, sites, events):
        ## Inputs:
        ##   events - record array of event data. Must have fields 'protocolDir', 'fitTime'
        ##   sites  - record array with 'protocolDir', 'start', and 'stop' fields. Sorted by start.
        
        self.timeMarker.setTimes(zip(sites['start'], sites['stop']))
        
        ## filter events by pre-region
        stimTime = self.params['Stimulus Time']
        events = events[events['fitTime'] < stimTime]
        
        ## measure spont. rate for each handle
        spontRate = []
        for site in sites:
            ev = events[events['ProtocolDir'] == site['ProtocolDir']]
            spontRate.append(len(ev) / stimTime)
        spontRate = np.array(spontRate)
        
        self.spontRatePlot.setData(x=sites['start'], y=spontRate)
        
        ## do averaging
        method = self.params['Method']
        if method == 'Constant':
            rate = self.params['Constant Rate']
            filtered = [rate] * len(spontRate)
        elif method == 'Constant (Median)':
            rate = np.median(spontRate)
            filtered = [rate] * len(spontRate)
            self.params['Constant Rate'] = rate
        elif method == 'Constant (Mean)':
            rate = np.mean(spontRate)
            filtered = [rate] * len(spontRate)
            self.params['Constant Rate'] = rate
        else:
            filtered = np.empty(len(spontRate))
            for i in xrange(len(spontRate)):
                now = sites['start'][i]
                window = self.params['Filter Window']
                start = now - window
                stop = now + window
                if method == 'Median Window':
                    mask = (sites['start'] > start) & (sites['start'] < stop)
                    filtered[i] = np.median(spontRate[mask])
                if method == 'Mean Window':
                    mask = (sites['start'] > start) & (sites['start'] < stop)
                    filtered[i] = np.mean(spontRate[mask])
                if method == 'Gaussian Window':
                    filtered[i] = self.gauss(spontRate, sites['start'], now, window)
        
        self.filterPlot.setData(x=sites['start'], y=filtered)
        
        return {'spontRate': spontRate, 'filteredSpontRate': filtered}
        
    @staticmethod
    def gauss(values, times, mean, sigma):
        a = 1.0 / (sigma * (2 * np.pi)**0.5)
        weights = np.exp(-((times-mean)**2) / (2 * sigma**2))
        weights /= weights.sum()
        return (weights * values).sum()
        

class EventStatisticsAnalyzer:
    def __init__(self):
        self.params = ptree.Parameter(name='Analysis Methods', type='group', children=[
                dict(name='Z-Score', type='bool', value=False),
                dict(name='Poisson', type='bool', value=False),
                dict(name='Poisson Multi', type='bool', value=True, children=[
                    dict(name='Amplitude', type='bool', value=False),
                    dict(name='Mean', type='float', readonly=True),
                    dict(name='Stdev', type='float', readonly=True),
                ]),
            ])
    
    def parameters(self):
        return self.params

    def process(self):
        pass
            
    
    

class Loader(QtGui.QWidget):
    def __init__(self, parent=None, host=None, dm=None):
        QtGui.QWidget.__init__(self, parent)
        self.host = host
        
        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)
        self.dbGui = DatabaseGui.DatabaseGui(dm=dm, tables={'Photostim.events': None, 'Photostim.sites': None, 'Photostim.maps': None})
        self.layout.addWidget(self.dbGui, 0, 0)
        
        self.tree = pg.TreeWidget()
        self.layout.addWidget(self.tree, 1, 0)
        
        self.loadBtn = QtGui.QPushButton('Load Map')
        self.layout.addWidget(self.loadBtn, 2, 0)
        self.loadBtn.clicked.connect(self.load)
        
        self.loadedLabel = QtGui.QLabel("Loaded: [none]")
        self.layout.addWidget(self.loadedLabel, 3, 0)
        
        self.populate()
        
    def populate(self):
        self.tree.clear()
        mapTable = self.dbGui.getTableName('Photostim.maps')
        if mapTable == '':
            return
            #raise Exception("No table selected for %s" % ident)
        db = self.dbGui.getDb()
        maps = db.select(mapTable, ['rowid','*'])
        
        paths = {}
        for rec in maps:
            if len(rec['scans']) == 0:
                continue
            
            ## convert (table, rowid) to (dirhandle, rowid) before creating Map
            rec['scans'] = [(db.getDir(*s), s[1]) for s in rec['scans']]
            path = rec['scans'][0][0].parent()
            
            if path not in paths:
                pathItem = pg.TreeWidgetItem([path.name(relativeTo=db.baseDir())])
                self.tree.addTopLevelItem(pathItem)
                paths[path] = pathItem
            
            item = pg.TreeWidgetItem([rec['description']])
            item.rec = rec
            paths[path].addChild(item)
            
    def load(self):
        sel = self.tree.selectedItems()
        if len(sel) != 1:
            raise Exception("Must select a single map to load.")
        sel = sel[0]
        if not hasattr(sel, 'rec'):
            raise Exception("Must select a map to load.")
        try: 
            self.host.loadMap(sel.rec)
            self.loadedLabel.setText("Loaded: %s" % (sel.parent().text(0) + '/' + sel.text(0)))
        except:
            self.loadedLabel.setText("Loaded: [none]")
            raise
        
class TimelineMarker(pg.GraphicsObject):
    def __init__(self):
        pg.GraphicsObject.__init__(self)
        self.times = []
        self.yRange=(0.1, 0.2)
        self.xRange=[float('inf'), float('-inf')]
        self.pen = pg.mkPen(None)
        self.brush = pg.mkBrush((200,200,255,200))
        
    def boundingRect(self):
        if self.xRange[0] == float('inf'):
            x1,x2 = 0,0
        else:
            x1,x2 = self.xRange
        return QtCore.QRectF(x1, 0, x2-x1, 1)
        
    def setTimes(self, times):
        """Times must be a list of (start, end) tuples."""
        self.clear()
        self.addTimes(times)
            
    def addTimes(self, times):
        for x1, x2 in times:
            t = QtGui.QGraphicsRectItem(QtCore.QRectF(x1, 0, x2-x1, 1))
            t.setParentItem(self)
            t.setPen(self.pen)
            t.setBrush(self.brush)
            self.xRange[0] = min(self.xRange[0], x1, x2)
            self.xRange[1] = max(self.xRange[1], x1, x2)
            self.prepareGeometryChange()
            self.times.append(t)
            
    def paint(self, p, *args):
        pass
        #p.setPen(pg.mkPen('r'))
        #p.drawRect(self.boundingRect())
            
    def clear(self):
        self.xRange
        s = self.scene()
        if s is not None:
            for t in self.times:
                s.removeItem(t)
                t.setParentItem(None)
        else:
            for t in self.times:
                t.setParentItem(None)
            
        self.times = []
            
    def setPen(self, pen):
        pen = pg.mkPen(pen)
        self.pen = pen
        for t in self.times:
            t.setPen(pen)
            
    def setBrush(self, brush):
        brush = pg.mkBrush(brush)
        self.brush = brush
        for t in self.times:
            t.setBrush(brush)
            
            
        
    def viewRangeChanged(self):
        self.resetTransform()
        r = self.viewRect()
        y1 = r.top() + r.height() * self.yRange[0]
        y2 = r.top() + r.height() * self.yRange[1]
        self.translate(0, y1)
        self.scale(1.0, abs(y2-y1))
        print y1, y2
        
