# -*- coding: utf-8 -*-
from __future__ import print_function
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


from acq4.util import Qt
from acq4.analysis.AnalysisModule import AnalysisModule
import os
from collections import OrderedDict
import acq4.util.DatabaseGui as DatabaseGui
from acq4.util.ColorMapper import ColorMapper
import acq4.pyqtgraph as pg
import acq4.pyqtgraph.parametertree as ptree
import numpy as np
import acq4.analysis.modules.Photostim.Scan as Scan
from acq4.analysis.modules.Photostim.Map import Map
import acq4.analysis.tools.poissonScore as poissonScore
import acq4.util.flowchart.EventDetection as FCEventDetection
from six.moves import range


class MapAnalyzer(AnalysisModule):
    dbIdentity = 'MapAnalyzer'
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        if self.dataModel is None:
            raise Exception("MapAnalyzer module requires a data model, but none is loaded yet.")
        
        self.currentMap = None
        self.analysisValid = False
        self.colorsValid = False
        
        self.ctrlLayout = pg.LayoutWidget()
        self.ctrl = ptree.ParameterTree(showHeader=False)
        self.ctrlLayout.addWidget(self.ctrl, row=0, col=0)
        self.recalcBtn = Qt.QPushButton('Recalculate')
        self.ctrlLayout.addWidget(self.recalcBtn, row=1, col=0)
        self.storeBtn = pg.FeedbackButton('Store to DB')
        self.ctrlLayout.addWidget(self.storeBtn, row=2, col=0)
        
        
        self.loader = Loader(host=self, dm=host.dataManager())
        
        
        modPath = os.path.abspath(os.path.dirname(__file__))
        self.colorMapper = ColorMapper(filePath=os.path.join(modPath, "colorMaps"))
        self._elements_ = OrderedDict([
            ('File Loader', {'type': 'fileInput', 'size': (300, 300), 'host': self, 'showFileTree': False}),
            ('Map Loader', {'type': 'ctrl', 'object': self.loader, 'size': (300, 300), 'pos': ('below', 'File Loader')}),
            ('Color Mapper', {'type':'ctrl', 'object': self.colorMapper, 'size': (800,200), 'pos': ('right', 'Map Loader')}),
            ('Canvas', {'type': 'canvas', 'size': (800, 400), 'pos':('right', 'Color Mapper'), 'args': {'name': 'MapAnalyzer'}}),
            ('Options', {'type': 'ctrl', 'object': self.ctrlLayout, 'size': (300, 500), 'pos': ('bottom', 'Map Loader')}),
            ('Data Plot', {'type': 'plot', 'pos': ('top', 'Color Mapper'), 'size': (800, 300)}),
            ('Score Histogram', {'type': 'plot', 'pos': ('bottom', 'Data Plot'), 'size': (800, 300)}),
            ('Timeline', {'type': 'plot', 'pos': ('bottom', 'Data Plot'), 'size': (800, 300)}),
            ('Stats Table', {'type': 'dataTree', 'pos': ('bottom', 'Canvas'), 'size': (800,300)}),
        ])
        host.resize(1100, 800)
        self.initializeElements()
        
        
        self.filterStage = EventFilter()
        self.spontRateStage = SpontRateAnalyzer(plot=self.getElement('Timeline', create=True))
        self.statsStage = EventStatisticsAnalyzer(histogramPlot=self.getElement('Score Histogram', create=True))
        self.regions = RegionMarker(self.getElement('Canvas', create=True))
        self.stages = [self.filterStage, self.spontRateStage, self.statsStage, self.regions]
        
        params = [
            dict(name='Time Ranges', type='group', children=[
                dict(name='Direct Start', type='float', value=0.498, suffix='s', step=0.001, siPrefix=True),
                dict(name='Stimulus', type='float', value=0.5, suffix='s', step=0.001, siPrefix=True),
                dict(name='Post Start', type='float', value=0.502, suffix='s', step=0.001, siPrefix=True),
                dict(name='Post Stop', type='float', value=0.700, suffix='s', step=0.001, siPrefix=True),
            ]),
        ]
        
        ## each processing stage comes with its own set of parameters
        for stage in self.stages:
            params.append(stage.parameters())
        
        self.params = ptree.Parameter.create(name='options', type='group', children=params)
        self.ctrl.setParameters(self.params, showTop=False)
        
        canvas = self.getElement('Canvas', create=True)
        #self.scalebar = pg.ScaleBar(100e-6)
        #canvas.addGraphicsItem(self.scalebar, name="ScaleBar")
        self.scalebar = pg.ScaleBar(size=500e-6)
        self.scalebar.setParentItem(canvas.view)
        self.scalebar.anchor((1, 1), (1, 1), offset=(-20, -20))
        
        ## Note: need to reconnect this!!
        #self.params.sigTreeStateChanged.connect(self.invalidate)
        self.recalcBtn.clicked.connect(self.recalcClicked)
        self.storeBtn.clicked.connect(self.storeToDB)
        self.params.param('Time Ranges').sigTreeStateChanged.connect(self.updateTimes)
        
        self.getElement('Color Mapper', create=True).sigChanged.connect(self.colorMapChanged)
        self.regions.sigRegionChanged.connect(self.processRegions)
        
    def elementChanged(self, element, old, new):
        name = element.name()

    def loadMap(self, rec):
        self.getElement('Canvas').clear()
        self.currentMap = Map(self, rec)
        self.currentMap.loadStubs()
        self.currentMap.sPlotItem.sigClicked.connect(self.mapPointClicked)

        self.getElement('Canvas').addGraphicsItem(self.currentMap.sPlotItem, movable=False)
        
        self.invalidate()
        self.loadFromDB()
        self.update()
                
    def loadScan(self, dh):
        ## called by Map objects to load scans
        scans = Scan.loadScanSequence(dh, self)
        #if len(scans) > 1:
            #raise Exception("Scan sequences not supported yet.")
        for scan in scans:
            ci = scan.canvasItem()
            self.getElement('Canvas').addItem(ci)
            ci.hide()
            scan.canvasItem().graphicsItem().sigClicked.connect(self.scanPointClicked)

        return scans
        
    def loadScanFromDB(self, sourceDir):
        ## Called by Scan as it is loading
        statTable = self.loader.dbGui.getTableName('Photostim.sites')
        eventTable = self.loader.dbGui.getTableName('Photostim.events')
        db = self.loader.dbGui.getDb()
        stats = db.select(statTable, '*', where={'ProtocolSequenceDir': sourceDir})
        events = db.select(eventTable, '*', where={'ProtocolSequenceDir': sourceDir}, toArray=True)
        return events, stats
        
    def loadSpotFromDB(self, sourceDir):
        ## Called by Scan as it is loading single points
        statTable = self.loader.dbGui.getTableName('Photostim.sites')
        eventTable = self.loader.dbGui.getTableName('Photostim.events')
        db = self.loader.dbGui.getDb()
        stats = db.select(statTable, '*', where={'ProtocolDir': sourceDir})
        events = db.select(eventTable, '*', where={'ProtocolDir': sourceDir}, toArray=True)
        return events, stats
        
    def loadFileRequested(self, fhList):
        canvas = self.getElement('Canvas')
        model = self.dataModel

        with pg.ProgressDialog("Loading data..", 0, len(fhList)) as dlg:
            for fh in fhList:
                try:
                    ## TODO: use more clever detection of Scan data here.
                    if fh.isFile() or model.dirType(fh) == 'Cell':
                        canvas.addFile(fh, movable=False)
                    #else:
                        #self.loadScan(fh)
                        return True
                    else:
                        return False
                except:
                    debug.printExc("Error loading file %s" % fh.name())
                    return False
                dlg += 1
                if dlg.wasCanceled():
                    return
        

    def getDb(self):
        db = self.loader.dbGui.getDb()
        return db
        
        
    def getColor(self, stats, data):
        ## return the color to represent this data
        
        ## merge data together
        d2 = data.copy()
        del d2['sites']
        d2 = OrderedDict(d2)
        d2.update(stats)
        del d2['ProtocolDir']
        
        mapper = self.getElement('Color Mapper')
        mapper.setArgList(list(d2.keys()))
        
        return mapper.getColor(d2)
        
    def colorMapChanged(self):
        self.colorsValid = False
        self.update()
        
    def update(self):
        if not self.analysisValid:
            print("Updating analysis..")
            map = self.currentMap
            if map is None:
                return
            scans = map.scans
            
            ## Get a list of all stimulations in the map and their times.
            sites = []
            for s in scans:
                sites.extend(s.getTimes())
            sites.sort(key=lambda i: i[1])
            
            ## get list of all events
            events = []
            for scan in scans:
                ev = scan.getAllEvents()
                if ev is not None:
                    events.append(ev.copy())
            
            ## set up table of per-stimulation data
            spontRates = np.zeros(len(sites), dtype=[('ProtocolDir', object), ('start', float), ('stop', float), ('spontRate', float), ('filteredSpontRate', float)])
            spontRates[:] = [s+(0,0) for s in sites] ## fill with data
            
            filtered = None
            if len(events) > 0:
                events = np.concatenate(events)
                filtered = self.filterStage.process(events)
            
                ## compute spontaneous rates
                sr = self.spontRateStage.process(spontRates, filtered)
                spontRates['spontRate'] = sr['spontRate']
                spontRates['filteredSpontRate'] = sr['filteredSpontRate']
            else:
                sr = {'ampMean': 0, 'ampStdev': 0}
            
            output = self.statsStage.process(map, spontRates, filtered, sr['ampMean'], sr['ampStdev'])
            self.analysisValid = True
            
        if not self.colorsValid:
            self.currentMap.recolor()
            self.colorsValid = True
        
    def invalidate(self):
        print("invalidate.")
        self.analysisValid = False
        self.colorsValid = False

    def recalcClicked(self):
        self.invalidate()
        self.update()
        
    def updateTimes(self):
        self.params['Spontaneous Rate', 'Stop Time'] = self.params['Time Ranges', 'Direct Start']
        self.params['Analysis Methods', 'Stimulus Time'] = self.params['Time Ranges', 'Stimulus']
        self.params['Analysis Methods', 'Pre Stop'] = self.params['Time Ranges', 'Direct Start']
        self.params['Analysis Methods', 'Post Start'] = self.params['Time Ranges', 'Post Start']
        self.params['Analysis Methods', 'Post Stop'] = self.params['Time Ranges', 'Post Stop']
        
        
    def scanPointClicked(self, gitem, points):
        plot = self.getElement('Data Plot', create=True)
        plot.clear()
        scan = gitem.scan
        scan.displayData(points[0].data(), plot, 'w')
        
    def mapPointClicked(self, gitem, points):
        plot = self.getElement('Data Plot', create=True)
        plot.clear()
        data = []
        for p in points:
            for source in p.data()['sites']:
                data.append(source)
            #data.extend(p.data)
        for i in range(len(data)):
            scan, fh = data[i]
            scan.displayData(fh, plot, pen=(i, len(data)*1.3), eventFilter=self.filterStage.process)
        
        self.getElement('Stats Table').setData(points[0].data())

    def storeToDB(self):
        try:
            self.update()
            
            ## Determine currently selected table to store to
            dbui = self.getElement('Map Loader').dbGui
            identity = self.dbIdentity+'.sites'
            mapTable = dbui.getTableName('Photostim.maps')
            table = dbui.getTableName(identity)
            db = dbui.getDb()

            if db is None:
                raise Exception("No DB selected")
            
            fields = OrderedDict([
                ('Map', {'Type': 'int', 'Link': mapTable}),
                #('CellDir', 'directory:Cell'),
                ('FirstSite', 'directory:Protocol'),
                ('Sites', 'blob'),
                ('PoissonScore', 'real'),
                ('PoissonScore_Pre', 'real'),
                ('PoissonAmpScore', 'real'),
                ('PoissonAmpScore_Pre', 'real'),
                ('HasInput', 'int'),
                ('FirstLatency', 'real'),
                ('ZScore', 'real'),
                ('FitAmpSum', 'real'),
                ('FitAmpSum_Pre', 'real'),
                ('NumEvents', 'real'),
                ('SpontRate', 'real'),
                ('DirectPeak', 'real'),
                ('Region', 'text'),
            ])
            
            mapRec = self.currentMap.getRecord()
            data = []
            for spot in self.currentMap.spots:
                rec = {}
                for k in fields:
                    if k in spot['data']:
                        rec[k] = spot['data'][k]
                #rec['CellDir'] = mapRec['cell'] 
                rec['Map'] = self.currentMap.rowID
                sites = [s[1] for s in spot['data']['sites']]
                rec['FirstSite'] = sites[0]
                rec['Sites'] = [db.getDirRowID(s) for s in sites]
                data.append(rec)
                
            
            with db.transaction():
                ## Make sure target table exists and has correct columns, links to input file
                db.checkTable(table, owner=identity, columns=fields, create=True, addUnknownColumns=True, indexes=[['Map']])
                
                # delete old
                db.delete(table, where={'Map': self.currentMap.rowID})

                # write new
                with pg.ProgressDialog("Storing map data...", 0, 100) as dlg:
                    for n, nmax in db.iterInsert(table, data, chunkSize=100):
                        dlg.setMaximum(nmax)
                        dlg.setValue(n)
                        if dlg.wasCanceled():
                            raise HelpfulException("Scan store canceled by user.", msgType='status')
            self.storeBtn.success()
        except:
            self.storeBtn.failure()            
            raise
        
    def processRegions(self):
        ## Compute regions for each spot
        for spot in self.currentMap.spots:
            dh = spot['data']['sites'][0][1]
            pos = spot['pos']
            rgn = self.regions.getRegion(pos)
            spot['data']['Region'] = rgn
            #print dh,rgn
            
        ## Store ROI positions with cell
        cell = self.currentMap.getRecord()['cell'] 
        rgns = self.regions.getRegions()
        cell.setInfo(MapAnalyzer_Regions=rgns)
        
    def loadFromDB(self):
        ## read in analysis from DB
        
        dbui = self.getElement('Map Loader').dbGui
        identity = self.dbIdentity+'.sites'
        mapTable = dbui.getTableName('Photostim.maps')
        table = dbui.getTableName(identity)
        db = dbui.getDb()

        if db is None:
            raise Exception("No DB selected")
        if not db.hasTable(table):
            return None
        
        fields = OrderedDict([
            ('Map', {'Type': 'int', 'Link': mapTable}),
            #('Sites', 'blob'),
            ('PoissonScore', 'real'),
            ('PoissonScore_Pre', 'real'),
            ('PoissonAmpScore', 'real'),
            ('PoissonAmpScore_Pre', 'real'),
            ('HasInput', 'int'),
            ('FirstLatency', 'real'),
            ('ZScore', 'real'),
            ('FitAmpSum', 'real'),
            ('FitAmpSum_Pre', 'real'),
            ('NumEvents', 'real'),
            ('SpontRate', 'real'),
            ('DirectPeak', 'real'),
            ('Region', 'text'),
        ])
        
        #mapRec = self.currentMap.getRecord()
        recs = db.select(table, ['rowid', '*'], where={'Map': self.currentMap.rowID})
        if len(recs) == len(self.currentMap.spots):
            for i, spot in enumerate(self.currentMap.spots):
                
                for k in list(fields.keys()) + list(recs[i].keys()):
                    spot['data'][k] = recs[i].get(k, None)
            self.analysisValid = True
            print("reloaded analysis from DB", self.currentMap.rowID)
        else:
            print("analysis incomplete:", len(recs), len(self.currentMap.spots))
        
        
        
        
        
