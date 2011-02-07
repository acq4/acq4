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
import pyqtgraph as pg
#import FileLoader

class Photostim(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        self.dbIdentity = "Photostim"  ## how we identify to the database; this determines which tables we own
        self.selectedSpot = None


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
        self.scans = {}
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
            ('Database', {'type': 'ctrl', 'object': self.dbCtrl, 'size': (200, 200)}),
            ('Canvas', {'type': 'canvas', 'pos': ('right',), 'size': (400,400), 'allowTransforms': False}),
            #('Maps', {'type': 'ctrl', 'pos': ('bottom', 'Database'), 'size': (200,200), 'object': self.mapDBCtrl}),
            ('Detection Opts', elems['Detection Opts'].setParams(pos=('bottom', 'Database'), size= (200,500))),
            ('File Loader', {'type': 'fileInput', 'size': (200, 200), 'pos': ('top', 'Database'), 'host': self}),
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
        self.detector.flowchart.sigStateChanged.connect(self.detectorStateChanged)
        self.flowchart.sigStateChanged.connect(self.analyzerStateChanged)
        self.recolorBtn.clicked.connect(self.recolor)
        
        
    def elementChanged(self, element, old, new):
        name = element.name()
        
        ## connect plots to flowchart, link X axes
        if name == 'File Loader':
            new.sigBaseChanged.connect(self.baseDirChanged)
            QtCore.QObject.connect(new.ui.dirTree, QtCore.SIGNAL('selectionChanged'), self.fileSelected)

    def fileSelected(self):
        fh = self.getElement('File Loader').ui.dirTree.selectedFile()
        print Scan.describe(fh)

    def baseDirChanged(self, dh):
        typ = dh.info()['dirType']
        if typ == 'Slice':
            cells = [dh[d] for d in dh.subDirs() if dh[d].info().get('dirType',None) == 'Cell']
        elif typ == 'Cell':
            cells = [dh]
        else:
            return
        for cell in cells:
            self.dbCtrl.listMaps(cell)

            
    def loadFileRequested(self, fh):
        canvas = self.getElement('Canvas')
        try:
            if fh.isFile():
                canvas.addFile(fh)
            else:
                self.loadScan(fh)
            return True
        except:
            debug.printExc("Error loading file %s" % fh.name())
            return False
    
    def loadScan(self, fh):
        if fh not in self.scans:
            canvas = self.getElement('Canvas')
            scan = canvas.addFile(fh)
            #self.scanItems[fh] = scan
            self.scans[fh] = Scan(self, fh, scan.item)
            scan.item.sigPointClicked.connect(self.scanPointClicked)
        return self.scans[fh]

    def registerMap(self, map):
        #if map in self.maps:
            #return
        canvas = self.getElement('Canvas')
        canvas.addItem(map.sPlotItem, name=map.name())
        self.maps.append(map)
        map.sPlotItem.sigPointClicked.connect(self.mapPointClicked)
        
    def unregisterMap(self, map):
        canvas = self.getElement('Canvas')
        canvas.removeItem(map.sPlotItem)
        self.maps.remove(map)
        map.sPlotItem.sigPointClicked.disconnect(self.mapPointClicked)
    

    def storeToDB(self):
        pass

    def getClampFile(self, dh):
        try:
            return dh['Clamp2.ma']
        except:
            return dh['Clamp1.ma']

    def scanPointClicked(self, point):
        print "click!", point.data
        plot = self.getElement("Data Plot")
        plot.clear()
        self.selectedSpot = point
            
        self.detector.loadFileRequested(self.getClampFile(point.data))
        
    def mapPointClicked(self, point):
        plot = self.getElement("Data Plot")
        plot.clear()
        eTable = self.getElement("Output Table")
        sTable = self.getElement("Stats")
        self.mapTicks = []
        
        num = len(point.data)
        statList = []
        evList = []
        for i in range(num):
            color = pg.intColor(i, num)
            scan, fh = point.data[i]
            
            ## plot all data, incl. events
            data = fh.read()['primary']
            plot.plot(data, pen=color, clear=False)
            
            ## show stats
            stats = scan.getStats(fh)
            statList.append(stats)
            events = scan.getEvents(fh)['events']
            evList.append(events)
        
            times = events['fitTime']
            ticks = pg.VTickGroup(times, [0.0, 0.15], pen=color, relative=True, view=plot)
            plot.addItem(ticks)
            self.mapTicks.append(ticks)
        
        sTable.setData(statList)
        eTable.setData(np.concatenate(evList))
        
    def detectorStateChanged(self):
        #print "STATE CHANGE"
        print "Detector state changed"
        for m in self.scans.itervalues():
            m.forgetEvents()
        
    def detectorOutputChanged(self):
        output = self.detector.flowchart.output()
        #table = self.getElement('Stats')
        #stats = self.detector.flowchart.output()['stats']
        #print stats
        #table.setData(stats)
        self.flowchart.setInput(**output)

    def analyzerStateChanged(self):
        print "Analyzer state changed."
        for m in self.scans.itervalues():
            m.forgetEvents()
        
    def analyzerOutputChanged(self):
        table = self.getElement('Stats')
        stats = self.processStats()  ## gets current stats
        table.setData(stats)
        if stats is None:
            return
        self.mapper.setArgList(stats.keys())
        
    #def getCurrentStats(self):
        #stats = self.flowchart.output()['dataOut']
        #spot = self.selectedSpot
        #pos = spot.scenePos()
        #stats['xPos'] = pos.x()
        #stats['yPos'] = pos.y()
        #return stats
        
        
    def recolor(self):
        for i in range(len(self.scans)):
            s = self.scans[self.scans.keys()[i]]
            s.recolor(i, len(self.scans))
        for m in self.maps:
            m.recolor(self)

    def getColor(self, stats):
        #print "STATS:", stats
        return self.mapper.getColor(stats)

    def processEvents(self, fh):
        print "Process Events:", fh
        return self.detector.process(fh)

    def processStats(self, data=None, spot=None):
        if data is None:
            stats = self.flowchart.output()['dataOut']
            spot = self.selectedSpot
        else:
            stats = self.flowchart.process(**data)['dataOut']
        pos = spot.scenePos()
        stats['xPos'] = pos.x()
        stats['yPos'] = pos.y()
        
        d = spot.data.parent()
        size = d.info().get('Scanner', {}).get('spotSize', 100e-6)
        stats['spotSize'] = size
        print "Process Stats:", spot.data
        
        return stats


    def storeDBSpot(self):
        """Stores data for selected spot immediately, using current flowchart outputs"""
        dbui = self.getElement('Database')
        #identity = self.dbIdentity+'.sites'
        #table = dbui.getTableName(identity)
        db = dbui.getDb()
        
        ## get events and stats for selected spot
        spot = self.selectedSpot
        if spot is None:
            raise Exception("No spot selected")
        fh = self.getClampFile(spot.data)
        print "Store spot:", fh
        parentDir = fh.parent()
        p2 = parentDir.parent()
        if db.dirTypeName(p2) == 'ProtocolSequence':
            parentDir = p2
            
        ## ask eventdetector to store events for us.
        #print parentDir
        self.detector.storeToDB(parentDir=parentDir)
        events = self.detector.output()

        ## store stats
        #stats = self.flowchart.output()['dataOut']
        stats = self.processStats()  ## gets current stats if no processing is requested
        
        self.storeStats(stats, fh, parentDir)
        
        
        ## update data in Map
        scan = self.scans[parentDir]
        scan.updateSpot(fh, events, stats)
        
    def selectedScan(self):
        loader = self.getElement('File Loader')
        dh = loader.selectedFile()
        scan = self.scans[dh]
        return scan

    def storeDBScan(self):
        """Store all data for a scan, using cached values if possible"""
        loader = self.getElement('File Loader')
        dh = loader.selectedFile()
        scan = self.scans[dh]
        print "Store scan:", dh.name()
        for s in scan.spots():
            fh = self.getClampFile(s.data)
            try:
                ev = scan.getEvents(fh)['events']
            except:
                print fh, scan.getEvents(fh)
                raise
            st = scan.getStats(fh)
            self.detector.storeToDB(ev, dh)
            self.storeStats(st, fh, dh)
        print "   scan %s is now locked" % dh.name()
        scan.locked = True

    def clearDBScan(self):
        dbui = self.getElement('Database')
        db = dbui.getDb()
        loader = self.getElement('File Loader')
        dh = loader.selectedFile()
        scan = self.scans[dh]
        pRow = db.getDirRowID(dh)
        
        identity = self.dbIdentity+'.sites'
        table = dbui.getTableName(identity)
        db.delete(table, "SourceDir=%d" % pRow)
        
        identity = self.dbIdentity+'.events'
        table = dbui.getTableName(identity)
        db.delete(table, "SourceDir=%d" % pRow)
            
        scan.locked = False


    def storeStats(self, data, fh, parentDir):
        print "Store stats:", fh
        dbui = self.getElement('Database')
        identity = self.dbIdentity+'.sites'
        table = dbui.getTableName(identity)
        db = dbui.getDb()

        if db is None:
            raise Exception("No DB selected")

        pTable, pRow = db.addDir(parentDir)
        
        name = fh.name(relativeTo=parentDir)
        data = data.copy()  ## don't overwrite anything we shouldn't.. 
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

    def loadSpotFromDB(self, dh):
        dbui = self.getElement('Database')
        db = dbui.getDb()

        if db is None:
            raise Exception("No DB selected")
        
        fh = self.getClampFile(dh)
        parentDir = fh.parent()
        p2 = parentDir.parent()
        if db.dirTypeName(p2) == 'ProtocolSequence':
            parentDir = p2
            
        
        pRow = db.getDirRowID(parentDir)
        if pRow is None:
            return None, None
            
        identity = self.dbIdentity+'.sites'
        table = dbui.getTableName(identity)
        if not db.hasTable(table):
            return None, None
        stats = db.select(table, '*', "where SourceDir=%d and SourceFile='%s'" % (pRow, fh.name(relativeTo=parentDir)))
        
        identity = self.dbIdentity+'.events'
        table = dbui.getTableName(identity)
        if not db.hasTable(table):
            return None, None
        events = db.select(table, '*', "where SourceDir=%d and SourceFile='%s'" % (pRow, fh.name(relativeTo=parentDir)))
        
        return events, stats
        
    def getDb(self):
        dbui = self.getElement('Database')
        db = dbui.getDb()
        return db


class Scan:
    def __init__(self, host, source, item):
        self.source = source
        self.item = item
        self.host = host
        self.locked = False  ## prevents flowchart changes from clearing the cache--only individual updates allowed
        self.loadFromDB()
        self.spotDict = {}  ##  fh: spot
        
    def name(self):
        return self.source.shortName()

    def rowId(self):
        db = self.host.getDb()
        table, rid = db.addDir(self.source)
        return rid

    def loadFromDB(self):
        self.events = {}
        self.stats = {}
        self.statExample = None
        for spot in self.spots():
            dh = spot.data
            fh = self.host.getClampFile(dh)
            events, stats = self.host.loadSpotFromDB(dh)
            if events is None or len(stats) == 0:
                continue
            self.statExample = stats
            self.events[fh] = {'events': events}
            self.stats[fh] = stats[0]

    def getStatsKeys(self):
        if self.statExample is None:
            return None
        else:
            return self.statExample.keys()

    def forgetEvents(self):
        if not self.locked:
            print "Scan forget events:", self.source
            self.events = {}
            self.forgetStats()
        
    def forgetStats(self):
        if not self.locked:
            print "Scan forget stats:", self.source
            self.stats = {}
        
    def recolor(self, n, nMax):
        if not self.item.isVisible():
            return
        spots = self.spots()
        progressDlg = QtGui.QProgressDialog("Computing spot colors (Map %d/%d)" % (n+1,nMax), "Cancel", 0, len(spots))
        #progressDlg.setWindowModality(QtCore.Qt.WindowModal)
        progressDlg.setMinimumDuration(250)
        ops = []
        try:
            for i in range(len(spots)):
                spot = spots[i]
                fh = self.host.getClampFile(spot.data)
                stats = self.getStats(fh)
                #print "stats:", stats
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
        #print "getStats", fh
        spot = self.getSpot(fh)
        #print "  got spot:", spot
        #except:
            #raise Exception("File %s is not in this scan" % fh.name())
        if fh not in self.stats:
            print "No stats cache for", fh.name(), "compute.."
            events = self.getEvents(fh)
            stats = self.host.processStats(events, spot)
            self.stats[fh] = stats
        return self.stats[fh]

    def getEvents(self, fh):
        if fh not in self.events:
            print "No event cache for", fh.name(), "compute.."
            events = self.host.processEvents(fh)
            self.events[fh] = events
        return self.events[fh]
        
    def spots(self):
        gi = self.item
        return gi.points()

    def updateSpot(self, fh, events, stats):
        self.events[fh] = events
        self.stats[fh] = stats

    def getSpot(self, fh):
        if fh not in self.spotDict:
            for s in self.spots():
                self.spotDict[self.host.getClampFile(s.data)] = s
        return self.spotDict[fh]

    @staticmethod
    def describe(source):
        rec = {}
        source = source
        sinfo = source.info()
        if 'sequenceParams' in sinfo:
            next = source[source.ls()[0]]
        else:
            next = source
        
        if next.exists('Clamp1.ma'):
            cname = 'Clamp1'
            file = next['Clamp1.ma']
        elif next.exists('Clamp2.ma'):
            cname = 'Clamp2'
            file = next['Clamp2.ma']
            
        data = file.read()
        info = data._info[-1]
        rec['mode'] = info['mode']
        try:
            rec['holding'] = float(sinfo['devices'][cname]['holdingSpin'])*1000.
        except:
            pass
        
        cell = source.parent()
        day = cell.parent().parent()
        dinfo = day.info()
        rec['acsf'] = dinfo.get('solution', '')
        rec['internal'] = dinfo.get('internal', '')
        rec['temp'] = dinfo.get('temperature', '')
        
        rec['cellType'] = cell.info().get('type', '')
        
        ninfo = next.info()
        if 'Temperature.BathTemp' in ninfo:
            rec['temp'] = ninfo['Temperature.BathTemp']
        return rec

        
class Map:
    mapFields = OrderedDict([
        ('cell', 'int'),
        ('scans', 'blob'),
        #('date', 'int'),
        #('name', 'text'),
        ('description', 'text'),
        ('cellType', 'text'),
        ('mode', 'text'),
        ('holding', 'real'),
        ('internal', 'text'),
        ('acsf', 'text'),
        ('drug', 'text'),
        ('temp', 'real'),
    ])
        
    def __init__(self, host, rec=None):
        self.host = host
        self.scans = []
        self.scanItems = {}  # scan: tree item
        self.points = []         ## Holds all data: [ (position, [(scan, dh), ...], spotData), ... ]
        self.pointsByFile = {}   ## just a lookup dictionary
        self.spots = []               ## used to construct scatterplotitem
        self.sPlotItem = pg.ScatterPlotItem(pxMode=False)
        
        self.header = self.mapFields.keys()[2:]
        
        self.item = QtGui.QTreeWidgetItem([""] * len(self.header))
        self.item.setFlags(QtCore.Qt.ItemIsSelectable| QtCore.Qt.ItemIsEditable| QtCore.Qt.ItemIsEnabled)
        self.item.map = self
        self.item.setExpanded(True)
        self.rowID = None
        
        if rec is not None:
            self.rowID = rec['rowid']
            scans = rec['scans']
            #del rec['scans']
            #del rec['cell']
            for i in range(len(self.header)):
                self.item.setText(i, str(rec[self.header[i]]))
            for fh,rowid in scans:
                item = QtGui.QTreeWidgetItem([fh.shortName()])
                self.scans.append((fh, item, rowid))
                self.item.addChild(item)

    def name(self, cell=None):
        rec = self.getRecord()
        if cell is None:
            cell = rec['cell']
        if cell is None:
            return ""
        name = cell.shortName()
        if rec['holding'] < -40:
            name = name + "_excitatory"
        elif rec['holding'] >= -10:
            name = name + "_inhibitory"
        return name

    def rebuildPlot(self):
        ## decide on point locations, build scatterplot
        self.points = []         ## Holds all data: [ (position, [(scan, dh), ...], spotData), ... ]
        self.pointsByFile = {}   ## just a lookup dictionary
        self.spots = []               ## used to construct scatterplotitem
        for scan in self.scans:  ## iterate over all points in all scans
            if isinstance(scan, tuple):
                continue    ## need to load before building
            self.addScanSpots(scan)
        self.sPlotItem.setPoints(self.spots)

    def addScanSpots(self, scan):
        for pt in scan.spots():
            pos = pt.scenePos()
            size = pt.boundingRect().width()
            added = False
            fh = self.host.getClampFile(pt.data)
            for pt2 in self.points:     ## check all previously added points for position match
                pos2 = pt2[0]
                dp = pos2-pos
                dist = (dp.x()**2 + dp.y()**2)**0.5
                if dist < size/3.:      ## if position matches, add scan/spot data into existing site
                    pt2[1].append((scan, pt.data))
                    pt2[2]['data'].append((scan, fh))
                    added = True
                    self.pointsByFile[pt.data] = pt2
                    break
            if not added:               ## ..otherwise, add a new site
                self.spots.append({'pos': pos, 'size': size, 'data': [(scan, fh)]})
                self.points.append((pos, [(scan, fh)], self.spots[-1]))
                self.pointsByFile[pt.data] = self.points[-1]

    def addScan(self, scan):
        if scan in self.scans:
            raise Exception("Scan already present in this map.")
        if len(self.scans) == 0:
            ## auto-populate fields
            rec = self.generateDefaults(scan)
            for i in range(2, len(self.mapFields)):
                ind = i-2
                key = self.mapFields.keys()[i]
                if key in rec and str(self.item.text(ind)) == '':
                    self.item.setText(ind, str(rec[key]))

        self.scans.append(scan)
        item = QtGui.QTreeWidgetItem([scan.name()])
        self.item.addChild(item)
        self.item.setExpanded(True)
        item.scan = scan
        self.scanItems[scan] = item

    def generateDefaults(self, scan):
        rec = {}
        source = scan.source
        sinfo = source.info()
        if 'sequenceParams' in sinfo:
            next = source[source.ls()[0]]
        else:
            next = source
        
        if next.exists('Clamp1.ma'):
            cname = 'Clamp1'
            file = next['Clamp1.ma']
        elif next.exists('Clamp2.ma'):
            cname = 'Clamp2'
            file = next['Clamp2.ma']
            
        data = file.read()
        info = data._info[-1]
        rec['mode'] = info['mode']
        try:
            rec['holding'] = float(sinfo['devices'][cname]['holdingSpin'])*1000.
        except:
            pass
        
        cell = source.parent()
        day = cell.parent().parent()
        dinfo = day.info()
        rec['acsf'] = dinfo.get('solution', '')
        rec['internal'] = dinfo.get('internal', '')
        rec['temp'] = dinfo.get('temperature', '')
        
        rec['cellType'] = cell.info().get('type', '')
        
        ninfo = next.info()
        if 'Temperature.BathTemp' in ninfo:
            rec['temp'] = ninfo['Temperature.BathTemp']
        rec['description'] = self.name(source.parent())
        return rec


    def removeScan(self, scan):
        self.scans.remove(scan)
        item = self.scanItems[scan]
        self.item.removeChild(item)
        
    def getRecord(self):
        rec = {}
        i = 0
        for k in self.mapFields:
            if k == 'scans':
                rowids = []
                for s in self.scans:
                    if isinstance(s, tuple):
                        rowids.append(s[2])
                    else:
                        rowids.append(s.rowId())
                rec[k] = rowids
            elif k == 'cell':
                if len(self.scans) == 0:
                    rec[k] = None
                else:
                    s = self.scans[0]
                    if isinstance(s, tuple):
                        rec[k] = s[0].parent()
                    else:
                        rec[k] = self.scans[0].source.parent()
            else:
                rec[k] = str(self.item.text(i))
                if self.mapFields[k] == 'real':
                    try:
                        num = rec[k].replace('C', '')
                        rec[k] = float(num)
                    except:
                        pass
                i += 1
        return rec
        
            
    def recolor(self, host):
        if not self.sPlotItem.isVisible():
            return
        spots = self.sPlotItem.points()
        for s in spots:
            data = []
            sources = s.data
            for scan, dh in sources:
                data.append(scan.getStats(dh))
            
            if len(data) == 0:
                continue
            if len(data) == 1:
                mergeData = data[0]
            else:
                mergeData = {}
                for k in data[0]:
                    vals = [d[k] for d in data]
                    try:
                        if len(data) == 2:
                            mergeData[k] = np.mean(vals)
                        else:
                            mergeData[k] = np.median(vals)
                    except:
                        mergeData[k] = vals[0]
            #print mergeData
            color = host.getColor(mergeData)
            s.setBrush(color)
            



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
        self.maps = []
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


    def newMap(self, rec=None):
        m = Map(self.host, rec)
        self.maps.append(m)
        item = m.item
        self.ui.mapTable.addTopLevelItem(item)

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
            raise Exception("No DB Loaded.")
            
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
                fh = db.getDir('ProtocolSequence', rowid)    ## NOTE: single-spot maps use a different table!
                scans.append((fh, rowid))
            rec['scans'] = scans
            self.newMap(rec)


    def loadMap(self, map):
        ## turn scan stubs into real scans
        rscans = []
        for i in range(len(map.scans)):
            scan = map.scans[i]
            if not isinstance(scan, tuple):
                rscans.append(scan)
                continue
            newScan = self.host.loadScan(scan[0])
            #newScan.item = scan[1]
            item = scan[1]
            item.scan = newScan
            rscans.append(newScan)
            map.scanItems[newScan] = item
        map.scans = rscans
            
        ## decide on point set, generate scatter plot 
        map.rebuildPlot()
        
        self.host.registerMap(map)

        
        



    def newMapClicked(self):
        ## Create a new map in the database
        try:
            self.newMap()
            self.ui.newMapBtn.success("Added.")
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
    
    def addScanClicked(self):
        try:
            scan = self.host.selectedScan()
            map = self.selectedMap()
            map.addScan(scan)
            self.writeMapRecord(map)
            map.rebuildPlot()
            self.ui.addScanBtn.success("Stored.")
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
            self.ui.removeScanBtn.success("Stored.")
        except:
            self.ui.removeScanBtn.failure("Error.")
            raise
        
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
        
    def selectedMap(self):
        item = self.ui.mapTable.currentItem()
        if not hasattr(item, 'map'):
            item = item.parent()
        return item.map
    
    def clearDBScan(self):
        try:
            self.host.clearDBScan()
            self.ui.clearDBScanBtn.success("Cleared.")
        except:
            self.ui.clearDBScanBtn.failure("Error.")
            raise
    
    def storeDBScan(self):
        try:
            self.host.storeDBScan()
            self.ui.storeDBScanBtn.success("Stored.")
        except:
            self.ui.storeDBScanBtn.failure("Error.")
            raise
    



