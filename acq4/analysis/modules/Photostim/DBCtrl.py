# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
from collections import OrderedDict
from .Map import Map
import acq4.util.DatabaseGui as DatabaseGui
from . import MapCtrlTemplate
from acq4.Manager import logMsg, logExc
import acq4.pyqtgraph as pg
import os

class DBCtrl(Qt.QWidget):
    """GUI for reading and writing to the database."""
    def __init__(self, host, identity):
        Qt.QWidget.__init__(self)
        self.host = host   ## host is the parent Photostim object
        self.dbIdentity = identity
        
        ## DB tables we will be using  {owner: defaultTableName}
        tables = OrderedDict([
            (self.dbIdentity+'.maps', 'Photostim_maps'),
            (self.dbIdentity+'.sites', 'Photostim_sites'),
            (self.dbIdentity+'.events', 'Photostim_events')
        ])
        self.maps = []
        self.layout = Qt.QVBoxLayout()
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
        self.mapWidget = Qt.QWidget()
        self.ui.setupUi(self.mapWidget)
        self.layout.addWidget(self.mapWidget)
        self.ui.scanTree.setAcceptDrops(False)
        self.ui.scanTree.setDragEnabled(False)
        
        
        labels = list(Map.mapFields.keys())[2:]
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
        item = ScanTreeItem(scan)
        self.ui.scanTree.addTopLevelItem(item)

    def scanTreeItemChanged(self, item, col):
        item.changed(col)
        
        
        
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
        #if cell is not None:
            #pt, rid = db.addDir(cell)
            #rec['cell'] = rid
        if rec['cell'] is None:
            return
        cell = rec['cell']
        
        #fields = db.describeData(rec)
        #fields['cell'] = 'int'
        db.checkTable(table, ident, Map.mapFields, create=True)
        
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
        
        db.delete(table, where={'rowid':rowID})
        
        self.host.unregisterMap(map)
        

    def listMaps(self, cells):
        """List all maps associated with the file handle for each cell in a list"""
        self.ui.mapTable.clear()
        self.maps = []
        
        for cell in cells:
            
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
            
            #row = db.getDirRowID(cell)
            #if row is None:
                #return
                
            maps = db.select(table, ['rowid','*'], where={'cell': cell})
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
            scans = self.selectedScans()
            for scan in scans:
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
        #raise Exception("Clearing spot data from a db is not yet implemented.")
        
        ### This clearly needs to change because it only works with the default tables -- but I wasn't sure how to get the right table names
        dbui = self.host.getElement('Database')
        db = dbui.getDb()        
        spot = self.host.selectedSpot
        dh = spot.data().name(relativeTo=db.baseDir())  
        protocolID = db('Select rowid, Dir from DirTable_Protocol where Dir="%s"' %dh)
        if len(protocolID) > 0:
            protocolID = protocolID[0]['rowid']
        else:
            return
        db('Delete from Photostim_events where ProtocolDir=%i' %protocolID)
        db('Delete from Photostim_sites where ProtocolDir=%i' %protocolID)
        #db('Delete from DirTable_Protocol where Dir="%s"' %dh)## don't delete the protocol, because other things like atlas tables reference the protocol, only delete from tables we own
        print("Removed data for %s" %dh)
        
        
    
    def storeDBSpot(self):
        try:
            self.host.storeDBSpot()
            self.ui.storeDBSpotBtn.success("Stored.")
        except:
            self.ui.storeDBSpotBtn.failure("Error.")
            raise
        
    def selectedMap(self):
        item = self.ui.mapTable.currentItem()
        if item is None:
            raise Exception("No map selected.")
        if not hasattr(item, 'map'):
            item = item.parent()
        return item.map
        
    def selectedScans(self):
        items = self.ui.scanTree.selectedItems()
        #item = self.ui.scanTree.currentItem()
        return [item.scan for item in items]
        
    
    def clearDBScan(self):
        try:
            scans = self.selectedScans()
            if len(scans) == 0:
                raise Exception("No scans selected.")
            for scan in scans:
                scan.clearFromDB()
                #self.host.clearDBScan(scan)
            self.ui.clearDBScanBtn.success("Cleared.")
        except:
            self.ui.clearDBScanBtn.failure("Error.")
            raise
    
    def storeDBScan(self):
        try:
            scans = self.selectedScans()
            if len(scans) == 0:
                raise Exception("No scans selected.")
            with pg.ProgressDialog('Storing scan data to DB..', maximum=len(scans)) as dlg:
                for scan in scans:
                    scan.storeToDB()
                    #self.host.storeDBScan(scan)
                    dlg += 1
                    if dlg.wasCanceled():
                        raise Exception('Store canceled by user')
            self.ui.scanTree.clearSelection()  ## We do this because it is too easy to forget to select the correct set of data before clicking store.
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

            

            
            
            
            
            
            
