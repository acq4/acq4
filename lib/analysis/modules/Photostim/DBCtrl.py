# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from collections import OrderedDict
from Map import Map
import DatabaseGui
import MapCtrlTemplate
from lib.Manager import logMsg, logExc

class DBCtrl(QtGui.QWidget):
    """GUI for reading and writing to the database."""
    def __init__(self, host, identity):
        QtGui.QWidget.__init__(self)
        self.host = host   ## host is the parent Photostim object
        self.dbIdentity = identity
        
        ## DB tables we will be using  {owner: defaultTableName}
        tables = OrderedDict([
            (self.dbIdentity+'.maps', 'Photostim_maps'),
            (self.dbIdentity+'.sites', 'Photostim_sites'),
            (self.dbIdentity+'.events', 'Photostim_events')
        ])
        self.maps = []
        self.layout = QtGui.QVBoxLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)
        
        self.dbgui = DatabaseGui.DatabaseGui(dm=host.dataManager(), tables=tables)
        self.layout.addWidget(self.dbgui)
        for name in ['getTableName', 'getDb']:
            setattr(self, name, getattr(self.dbgui, name))
        #self.scanTree = TreeWidget.TreeWidget()
        #self.layout.addWidget(self.scanTree)
        self.ui = MapCtrlTemplate.Ui_Form()
        self.mapWidget = QtGui.QWidget()
        self.ui.setupUi(self.mapWidget)
        self.layout.addWidget(self.mapWidget)
        
        
        labels = Map.mapFields.keys()[2:]
        self.ui.mapTable.setHeaderLabels(labels)
        self.ui.mapTable.itemChanged.connect(self.mapItemChanged)
        
        self.ui.newMapBtn.clicked.connect(self.newMapClicked)
        self.ui.loadMapBtn.clicked.connect(self.loadMapClicked)
        self.ui.delMapBtn.clicked.connect(self.delMapClicked)
        self.ui.addScanBtn.clicked.connect(self.addScanClicked)
        self.ui.removeScanBtn.clicked.connect(self.removeScanClicked)
        self.ui.clearDBSpotBtn.clicked.connect(self.clearDBSpot)
        self.ui.storeDBSpotBtn.clicked.connect(self.storeDBSpot)
        self.ui.clearDBScanBtn.clicked.connect(self.clearDBScan)
        self.ui.storeDBScanBtn.clicked.connect(self.storeDBScan)
        self.ui.rewriteSpotPosBtn.clicked.connect(self.rewriteSpotPosClicked)
        self.ui.scanTree.itemChanged.connect(self.scanTreeItemChanged)

    def scanLoaded(self, scan):
        ## Scan has been loaded, add a new item into the scanTree
        item = QtGui.QTreeWidgetItem([scan.name(), '', ''])
        self.ui.scanTree.addTopLevelItem(item)
        scan.scanTreeItem = item
        item.scan = scan
        item.setCheckState(2, QtCore.Qt.Checked)
        scan.sigLockChanged.connect(self.scanLockChanged)
        self.scanLockChanged(scan)
        scan.sigItemVisibilityChanged.connect(self.scanItemVisibilityChanged)
        
    def scanTreeItemChanged(self, item, col):
        ## when scan items are checked/unchecked, show/hide the canvasItem
        if col == 2:
            vis = item.checkState(col) == QtCore.Qt.Checked
            scan = item.scan
            ci = scan.canvasItem
            ci.setVisible(vis)
        
    def scanLockChanged(self, scan):
        ## scan has been locked/unlocked (or newly loaded), update the indicator in the scanTree
        item = scan.scanTreeItem
        if scan.locked():
            item.setText(1, 'Yes')
        else:
            item.setText(1, 'No')
            
    def scanItemVisibilityChanged(self, scan):
        treeItem = scan.scanTreeItem
        cItem = scan.canvasItem
        checked = treeItem.checkState(2) == QtCore.Qt.Checked
        vis = cItem.isVisible()
        if vis == checked:
            return
        if vis:
            treeItem.setCheckState(2, QtCore.Qt.Checked)
        else:
            treeItem.setCheckState(2, QtCore.Qt.Unchecked)
            

    def newMap(self, rec=None):
        m = Map(self.host, rec)
        self.maps.append(m)
        item = m.item
        self.ui.mapTable.addTopLevelItem(item)
        self.ui.mapTable.setCurrentItem(item)

    def mapItemChanged(self, item, col):
        self.writeMapRecord(item.map)
        

    def writeMapRecord(self, map):
        dbui = self.host.getElement('Database')
        db = dbui.getDb()
        if db is None:
            return
            
        ident = self.dbIdentity+'.maps'
        table = dbui.getTableName(ident)
        
        rec = map.getRecord()
        cell = rec['cell']
        if cell is not None:
            pt, rid = db.addDir(cell)
            rec['cell'] = rid
        if rec['cell'] is None:
            return
        
        #fields = db.describeData(rec)
        #fields['cell'] = 'int'
        db.checkTable(table, ident, Map.mapFields, [('cell', 'Cell')], create=True)
        
        if map.rowID is None:
            db.insert(table, rec)
            map.rowID = db.lastInsertRow()
        else:
            rec['rowid'] = map.rowID
            db.insert(table, rec, replaceOnConflict=True)

    def deleteMap(self, map):
        item = map.item
        self.ui.mapTable.takeTopLevelItem(self.ui.mapTable.indexOfTopLevelItem(item))
        rowID = map.rowID
        if rowID is None:
            return
        
        dbui = self.host.getElement('Database')
        db = dbui.getDb()
        if db is None:
            raise Exception("No DB Loaded.")
            
        ident = self.dbIdentity+'.maps'
        table = dbui.getTableName(ident)
        if db.tableOwner(table) != ident:
            raise Exception("Table %s not owned by %s" % (table, ident))
        
        db.delete(table, 'rowid=%d'%rowID)
        
        self.host.unregisterMap(map)
        

    def listMaps(self, cell):
        """List all maps associated with the file handle for cell"""
        dbui = self.host.getElement('Database')
        db = dbui.getDb()
        if db is None:
            logMsg("No database loaded in Data Manager.", msgType='error')
            
        ident = self.dbIdentity+'.maps'
        table = dbui.getTableName(ident)
        if not db.hasTable(table):
            return
        if db.tableOwner(table) != ident:
            raise Exception("Table %s not owned by %s" % (table, ident))
        
        row = db.getDirRowID(cell)
        if row is None:
            return
            
        maps = db.select(table, ['rowid','*'], 'where cell=%d'%row)
        #print maps
        for rec in maps:
            scans = []
            for rowid in rec['scans']:
                if isinstance(rowid, tuple):
                    fh = db.getDir(rowid[0], rowid[1])  ## single-spot maps specify the Protocol table instead
                else:
                    fh = db.getDir('ProtocolSequence', rowid)    ## NOTE: single-spot maps use a different table!
                scans.append((fh, rowid))
            rec['scans'] = scans
            self.newMap(rec)


    def loadMap(self, map):
        ## turn scan stubs into real scans
        map.loadStubs()
        self.host.registerMap(map)

    def newMapClicked(self):
        ## Create a new map in the database
        try:
            self.newMap()
            self.ui.newMapBtn.success("OK.")
        except:
            self.ui.newMapBtn.failure("Error.")
            raise
        
        pass
    
    def loadMapClicked(self):
        try:
            map = self.selectedMap()
            self.loadMap(map)
            self.ui.loadMapBtn.success("OK.")
        except:
            self.ui.loadMapBtn.failure("Error.")
            raise
    
    def delMapClicked(self):
        try:
            map = self.selectedMap()
            self.deleteMap(map)
            self.ui.addScanBtn.success("Deleted.")
        except:
            self.ui.addScanBtn.failure("Error.")
            raise
        
    #def getSelectedScanFromScanTree(self):
        #"""Needs to return a list of scans."""
        #if self.scanTree.currentItem().childCount() == 0:
            #scan = self.scanTree.currentItem().scan
            #return [scan]
        #else:
            #scans = []
            #for i in range(self.scanTree.currentItem().childCount()):
                #scan = self.scanTree.currentItem().child(i).scan
                #scans.append(scan)
            #return scans
        
    def addScanClicked(self):
        try:
            #scan = self.getSelectedScanFromScanTree()
            scan = self.selectedScan()
            map = self.selectedMap()
            map.addScans([scan])
            self.writeMapRecord(map)
            map.rebuildPlot()
            self.ui.addScanBtn.success("OK.")
        except:
            self.ui.addScanBtn.failure("Error.")
            raise
    
    def removeScanClicked(self):
        try:
            item = self.ui.mapTable.currentItem()
            scan = item.scan
            map = item.parent().map
            map.removeScan(scan)
            self.writeMapRecord(map)
            map.rebuildPlot()
            self.ui.removeScanBtn.success("OK.")
        except:
            self.ui.removeScanBtn.failure("Error.")
            raise
        
    def clearDBSpot(self):
        ## remove all events referencing this spot
        ## remove stats for this spot
        raise Exception("Clearing spot data from a db is not yet implemented.")
    
    
    def storeDBSpot(self):
        try:
            self.host.storeDBSpot()
            self.ui.storeDBSpotBtn.success("Stored.")
        except:
            self.ui.storeDBSpotBtn.failure("Error.")
            raise
        
    def selectedMap(self):
        item = self.ui.mapTable.currentItem()
        if not hasattr(item, 'map'):
            item = item.parent()
        return item.map
        
    def selectedScan(self):
        item = self.ui.scanTree.currentItem()
        #if not hasattr(item, 'scan'):
            #return None
        return item.scan
        
    
    def clearDBScan(self):
        try:
            scan = self.selectedScan()
            if scan is None:
                raise Exception("No scan selected.")
            self.host.clearDBScan(scan)
            self.ui.clearDBScanBtn.success("Cleared.")
        except:
            self.ui.clearDBScanBtn.failure("Error.")
            raise
    
    def storeDBScan(self):
        try:
            scan = self.selectedScan()
            if scan is None:
                raise Exception("No scan selected.")
            self.host.storeDBScan(scan)
            self.ui.storeDBScanBtn.success("Stored.")
        except:
            self.ui.storeDBScanBtn.failure("Error.")
            raise
    
    def rewriteSpotPosClicked(self):
        ## Recompute spot locations for selected scan and write to DB
        try:
            scan = self.selectedScan()
            if scan is None:
                raise Exception("No scan selected.")
            self.host.rewriteSpotPositions(scan)
            self.ui.rewriteSpotPosBtn.success("Stored.")
        except:
            self.ui.rewriteSpotPosBtn.failure("Error.")
            raise
