# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
import lib.analysis.modules.EventDetector as EventDetector
import MapCtrlTemplate
import DatabaseGui
from flowchart import *
import os
from advancedTypes import OrderedDict
import debug
import ColorMapper
#import FileLoader

class Photostim(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        self.dbIdentity = "Photostim"  ## how we identify to the database; this determines which tables we own
        self.selectedSpot = None

        self.mapFields = {
            'name': 'text',
            'description': 'text',
            'scans': 'blob',
            'mode': 'text',
            'holding': 'real',
            'internal': 'text',
            'acsf': 'text',
            'drug': 'text',
            'temp': 'real',
        }

        ## setup analysis flowchart
        modPath = os.path.abspath(os.path.split(__file__)[0])
        flowchartDir = os.path.join(modPath, "analysis_fc")
        self.flowchart = Flowchart(filePath=flowchartDir)
        self.flowchart.addInput('events')
        self.flowchart.addInput('regions')
        self.flowchart.addOutput('dataOut')
        self.analysisCtrl = self.flowchart.widget()
        
        ## color mapper
        self.mapper = ColorMapper.ColorMapper(filePath=os.path.join(modPath, "colormaps"))
        self.mapCtrl = QtGui.QWidget()
        self.mapLayout = QtGui.QVBoxLayout()
        self.mapCtrl.setLayout(self.mapLayout)
        self.recolorBtn = QtGui.QPushButton("Recolor")
        self.mapLayout.addWidget(self.analysisCtrl)
        self.mapLayout.addWidget(self.mapper)
        self.mapLayout.addWidget(self.recolorBtn)
        
        ## setup map DB ctrl
        self.dbCtrl = DBCtrl(self, self.dbIdentity)
        
        ## storage for map data
        #self.scanItems = {}
        self.maps = []
        
        ## create event detector
        fcDir = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "detector_fc")
        self.detector = EventDetector.EventDetector(host, flowchartDir=fcDir, dbIdentity=self.dbIdentity+'.events')
        
        ## override some of its elements
        self.detector.setElement('File Loader', self)
        self.detector.setElement('Database', self.dbCtrl)
        
            
        ## Create element list, importing some gui elements from event detector
        elems = self.detector.listElements()
        self._elements_ = OrderedDict([
            ('Database', {'type': 'ctrl', 'object': self.dbCtrl}),
            ('Canvas', {'type': 'canvas', 'pos': ('right',), 'size': (400,400), 'allowTransforms': False}),
            #('Maps', {'type': 'ctrl', 'pos': ('bottom', 'Database'), 'size': (200,200), 'object': self.mapDBCtrl}),
            ('Detection Opts', elems['Detection Opts'].setParams(pos=('bottom', 'Database'), size= (200,500))),
            ('File Loader', {'type': 'fileInput', 'size': (200, 300), 'pos': ('above', 'Database'), 'host': self}),
            ('Data Plot', elems['Data Plot'].setParams(pos=('bottom', 'Canvas'), size=(800,200))),
            ('Filter Plot', elems['Filter Plot'].setParams(pos=('bottom', 'Data Plot'), size=(800,200))),
            ('Output Table', elems['Output Table'].setParams(pos=('below', 'Filter Plot'), size=(800,200))),
            ('Stats', {'type': 'dataTree', 'size': (800,200), 'pos': ('below', 'Output Table')}),
            ('Map Opts', {'type': 'ctrl', 'object': self.mapCtrl, 'pos': ('left', 'Canvas'), 'size': (200,400)}),
        ])

        self.initializeElements()
        
        try:
            ## load default chart
            self.flowchart.loadFile(os.path.join(flowchartDir, 'default.fc'))
        except:
            debug.printExc('Error loading default flowchart:')
        
        
        self.detector.flowchart.sigOutputChanged.connect(self.detectorOutputChanged)
        self.flowchart.sigOutputChanged.connect(self.analyzerOutputChanged)
        self.recolorBtn.clicked.connect(self.recolor)
        
        

            
    def loadFileRequested(self, fh):
        canvas = self.getElement('Canvas')
        try:
            if fh.isFile():
                canvas.addFile(fh)
            else:
                scan = canvas.addFile(fh)
                #self.scanItems[fh] = scan
                self.maps.append(Map(self, fh, scan))
                scan.item.sigPointClicked.connect(self.scanPointClicked)
            return True
        except:
            debug.printExc("Error loading file %s" % fh.name())
            return False
    
    def storeToDB(self):
        pass

    def getClampFile(self, dh):
        try:
            return dh['Clamp2.ma']
        except:
            return dh['Clamp1.ma']

    def scanPointClicked(self, point):
        #print "click!", point.data
        self.detector.loadFileRequested(self.getClampFile(point.data))
        self.selectedSpot = point
        
    def detectorOutputChanged(self):
        output = self.detector.flowchart.output()
        #table = self.getElement('Stats')
        #stats = self.detector.flowchart.output()['stats']
        #print stats
        #table.setData(stats)
        self.flowchart.setInput(**output)
        for m in self.maps:
            m.forgetEvents()

    def analyzerOutputChanged(self):
        table = self.getElement('Stats')
        stats = self.flowchart.output()['dataOut']
        table.setData(stats)
        if stats is None:
            return
        self.mapper.setArgList(stats.keys())
        for m in self.maps:
            m.forgetStats()
        
    def recolor(self):
        for i in range(len(self.maps)):
            m = self.maps[i]
            m.recolor(i, len(self.maps))

    def getColor(self, stats):
        return self.mapper.getColor(stats)

    def processEvents(self, fh):
        return self.detector.process(fh)

    def processStats(self, data):
        return self.flowchart.process(**data)['dataOut']

    def storeDBSpot(self):
        dbui = self.getElement('Database')
        identity = self.dbIdentity+'.sites'
        table = dbui.getTableName(identity)
        db = dbui.getDb()
        
        ## get events and stats for selected spot
        spot = self.selectedSpot
        if spot is None:
            raise Exception("No spot selected")
        fh = self.getClampFile(spot.data)
        parentDir = fh.parent()
        p2 = parentDir.parent()
        if db.dirTypeName(p2) == 'ProtocolSequence':
            parentDir = p2
            
        ## ask eventdetector to store events for us.
        #print parentDir
        self.detector.storeToDB(parentDir=parentDir)

        ## store stats
        data = self.flowchart.output()['dataOut'].copy()
        if db is None:
            raise Exception("No DB selected")

        pTable, pRow = db.addDir(parentDir)
        
        name = fh.name(relativeTo=parentDir)
        data['SourceFile'] = name
        data['SourceDir'] = pRow
        
        ## determine the set of fields we expect to find in the table
        fields = OrderedDict([
            ('SourceDir', 'int'),
            ('SourceFile', 'text'),
        ])
        fields.update(db.describeData(data))
        
        ## Make sure target table exists and has correct columns, links to input file
        db.checkTable(table, owner=identity, fields=fields, links=[('SourceDir', pTable)], create=True)
        
        # delete old
        db.delete(table, "SourceDir=%d and SourceFile='%s'" % (pRow, name))

        # write new
        db.insert(table, data)