#class EventFilterParameterItem(WidgetParameterItem):
    #def __init__(self, param, depth):
        #WidgetParameterItem.__init__(self, param, depth)
        #self.subItem = Qt.QTreeWidgetItem()
        #self.addChild(self.subItem)
        #self.filter = FCEventDetection.EventFilter('eventFilter')

    #def treeWidgetChanged(self):
        #self.treeWidget().setFirstItemColumnSpanned(self.subItem, True)
        #self.treeWidget().setItemWidget(self.subItem, 0, self.textBox)
        #self.setExpanded(True)
        
    #def makeWidget(self):
        #self.textBox = Qt.QTextEdit()
        #self.textBox.setMaximumHeight(100)
        #self.textBox.value = lambda: str(self.textBox.toPlainText())
        #self.textBox.setValue = self.textBox.setPlainText
        #self.textBox.sigChanged = self.textBox.textChanged
        #return self.textBox
        
#class TextParameter(Parameter):
    #"""Editable string; displayed as large text box in the tree."""
    #itemClass = TextParameterItem

class EventFilter:
    def __init__(self):
        self.keyList = []
        
        self.params = ptree.Parameter.create(name='Event Selection', type='group', addText='Add filter..', addList=self.keyList, children=[
                dict(name='Amplitude Sign', type='list', values=['+', '-'], value='+'),
            ])
        self.params.addNew = self.addNew
            
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
            if fp.name() == 'Amplitude Sign':
                continue
            fp.param('Field').setLimits(keys)
    
    def process(self, events):
        if len(events) == 0:
            return events
        
        self.updateKeys(events.dtype.names)
        
        if self.params['Amplitude Sign'] == '+':
            events = events[events['fitAmplitude'] > 0]
        else:
            events = events[events['fitAmplitude'] < 0]
        
        for fp in self.params:
            if fp.name() == 'Amplitude Sign':
                continue
            if fp.value() is False:
                continue
            key, mn, mx = fp['Field'], fp['Min'], fp['Max']
            vals = events[key]
            mask = (vals >= mn) * (vals < mx)  ## Use inclusive minimum and non-inclusive maximum. This makes it easier to create non-overlapping selections
            events = events[mask]
            
        return events
        

