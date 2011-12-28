# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
from flowchart import *
import os
from collections import OrderedDict
import debug
import FileLoader
import DatabaseGui
import FeedbackButton

class EventDetector(AnalysisModule):
    """
    The basic function of this analyzer is to detect repeated signals (action potentials, PSPs, calcium signals, etc)
    within a trace. 
    
    The core analysis is carried out by a flowchart that may be modified for a variety of different detection algorithms.
        * The flowchart input "dataIn" is a file handle
        * The output "events" is a numpy record array with one record per event. The columns are determined 
          by the flowchart itself
        * The output "regions" is a list of the regions that are defined within the flowchart. These
          are optional and may be used by downstream analysis modules.
          
    Data is saved to DB in almost exactly the same form that the "events" output produces, with some 
    extra fields:
        * SourceDir: integer referring to the rowid of the source directory OR
                     tuple (table, rowid) if the source directory is not a ProtocolSequence
        * SourceFile: the name of the file in which the event was detected. The name is relative to the SourceDir.                    
    
    """
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
        
    def output(self):
        return self.flowchart.output()
        
    def storeClicked(self):
        try:
            self.storeToDB()
            self.dbCtrl.storeBtn.success("Stored (%s rec)" % len(data))
        except:
            self.dbCtrl.storeBtn.failure("Error.")
            raise
        
    def storeToDB(self, data=None, protoDir=None):
        p = debug.Profiler("EventDetector.storeToDB", disabled=True)
        
        if data is None:
            data = self.flowchart.output()['events']
        if protoDir is None:
            protoDir = self.currentFile.parent()
            
        dbui = self.getElement('Database')
        table = dbui.getTableName(self.dbIdentity)
        db = dbui.getDb()
        if db is None:
            raise Exception("No DB selected")
        #if len(data) == 0:
            #raise Exception("No data to store.")
            
            
        ## make sure parent dir(s) are registered in DB, get table names
        #pDir = self.currentFile.parent()
        pTable, pRow = db.addDir(protoDir)
        protoSeqDir = self.dataModel.getParent('ProtocolSequence')
        if protoSeqDir is not None:
            psTable, psRow = db.addDir(protoSeqDir)
            
        psTable = db.getDirTable('ProtocolSequence')
        
        p.mark("DB prep done")
        
        ## determine the set of fields we expect to find in the table
        fields = OrderedDict([
            ('ProtocolSequenceDir', 'int'),  ## events that are not part of a sequence will have no vaue here.
            ('ProtocolDir', 'int'),
            ('SourceFile', 'text'),
        ])
        fields.update(db.describeData(data))
        fields['SourceFile'] = 'text'   ## SourceFile is currently a FileHandle, but will be converted to str.
        p.mark("field list done")
        
        ## Make sure target table exists and has correct columns, links to input file
        links = [('ProtocolDir', 'Protocol'), ('ProtocolSequenceDir', 'ProtocolSequence')]
        db.checkTable(table, owner=self.dbIdentity, fields=fields, links=links, create=True)
        
        ## convert source file handles to strings relative to the parent dir
        names = [fh.name(relativeTo=parentDir) for fh in data['SourceFile']]
        #for i in xrange(len(data)):
            #source = data[i]['SourceFile']
            #name = source.name(relativeTo=parentDir)
            #names.append(name)
        p.mark("data prepared")
        
        ## delete all records from table for current input files
        for name in set(names):
            db.delete(table, "SourceDir=%d and SourceFile='%s'" % (pRow, name))
        p.mark("previous records deleted")
        
        ## assemble final list of records
        records = []
        for i in xrange(len(data)):
            ## add new records
            d2 = data[i]
            rec = {'SourceDir': pRow, 'SourceFile': names[i]}
            rec2 = dict(zip(d2.dtype.names, d2))
            rec2.update(rec)
            records.append(rec2)
        p.mark("record list assembled")
            
        ## insert all data to DB
        db.insert(table, records)
        p.mark("records inserted")
        p.finish()

        
        
    def readFromDb(self, sourceDir, sourceFile=None):
        """Read events from DB that originate in sourceDir. 
        If sourceFile is specified, only return events that came from that file. 
        """
        
        dbui = self.getElement('Database')
        table = dbui.getTableName(self.dbIdentity)
        db = dbui.getDb()
        if db is None:
            raise Exception("No DB selected")
        
        #identity = self.dbIdentity+'.events'
        #table = dbui.getTableName(identity)
        #if not db.hasTable(table):
            #return None, None
            
        pRow = db.getDirRowID(sourceDir)
        if pRow is None:
            return None, None
        
        if sourceFile is not None:
            events = db.select(table, '*', "where SourceDir=%d and SourceFile='%s'" % (pRow, sourceFile.name(relativeTo=sourceDir)), toArray=True)
        else:
            events = db.select(table, '*', "where SourceDir=%d" % pRow, toArray=True)
        
        if events is None:
            ## need to make an empty array with the correct field names
            schema = db.tableSchema(table)
            ## NOTE: dtype MUST be specified as {names: formats: } since the names are unicode objects
            ##  [(name, format), ..] does NOT work.
            events = np.empty(0, dtype={'names': [k for k in schema], 'formats': [object]*len(schema)})
            
        else:   ## convert file strings to handles
            if sourceFile is None:
                for ev in events:  
                    #ev['SourceDir'] = parentDir
                    ev['SourceFile'] = sourceDir[ev['SourceFile']]
            else:
                for ev in events: 
                    #ev['SourceDir'] = parentDir
                    ev['SourceFile'] = sourceFile
        
        return events
        
                
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