class ScanTreeItem(pg.TreeWidgetItem):
    def __init__(self, scan):
        pg.TreeWidgetItem.__init__(self, [scan.name(), '', '', ''])
        scan.scanTreeItem = self
        self.scan = scan
        self.setChecked(1, True)
        self.eventWidget = SaveLockWidget()
        self.statWidget = SaveLockWidget()
        self.setWidget(2, self.eventWidget)
        self.setWidget(3, self.statWidget)
        self.scanLockChanged(scan)
        self.scanStorageChanged(scan)
        
        self.eventWidget.sigLockClicked.connect(self.eventLockClicked)
        self.statWidget.sigLockClicked.connect(self.statLockClicked)
        scan.sigLockStateChanged.connect(self.scanLockChanged)
        scan.sigStorageStateChanged.connect(self.scanStorageChanged)
        scan.sigItemVisibilityChanged.connect(self.scanItemVisibilityChanged)
        
    def changed(self, col):
        ## when scan items are checked/unchecked, show/hide the canvasItem
        checked = self.checkState(col) == Qt.Qt.Checked
        if col == 1:
            self.scan.canvasItem().setVisible(checked)
            
    def scanLockChanged(self, scan):
        ## scan has been locked/unlocked (or newly loaded), update the indicator in the scanTree
        item = scan.scanTreeItem
        ev, st = scan.getLockState()
        self.eventWidget.setLocked(ev)
        self.statWidget.setLocked(st)

    def eventLockClicked(self):
        ev, st = self.scan.getLockState()
        self.scan.lockEvents(not ev)
        
    def statLockClicked(self):
        ev, st = self.scan.getLockState()
        self.scan.lockStats(not st)
        
    def scanStorageChanged(self, scan):
        ev, st = self.scan.getStorageState()
        #print "set saved:", ev, st
        self.eventWidget.setSaved(ev)
        self.statWidget.setSaved(st)
        
    def scanItemVisibilityChanged(self, scan):
        cItem = scan.canvasItem()
        checked = self.checkState(1) == Qt.Qt.Checked
        vis = cItem.isVisible()
        if vis == checked:
            return
        self.setCheckState(1, Qt.Qt.Checked if vis else Qt.Qt.Unchecked)
            

class SaveLockWidget(Qt.QWidget):
    sigLockClicked = Qt.Signal(object)  # self, lock
    
    def __init__(self):
        Qt.QWidget.__init__(self)
        self.layout = Qt.QHBoxLayout()
        self.setLayout(self.layout)
        self.saveLabel = Qt.QLabel()
        self.saveLabel.setScaledContents(True)
        self.lockBtn = Qt.QPushButton()
        self.lockBtn.setFixedWidth(20)
        self.lockBtn.setFixedHeight(20)
        self.saveLabel.setFixedWidth(20)
        self.saveLabel.setFixedHeight(20)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.addWidget(self.lockBtn)
        self.layout.addWidget(self.saveLabel)
        self.setFixedWidth(40)
        
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'icons'))
        images = [os.path.join(path, x) for x in ['locked.png', 'unlocked.png', 'saved.png', 'unsaved.png']]
        self.images = [Qt.QPixmap(img) for img in images]
        self.icons = [Qt.QIcon(img) for img in self.images[:2]]
        if any([img.width() == 0 for img in self.images]):
            raise Exception("Could not load icons:", images)
        self.setSaved(False)
        self.setLocked(False)
        self.lockBtn.clicked.connect(self.lockClicked)
        
    def lockClicked(self):
        self.sigLockClicked.emit(self)
        
    def setLocked(self, locked):
        self.lockBtn.setIcon(self.icons[0 if locked else 1])
       
    def setSaved(self, saved):
        self.saveLabel.setPixmap(self.images[2 if saved else 3])
        
        