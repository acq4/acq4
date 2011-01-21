# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
from flowchart import *
import os
from advancedTypes import OrderedDict
import debug
import FileLoader

class EventDetector(AnalysisModule):
    def __init__(self, host):
        path = os.path.join(os.path.abspath(os.path.split(__file__)[0]), "flowcharts")
        self.flowchart = Flowchart(filePath=path)
        self.dbIdentity = "EventDetector"  ## how we identify to the database; this determines which tables we own
        #self.loader = FileLoader.FileLoader(host.dataManager())
        #self.setCentralWidget(self.flowchart.widget())
        #self.ui.chartDock1.setWidget(self.flowchart.widget())
        self.flowchart.addInput("dataIn")
        #self.ctrl = QtGui.QLabel('LABEL')
        self.ctrl = self.flowchart.widget()
        self._elements_ = OrderedDict([
            ('File Loader', {'type': 'fileInput', 'size': (200, 300)}),
            ('Data Plot', {'type': 'plot', 'pos': ('right', 'File Loader'), 'size': (800, 400)}),
            ('Detection Opts', {'type': 'ctrl', 'object': self.ctrl, 'pos': ('bottom', 'File Loader'), 'size': (200, 500)}),
            ('Database', {'type': 'database', 'pos': ('below', 'File Loader'), 'tables': {self.dbIdentity: 'EventDetector_events'}}),
            ('Filter Plot', {'type': 'plot', 'pos': ('bottom', 'Data Plot'), 'size': (800, 400)}),
            ('Output Table', {'type': 'table', 'pos': ('bottom', 'Filter Plot'), 'optional': True}),
        ])
        
        #print "EventDetector init:", id(EventDetector), id(AnalysisModule)
        #print "  bases:", map(id, EventDetector.__bases__)
        #print "  init fn:", AnalysisModule.__init__, id(AnalysisModule.__init__)
        AnalysisModule.__init__(self, host)
        
        try:
            ## load default chart
            self.flowchart.loadFile(os.path.join(path, 'default.fc'))
            
            ## assign plots to their correct spots in the chart
            p1 = self.getElement('Data Plot')
            p2 = self.getElement('Filter Plot')
            self.flowchart.nodes()['Plot_000'].setPlot(p1)
            self.flowchart.nodes()['Plot_001'].setPlot(p2)
            
            ## link plot X axes
            p1.setXLink(p2)
        except:
            debug.printExc('Error loading default flowchart:')
        
        self.loader = self.getElement('File Loader')
        self.table = self.getElement('Output Table')
        self.dbui = self.getElement('Database')
        self.flowchart.sigOutputChanged.connect(self.outputChanged)
        QtCore.QObject.connect(self.loader, QtCore.SIGNAL('fileLoaded'), self.fileLoaded)
        self.dbui.sigStoreToDB.connect(self.storeClicked)
        
    def fileLoaded(self, fh):
        self.flowchart.setInput(dataIn=fh)
        self.currentFile = fh
        
    def outputChanged(self):
        self.table.setData(self.flowchart.output()['events'])
        
    def storeToDB(self):
        data = self.flowchart.output()['events']
        table = self.dbui.getTableName(self.dbIdentity)
        db = self.dbui.getDb()
        if db is None:
            raise Exception("No DB selected")
        if len(data) == 0:
            raise Exception("No data to store.")
            
            
        ## make sure parent dir is registered in DB, get its table name
        pDir = self.currentFile.parent()
        pTable, pRow = db.addDir(pDir)
            
        ## determine the set of fields we expect to find in the table
        fields = OrderedDict([
            ('SourceDir', 'int'),
            ('SourceFile', 'text'),
        ])
        for i in xrange(len(data.dtype)):
            name = data.dtype.names[i]
            typ = data.dtype[i].kind
            if typ == 'i':
                typ = 'int'
            elif typ == 'f':
                typ = 'real'
            fields[name] = typ
            
        
        ## Make sure target table exists and has correct columns, links to input file
        if not db.hasTable(table):
            ## create table
            db.createTable(table, fields)
            db.linkTables(table, 'SourceDir', pTable)
            db.takeOwnership(table, self.dbIdentity)
        else:
            ## check table for ownership, columns
            if db.tableOwner(table) != self.dbIdentity:
                raise Exception("Table %s is not owned by this module." % table)
            
            ts = db.tableSchema(table)
            for f in fields:
                if f not in ts:
                    raise Exception("Table has different data structure: Missing field %s" % f)
                elif ts[f] != fields[f]:
                    raise Exception("Table has different data structure: Field '%s' type is %s, should be %s" % (f, ts[f], fields[f]))

        ## delete all records from table for current input file
        db.delete(table, "SourceDir=%d and SourceFile='%s'" % (pRow, self.currentFile.shortName()))
        
        ## add new records
        rec = {'SourceDir': pRow, 'SourceFile': self.currentFile.shortName()}
        for i in xrange(len(data)):
            d2 = data[i]
            rec2 = dict(zip(d2.dtype.names, d2))
            rec2.update(rec)
            db.insert(table, rec2)
            
                
    def storeClicked(self):
        try:
            self.storeToDB()
            self.dbui.storeBtnFeedback(True, "Stored!")
        except:
            self.dbui.storeBtnFeedback(False, "Error!", "See console for error message..")
            raise
        