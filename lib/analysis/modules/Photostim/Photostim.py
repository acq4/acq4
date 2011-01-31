# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
import lib.analysis.modules.EventDetector as EventDetector
import MapCtrlTemplate
from flowchart import *
import os
from advancedTypes import OrderedDict
import debug
#import FileLoader

class Photostim(AnalysisModule):
    def __init__(self, host):
        self.dbIdentity = "Photostim"  ## how we identify to the database; this determines which tables we own

        ## setup analysis flowchart
        flowchartDir = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "analysis_fc")
        self.flowchart = Flowchart(filePath=flowchartDir)
        self.flowchart.addInput('events')
        self.flowchart.addInput('regions')
        self.flowchart.addOutput('dataOut')
        self.analysisCtrl = self.flowchart.widget()
        
        ## setup map DB ctrl
        self.mapCtrl = MapCtrl(self)
        self.scanItems = {}
        
        ## create event detector
        fcDir = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "detector_fc")
        self.detector = EventDetector.EventDetector(host, flowchartDir=fcDir)
        
        ## override some of its elements
        self.detector.setElement('File Loader', self)
        self.detector.setElement('Database', self)
        
        ## DB tables we will be using  {owner: defaultTableName}
        tables = {
            self.dbIdentity+'.maps': 'Photostim_maps',
            self.dbIdentity+'.sites': 'Photostim_sites',
            self.dbIdentity+'.events': 'Photostim_events'
        }
            
        ## Create element list, importing some gui elements from event detector
        elems = self.detector.listElements()
        self._elements_ = OrderedDict([
            ('Database', {'type': 'database', 'tables': tables, 'host': self}),
            ('Canvas', {'type': 'canvas', 'pos': ('right',), 'size': (400,400)}),
            ('Maps', {'type': 'ctrl', 'pos': ('bottom', 'Database'), 'size': (200,200), 'object': self.mapCtrl}),
            ('Detection Opts', elems['Detection Opts'].setParams(pos=('bottom', 'Maps'), size= (200,500))),
            ('File Loader', {'type': 'fileInput', 'size': (200, 300), 'pos': ('above', 'Database'), 'host': self}),
            ('Data Plot', elems['Data Plot'].setParams(pos=('bottom', 'Canvas'), size=(800,200))),
            ('Filter Plot', elems['Filter Plot'].setParams(pos=('bottom', 'Data Plot'), size=(800,200))),
            ('Output Table', elems['Output Table'].setParams(pos=('below', 'Filter Plot'), size=(800,200))),
            ('Stats', {'type': 'dataTree', 'size': (800,200), 'pos': ('below', 'Output Table')}),
            ('Map Opts', {'type': 'ctrl', 'object': self.analysisCtrl, 'pos': ('left', 'Canvas'), 'size': (200,400)}),
        ])

        AnalysisModule.__init__(self, host)
        self.detector.flowchart.sigOutputChanged.connect(self.detectorOutputChanged)

    
        
    def loadFileRequested(self, fh):
        canvas = self.getElement('Canvas')
        try:
            if fh.isFile():
                canvas.addFile(fh)
            else:
                scan = canvas.addFile(fh)
                self.scanItems[fh] = scan
                scan.item.sigPointClicked.connect(self.scanPointClicked)
            return True
        except:
            debug.printExc("Error loading file %s" % fh.name())
            return False
    
    def storeToDB(self):
        pass


    def scanPointClicked(self, point):
        #print "click!", point.data
        self.detector.loadFileRequested(point.data)
        
    def detectorOutputChanged(self):
        output = self.detector.flowchart.output()
        #table = self.getElement('Stats')
        #stats = self.detector.flowchart.output()['stats']
        #print stats
        #table.setData(stats)
        self.flowchart.setInput(**output)
        
        
        
class MapCtrl(QtGui.QWidget):
    """Interface for reading and writing the maps table.
    A map consists of one or more (probably overlapping) scans and associated meta-data."""
    def __init__(self, host):
        QtGui.QWidget.__init__(self)
        self.host = host
        
        self.fields = {
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
        
        self.ui = MapCtrlTemplate.Ui_Form()
        self.ui.setupUi(self)
        self.ui.newMapBtn.clicked.connect(self.newMapClicked)
        self.ui.loadMapBtn.clicked.connect(self.loadMapClicked)
        self.ui.delMapBtn.clicked.connect(self.delMapClicked)
        self.ui.addScanBtn.clicked.connect(self.addScanClicked)
        self.ui.removeScanBtn.clicked.connect(self.removeScanClicked)

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
        
        