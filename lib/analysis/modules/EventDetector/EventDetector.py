# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
from flowchart import *
import os
from advancedTypes import OrderedDict
import debug
import FileLoader
import DatabaseGui
import FeedbackButton

class EventDetector(AnalysisModule):
    def __init__(self, host, flowchartDir=None, dbIdentity="EventDetector"):
        AnalysisModule.__init__(self, host)
        
        if flowchartDir is None:
            flowchartDir = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "flowcharts")
        self.flowchart = Flowchart(filePath=flowchartDir)
        self.dbIdentity = dbIdentity  ## how we identify to the database; this determines which tables we own
        #self.loader = FileLoader.FileLoader(host.dataManager())
        #self.setCentralWidget(self.flowchart.widget())
        #self.ui.chartDock1.setWidget(self.flowchart.widget())
        self.flowchart.addInput("dataIn")
        self.flowchart.addOutput('events')
        self.flowchart.addOutput('regions', multi=True)        
        self.flowchart.sigChartLoaded.connect(self.connectPlots)

        self.dbCtrl = DBCtrl(self, identity=self.dbIdentity)
        self.dbCtrl.storeBtn.clicked.connect(self.storeClicked)

        #self.ctrl = QtGui.QLabel('LABEL')
        self.ctrl = self.flowchart.widget()
        self._elements_ = OrderedDict([
            ('File Loader', {'type': 'fileInput', 'size': (200, 300), 'host': self}),
            ('Database', {'type': 'ctrl', 'object': self.dbCtrl, 'size': (200,300), 'pos': ('bottom', 'File Loader')}),
            ('Data Plot', {'type': 'plot', 'pos': ('right',), 'size': (800, 300)}),
            ('Detection Opts', {'type': 'ctrl', 'object': self.ctrl, 'pos': ('bottom', 'Database'), 'size': (200, 500)}),
            ('Filter Plot', {'type': 'plot', 'pos': ('bottom', 'Data Plot'), 'size': (800, 300)}),
            ('Output Table', {'type': 'table', 'pos': ('bottom', 'Filter Plot'), 'optional': True, 'size': (800,200)}),
        ])
        
        self.initializeElements()
        
        try:
            ## load default chart
            self.flowchart.loadFile(os.path.join(flowchartDir, 'default.fc'))
        except:
            debug.printExc('Error loading default flowchart:')
        
        self.flowchart.sigOutputChanged.connect(self.outputChanged)
        
    def elementChanged(self, element, old, new):
        name = element.name()
        
        ## connect plots to flowchart, link X axes
        if name == 'Data Plot':
            self.flowchart.nodes()['Plot_000'].setPlot(new)
            p2 = self.getElement('Filter Plot')
            if p2 is not None:
                new.setXLink(p2)
        elif name == 'Filter Plot':
            self.flowchart.nodes()['Plot_001'].setPlot(new)
            p2 = self.getElement('Data Plot')
            if p2 is not None:
                p2.setXLink(new)

    def connectPlots(self):
        dp = self.getElement('Data Plot', create=False)
        fp = self.getElement('Filter Plot', create=False)
        if dp is not None:
            self.flowchart.nodes()['Plot_000'].setPlot(dp)
        if fp is not None:
            self.flowchart.nodes()['Plot_001'].setPlot(fp)


    def loadFileRequested(self, fh):
        """Called by file loader when a file load is requested."""
        self.flowchart.setInput(dataIn=fh)
        self.currentFile = fh
        return True

    def process(self, fh):
        return self.flowchart.process(dataIn=fh)

    def outputChanged(self):
        table = self.getElement('Output Table')
        table.setData(self.flowchart.output()['events'])
        
    def storeClicked(self):
        try:
            self.storeToDB()
            self.dbCtrl.storeBtn.success("Stored (%s rec)" % len(data))
        except:
            self.dbCtrl.storeBtn.failure("Error.")
            raise
        
    def storeToDB(self, data=None, parentDir=None):
        if data is None:
            data = self.flowchart.output()['events']
        if parentDir is None:
            parentDir = self.currentFile.parent()
            
        dbui = self.getElement('Database')
        table = dbui.getTableName(self.dbIdentity)
        db = dbui.getDb()
        if db is None:
            raise Exception("No DB selected")
        #if len(data) == 0:
            #raise Exception("No data to store.")
            
            
        ## make sure parent dir is registered in DB, get its table name
        #pDir = self.currentFile.parent()
        pTable, pRow = db.addDir(parentDir)
            
        ## determine the set of fields we expect to find in the table
        fields = OrderedDict([
            ('SourceDir', 'int'),
            ('SourceFile', 'text'),
        ])
        fields.update(db.describeData(data))
        fields['SourceFile'] = 'text' 
        
        ## Make sure target table exists and has correct columns, links to input file
        db.checkTable(table, owner=self.dbIdentity, fields=fields, links=[('SourceDir', pTable)], create=True)
        
        names = []
        for i in xrange(len(data)):
            ## delete all records from table for current input file
            source = data[i]['SourceFile']
            name = source.name(relativeTo=parentDir)
            names.append(name)
            db.delete(table, "SourceDir=%d and SourceFile='%s'" % (pRow, name))

        for i in xrange(len(data)):
            ## add new records
            d2 = data[i]
            rec = {'SourceDir': pRow, 'SourceFile': names[i]}
            rec2 = dict(zip(d2.dtype.names, d2))
            rec2.update(rec)
            db.insert(table, rec2)
                
    #def storeClicked(self):
        #dbui = self.getElement('Database')
        #try:
            #self.storeToDB()
            #dbui.storeBtnFeedback(True, "Stored!")
        #except:
            #dbui.storeBtnFeedback(False, "Error!", "See console for error message..")
            #raise
        
class DBCtrl(QtGui.QWidget):
    def __init__(self, host, identity):
        QtGui.QWidget.__init__(self)
        self.host = host
        
        self.layout = QtGui.QVBoxLayout()
        self.setLayout(self.layout)
        self.dbgui = DatabaseGui.DatabaseGui(dm=host.dataManager(), tables={identity: 'EventDetector_events'})
        self.storeBtn = FeedbackButton.FeedbackButton("Store to DB")
        #self.storeBtn.clicked.connect(self.storeClicked)
        self.layout.addWidget(self.dbgui)
        self.layout.addWidget(self.storeBtn)
        for name in ['getTableName', 'getDb']:
            setattr(self, name, getattr(self.dbgui, name))
            
    #def storeClicked(self):
        #if self.host is None:
            #self.sigStoreToDB.emit()
        #else:
            #try:
                #self.host.storeToDB()
            #except:
                #self.storeBtn.feedback(False, "Error!", "See console for error message..")
                #raise