class SpontRateAnalyzer:
    def __init__(self, plot=None):
        self.plot = plot
        self.spontRatePlot = plot.plot(pen=0.5)
        self.filterPlot = plot.plot(pen='g')
        self.timeMarker = TimelineMarker()
        plot.addItem(self.timeMarker)
        
        self.params = ptree.Parameter.create(name='Spontaneous Rate', type='group', children=[
                dict(name='Stop Time', type='float', value=0.495, suffix='s', siPrefix=True, step=0.005),
                dict(name='Method', type='list', values=['Constant', 'Constant (Mean)', 'Constant (Median)', 'Mean Window', 'Median Window', 'Gaussian Window'], value='Gaussian Window'),
                dict(name='Constant Rate', type='float', value=0, suffix='Hz', limits=[0, None], siPrefix=True),
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
        
        self.timeMarker.setTimes(list(zip(sites['start'], sites['stop'])))
        
        ## filter events by pre-region
        stimTime = self.params['Stop Time']
        events = events[events['fitTime'] < stimTime]
        
        ## measure spont. rate for each handle
        spontRate = []
        amps = []
        for site in sites:
            ev = events[events['ProtocolDir'] == site['ProtocolDir']]
            spontRate.append(len(ev) / stimTime)
            amps.extend(ev['fitAmplitude'])
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
            for i in range(len(spontRate)):
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
        if len(amps) == 0:
            ret = {'spontRate': spontRate, 'filteredSpontRate': filtered, 'ampMean': 0, 'ampStdev': 0}
        else:
            ret = {'spontRate': spontRate, 'filteredSpontRate': filtered, 'ampMean': np.mean(amps), 'ampStdev': np.std(amps)}
        assert not np.isnan(ret['ampMean']) and not np.isnan(ret['ampStdev'])
        return ret
        
    @staticmethod
    def gauss(values, times, mean, sigma):
        a = 1.0 / (sigma * (2 * np.pi)**0.5)
        weights = np.exp(-((times-mean)**2) / (2 * sigma**2))
        weights /= weights.sum()
        return (weights * values).sum()
        

class EventStatisticsAnalyzer:
    def __init__(self, histogramPlot):
        self.histogram = histogramPlot
        self.params = ptree.Parameter.create(name='Analysis Methods', type='group', children=[
                dict(name='Stimulus Time', type='float', value=0.5, suffix='s', siPrefix=True, step=0.001),
                dict(name='Pre Start', type='float', value=0.0, suffix='s', siPrefix=True, step=0.001),
                dict(name='Pre Stop', type='float', value=0.495, suffix='s', siPrefix=True, step=0.001),
                dict(name='Post Start', type='float', value=0.502, suffix='s', siPrefix=True, step=0.001),
                dict(name='Post Stop', type='float', value=0.7, suffix='s', siPrefix=True, step=0.001),
                #dict(name='Z-Score', type='bool', value=False),
                #dict(name='Poisson', type='bool', value=False),
                #dict(name='Poisson Multi', type='bool', value=True, children=[
                    #dict(name='Amplitude', type='bool', value=False),
                    #dict(name='Mean', type='float', readonly=True),
                    #dict(name='Stdev', type='float', readonly=True),
                #]),
                dict(name='Threshold Parameter', type='list', values=['PoissonScore', 'PoissonAmpScore', 'ZScore', 'FitAmpSum']),
                dict(name='Threshold', type='float', value=1000., dec=True, minStep=1, step=0.5),
            ])
    
    def parameters(self):
        return self.params

    def process(self, map, spontRateTable, events, ampMean, ampStdev):
        stimTime = self.params['Stimulus Time']
        
        preStart = self.params['Pre Start']
        preStop = self.params['Pre Stop']
        preDt = preStop - preStart
        
        postStart = self.params['Post Start']
        postStop = self.params['Post Stop']
        postDt = postStop - postStart
        
        ## generate dict of spont. rates for each site
        spontRate = {}
        for rec in spontRateTable:
            spontRate[rec['ProtocolDir']] = rec
            
        if events is None:  ## Didn't get an array, need to fake the fields
            events = np.empty(0, dtype=[('ProtocolDir', object), ('fitTime', float), ('fitAmplitude', float)])
            
        
        ## filter events by time
        postMask = (events['fitTime'] > postStart)  &  (events['fitTime'] < postStop)
        postEvents = events[postMask]
        preMask = (events['fitTime'] > preStart)  &  (events['fitTime'] < preStop)
        preEvents = events[preMask]
        
        preScores = {'PoissonScore': [], 'PoissonAmpScore': [], 'SpontZScore':[]}
        postScores = {'PoissonScore': [], 'PoissonAmpScore': [], 'ZScore': [], 'FitAmpSum': []}
        
        
        for site in map.spots:
            postSiteEvents = []
            preSiteEvents = []
            rates = []
            latencies = []
            nEvents = []
            
            ## generate lists of post-stimulus events for each site
            for scan,dh in site['data']['sites']:
                ## collect post-stim events
                ev = postEvents[postEvents['ProtocolDir'] == dh]
                ev2 = np.empty(len(ev), dtype=[('time', float), ('amp', float)])
                ev2['time'] = ev['fitTime'] - stimTime
                ev2['amp'] = ev['fitAmplitude']
                postSiteEvents.append(ev2)
                latencies.append(ev2['time'].min() if len(ev2) > 0 else -1)
                nEvents.append(len(ev2))
                
                ## collect pre-stim events
                ev = preEvents[preEvents['ProtocolDir'] == dh]
                ev2 = np.empty(len(ev), dtype=[('time', float), ('amp', float)])
                ev2['time'] = ev['fitTime']
                ev2['amp'] = ev['fitAmplitude']
                preSiteEvents.append(ev2)
                
                rates.append(spontRate[dh]['filteredSpontRate'])
        
            ## compute score for each site
            ## note that keys added to site here are ultimately passed to host.getColor via Map.recolor
            site['data']['spontaneousRates'] = rates
            site['data']['events'] = events
            site['data']['ampMean'] = ampMean
            site['data']['ampStdev'] = ampStdev
            site['data']['PoissonScore'] = poissonScore.PoissonScore.score(postSiteEvents, rates, tMax=postDt)
            site['data']['PoissonAmpScore'] = poissonScore.PoissonAmpScore.score(postSiteEvents, rates, tMax=postDt, ampMean=ampMean, ampStdev=ampStdev)
            postScores['PoissonScore'].append(site['data']['PoissonScore'])
            postScores['PoissonAmpScore'].append(site['data']['PoissonAmpScore'])
            
            site['data']['PoissonScore_Pre'] = poissonScore.PoissonScore.score(preSiteEvents, rates, tMax=postDt)
            site['data']['PoissonAmpScore_Pre'] = poissonScore.PoissonAmpScore.score(preSiteEvents, rates, tMax=postDt, ampMean=ampMean, ampStdev=ampStdev)
            preScores['PoissonScore'].append(site['data']['PoissonScore_Pre'])
            preScores['PoissonAmpScore'].append(site['data']['PoissonAmpScore_Pre'])
            
            #if site['data']['sites'][0][1].shortName() == '051':
                #raise Exception()
            
            ## Compute some extra statistics for this map site
            stats = [s[0].getStats(s[1]) for s in site['data']['sites']]   ## pre-recorded stats for all sub-sites in this map site
            if 'ZScore' in stats[0].keys():
                site['data']['ZScore'] = np.median([s['ZScore'] for s in stats])
                #site['data']['SpontZScore'] = np.median([s['SpontZScore'] for s in stats])
                postScores['ZScore'].append(site['data']['ZScore'])
                #preScores['SpontZScore'].append(site['data']['SpontZScore'])
            if 'directFitPeak' in stats[0].keys():
                site['data']['DirectPeak'] = np.median([s['directFitPeak'] for s in stats])
            if 'fitAmplitude_PostRegion_sum' in stats[0].keys():
                site['data']['FitAmpSum'] = np.median([s['fitAmplitude_PostRegion_sum'] for s in stats])
                postScores['FitAmpSum'].append(site['data']['FitAmpSum'])
            #site['data']['FitAmpSum_Pre'] = np.median([s['fitAmplitude_PreRegion_sum'] for s in stats])  
            site['data']['FirstLatency'] = np.median(latencies)
            site['data']['NumEvents'] = np.median(nEvents)
            site['data']['SpontRate'] = np.median(rates)
            
            
            
            ## Decide whether this site has input
            tparam = self.params['Threshold Parameter']
            if tparam not in site['data']:
                raise Exception('invalid threshold parameter')
            score = site['data'][tparam]
            site['data']['HasInput'] = score > self.params['Threshold']
            
        ## plot histogram of scores for threshold parameter
        if self.params['Threshold Parameter'] == 'PoissonScore':
            pre, post = preScores['PoissonScore'], postScores['PoissonScore']
        elif self.params['Threshold Parameter'] == 'PoissonAmpScore':
            pre, post = preScores['PoissonAmpScore'], postScores['PoissonAmpScore']
        elif self.params['Threshold Parameter'] == 'ZScore':
            if 'SpontZScore' in site['data'].keys():
                pre, post = preScores['SpontZScore'], postScores['ZScore']
            else:
                pre = None
                post = postScores[self.params['Threshold Parameter']]                
        else:
            pre = None
            post = postScores[self.params['Threshold Parameter']]
            
        self.histogram.clear()
        if pre is not None:
            self.histogram.plot(x=pre, y=np.arange(len(pre)), pen=None, symbol='o', symbolPen=None, symbolBrush=(0, 0, 255, 50))
        self.histogram.plot(x=post, y=np.arange(len(post)), pen=None, symbol='o', symbolPen=None, symbolBrush=(255, 255, 0, 50))
        self.histogram.autoRange()
        #self.threshLine = pg.InfiniteLine(angle=90)
        #self.histogram.addItem(self.threshLine)
        #self.threshLine.setPos(self.params['Threshold'])
    
class RegionMarker(Qt.QObject):
    """Allows user to specify multiple anatomical regions for classifying cells.
    Region names are written into custom DB columns for each site."""
    sigRegionChanged = Qt.Signal(object)
    
    def __init__(self, canvas):
        Qt.QObject.__init__(self)
        self.params = RegionsParameter(canvas)
        self.params.sigRegionChanged.connect(self.sigRegionChanged)
    
    def parameters(self):
        return self.params

    def getRegion(self, pos):
        ## return the first region containing pos
        for name,roi in self.params.getRegions():
            if roi.mapToParent(roi.shape()).contains(pos):
                return name
        return None
            
    def getRegions(self):
        ## Return a dict of all regions
        rgns = {}
        for name,roi in self.params.getRegions():
            pts = []
            for n,pos in roi.getLocalHandlePositions():
                pos = roi.mapToView(pos)
                pts.append((pos.x(), pos.y()))
            rgns[name] = pts
        return rgns
        
    #def process(self, map, spontRateTable, events, ampMean, ampStdev):
        #stimTime = self.params['Stimulus Time']
    
class RegionsParameter(ptree.types.GroupParameter):
    
    sigRegionChanged = Qt.Signal(object)
    
    def __init__(self, canvas):
        self.canvas = canvas
        ptree.types.GroupParameter.__init__(self, name="Anatomical Regions", addText='Add Region..', children=[
            ])
        self.sigTreeStateChanged.connect(self.treeChanged)
        
    def getRegions(self):
        return [(rgn.name(), rgn.roi) for rgn in self if hasattr(rgn, 'roi')]

        
    def addNew(self):
        rgn = ptree.Parameter.create(name='region', autoIncrementName=True, renamable=True, removable=True, type='bool', value=True, children=[
            dict(name='DB Column', type='str', value='Region'),
            dict(name='Color', type='color'),
            ])
        self.addChild(rgn)
        
        ## find the center of the view
        view = self.canvas.view
        center = view.viewRect().center()
        size = [x*50 for x in view.viewPixelSize()]
        pts = [center, center+pg.Point(size[0], 0), center+pg.Point(0, size[1])]
        
        roi = pg.PolyLineROI(pts, closed=True)
        roi.setZValue(1000)
        view.addItem(roi)
        rgn.roi = roi
        roi.rgn = rgn
        roi.sigRegionChangeFinished.connect(self.regionChanged)
        
    def regionChanged(self, roi):
        self.sigRegionChanged.emit(self)
        
    def treeChanged(self, *args):
        for rgn in self:
            if not hasattr(rgn, 'roi'):
                continue
            rgn.roi.setVisible(rgn.value())
            rgn.roi.setPen(rgn['Color'])
            
        

class Loader(pg.LayoutWidget):
    def __init__(self, parent=None, host=None, dm=None):
        pg.LayoutWidget.__init__(self, parent)
        self.host = host
        
        
        self.dbGui = DatabaseGui.DatabaseGui(dm=dm, tables={'Photostim.events': None, 'Photostim.sites': None, 'Photostim.maps': None, MapAnalyzer.dbIdentity+'.sites': 'map_sites'})
        self.addWidget(self.dbGui)
        
        self.tree = pg.TreeWidget()
        self.tree.setHeaderHidden(True)
        self.addWidget(self.tree, 1, 0)

        self.loadBtn = Qt.QPushButton('Load Map')
        self.addWidget(self.loadBtn, 2, 0)
        self.loadBtn.clicked.connect(self.load)
        
        self.refreshBtn = Qt.QPushButton('Reload Map List')
        self.addWidget(self.refreshBtn, 3, 0)
        self.refreshBtn.clicked.connect(self.populate)
        
        self.loadedLabel = Qt.QLabel("Loaded: [none]")
        self.addWidget(self.loadedLabel, 4, 0)
        
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
        with pg.ProgressDialog("Reading map table...", 0, len(maps)) as dlg:
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
                
                dlg += 1
                if dlg.wasCanceled():
                    raise Exception("User cancelled map list construction; some maps may not be displayed.")
        self.tree.sortItems(0, Qt.Qt.AscendingOrder)
            
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
        return Qt.QRectF(x1, 0, x2-x1, 1)
        
    def setTimes(self, times):
        """Times must be a list of (start, end) tuples."""
        self.clear()
        self.addTimes(times)
            
    def addTimes(self, times):
        for x1, x2 in times:
            t = Qt.QGraphicsRectItem(Qt.QRectF(x1, 0, x2-x1, 1))
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
        self.xRange = [float('inf'), float('-inf')]
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
        #print y1, y2
        