class Map:
    def __init__(self, host, source, item):
        self.source = source
        self.item = item
        self.host = host
        self.events = {}
        self.stats = {}
        
    def forgetEvents(self):
        self.events = {}
        self.forgetStats()
        
    def forgetStats(self):
        self.stats = {}
        
    def recolor(self, n, nMax):
        spots = self.spots()
        progressDlg = QtGui.QProgressDialog("Computing spot colors (Map %d/%d)" % (n+1,nMax), "Cancel", 0, len(spots))
        #progressDlg.setWindowModality(QtCore.Qt.WindowModal)
        progressDlg.setMinimumDuration(250)
        ops = []
        try:
            for i in range(len(spots)):
                spot = spots[i]
                fh = spot.data
                stats = self.getStats(fh)
                color = self.host.getColor(stats)
                ops.append((spot, color))
                progressDlg.setValue(i+1)
                QtGui.QApplication.processEvents()
                if progressDlg.wasCanceled():
                    raise Exception("Recolor canceled by user.")
        except:
            raise
        finally:
            ## close progress dialog no matter what happens
            progressDlg.setValue(len(spots))
        
        ## delay until the very end for speed.
        for spot, color in ops:
            spot.setBrush(color)
        
        
            
    def getStats(self, fh):
        if fh not in self.stats:
            events = self.getEvents(fh)
            stats = self.host.processStats(events)
            self.stats[fh] = stats
        return self.stats[fh]

    def getEvents(self, fh):
        if fh not in self.events:
            events = self.host.processEvents(fh)
            self.events[fh] = events
        return self.events[fh]
        
    def spots(self):
        gi = self.item.item
        return gi.points()



class DBCtrl(QtGui.QWidget):
    """Interface for reading and writing the maps table.
    A map consists of one or more (probably overlapping) scans and associated meta-data."""
    def __init__(self, host, identity):
        QtGui.QWidget.__init__(self)
        self.host = host
        self.dbIdentity = identity
        
        ## DB tables we will be using  {owner: defaultTableName}
        tables = OrderedDict([
            (self.dbIdentity+'.maps', 'Photostim_maps'),
            (self.dbIdentity+'.sites', 'Photostim_sites'),
            (self.dbIdentity+'.events', 'Photostim_events')
        ])
        
        self.layout = QtGui.QVBoxLayout()
        self.layout.setSpacing(0)
        self.setLayout(self.layout)
        self.dbgui = DatabaseGui.DatabaseGui(dm=host.dataManager(), tables=tables)
        self.layout.addWidget(self.dbgui)
        for name in ['getTableName', 'getDb']:
            setattr(self, name, getattr(self.dbgui, name))
        
        self.ui = MapCtrlTemplate.Ui_Form()
        self.mapWidget = QtGui.QWidget()
        self.ui.setupUi(self.mapWidget)
        self.layout.addWidget(self.mapWidget)
        
        
        
        self.ui.newMapBtn.clicked.connect(self.newMapClicked)
        self.ui.loadMapBtn.clicked.connect(self.loadMapClicked)
        self.ui.delMapBtn.clicked.connect(self.delMapClicked)
        self.ui.addScanBtn.clicked.connect(self.addScanClicked)
        self.ui.removeScanBtn.clicked.connect(self.removeScanClicked)
        self.ui.clearDBSpotBtn.clicked.connect(self.clearDBSpot)
        self.ui.storeDBSpotBtn.clicked.connect(self.storeDBSpot)
        self.ui.clearDBScanBtn.clicked.connect(self.clearDBScan)
        self.ui.storeDBScanBtn.clicked.connect(self.storeDBScan)

    def listMaps(self, cell):
        """List all maps associated with the file handle for cell"""
        pass


    def newMapClicked(self):
        ## Create a new map in the database
        pass
    
    def loadMapClicked(self):
        ## Load the selected map into the canvas
        pass
    
    def delMapClicked(self):
        ## remove the selected map from the database
        pass
    
    def addScanClicked(self):
        ## Add the selected scan to the selected map
        pass
    
    def removeScanClicked(self):
        ## remove the selected scan from its map
        pass
        
    def clearDBSpot(self):
        ## remove all events referencing this spot
        ## remove stats for this spot
        pass
    
    def storeDBSpot(self):
        try:
            self.host.storeDBSpot()
            self.ui.storeDBSpotBtn.success("Stored.")
        except:
            self.ui.storeDBSpotBtn.failure("Error.")
            raise
        
        
    
    def clearDBScan(self):
        pass
    
    def storeDBScan(self):
        ## get events and stats for selected scan
        
        ## decide what tables need to look like
        
        ## check tables for ownership, structure
        
        ## write data
        pass
    



