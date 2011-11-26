# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
import numpy as np
import ProgressDialog

class Scan(QtCore.QObject):
    ### This class represents a single photostim scan (one set of non-overlapping points)
    ### It handles processing and caching data 
    sigEventsChanged = QtCore.Signal(object)
    sigLockChanged = QtCore.Signal(object)
    sigItemVisibilityChanged = QtCore.Signal(object)
    
    def __init__(self, host, source, canvasItem, name=None):
        QtCore.QObject.__init__(self)
        self._source = source           ## DirHandle to data for this scan
        canvasItem.graphicsItem().scan = self  ## mark the graphicsItem so that we can trace back to here when it is clicked
        self.canvasItem = canvasItem
        canvasItem.sigVisibilityChanged.connect(self.itemVisibilityChanged)
        self.item = canvasItem.graphicsItem()     ## graphics item
        self.host = host                          ## the parent Photostim object
        self.dataModel = host.dataModel
        self.givenName = name
        self._locked = False  ## prevents flowchart changes from clearing the cache--only individual updates allowed
        self.loadFromDB()
        self.spotDict = {}  ##  fh: spot
        
    def itemVisibilityChanged(self):
        self.sigItemVisibilityChanged.emit(self)
        
    def source(self):
        return self._source
        
    def locked(self):
        return self._locked
        
    def lock(self, lock=True):
        ### If the scan is locked, it will no longer automatically invalidate its own cache.
        if self.locked() == lock:
            return
        self._locked = lock
        self.sigLockChanged.emit(self)
    
    def unlock(self):
        self.lock(False)
        
    def name(self):
        if self.givenName == None:
            return self.source().shortName()
        else:
            return self.givenName

    def rowId(self):
        db = self.host.getDb()
        table, rid = db.addDir(self.source())
        return table, rid

    def loadFromDB(self):
        print "Loading scan data for", self.source()
        self.events = {}
        self.stats = {}
        self.statExample = None
        haveAll = True
        for spot in self.spots():
            dh = spot.data
            #fh = self.host.getClampFile(dh)
            fh = self.dataModel.getClampFile(dh)
            events, stats = self.host.loadSpotFromDB(dh)
            if stats is None or len(stats) == 0:
                print "  No data for spot", dh
                haveAll = False
                continue
            self.statExample = stats
            self.events[fh] = {'events': events}
            self.stats[fh] = stats[0]
        if haveAll:
            print "  have data for all spots; locking."
            self.lock()

    def getStatsKeys(self):
        if self.statExample is None:
            return None
        else:
            return self.statExample.keys()

    def forgetEvents(self):
        if not self.locked():
            print "Scan forget events:", self.source()
            self.events = {}
            self.forgetStats()
        
    def forgetStats(self):
        #if not self.locked:
        print "Scan forget stats:", self.source()
        self.stats = {}
        
    def isVisible(self):
        return self.item.isVisible()
        
    def recolor(self, n, nMax):
        if not self.item.isVisible():
            return
        spots = self.spots()
        with ProgressDialog.ProgressDialog("Computing spot colors (Scan %d/%d)" % (n+1,nMax), 0, len(spots)) as dlg:
        #progressDlg = QtGui.QProgressDialog("Computing spot colors (Map %d/%d)" % (n+1,nMax), 0, len(spots))
        #progressDlg.setWindowModality(QtCore.Qt.WindowModal)
        #progressDlg.setMinimumDuration(250)
        #try:
            ops = []
            for i in range(len(spots)):
                spot = spots[i]
                fh = self.dataModel.getClampFile(spot.data)
                stats = self.getStats(fh, signal=False)
                #print "stats:", stats
                color = self.host.getColor(stats)
                ops.append((spot, color))
                dlg.setValue(i+1)
                #QtGui.QApplication.processEvents()
                if dlg.wasCanceled():
                    raise Exception("Recolor canceled by user.")
        #except:
            #raise
        #finally:
            ### close progress dialog no matter what happens
            #progressDlg.setValue(len(spots))
        
        ## delay until the very end for speed.
        for spot, color in ops:
            spot.setBrush(color)
            
        self.sigEventsChanged.emit(self)  ## it's possible events didn't actually change, but meh.
        
        
            
    def getStats(self, fh, signal=True):
        #print "getStats", fh
        spot = self.getSpot(fh)
        #print "  got spot:", spot
        #except:
            #raise Exception("File %s is not in this scan" % fh.name())
        if fh not in self.stats:
            print "No stats cache for", fh.name(), "compute.."
            events = self.getEvents(fh, signal=signal)
            try:
                stats = self.host.processStats(events, spot, fh=fh)
            except:
                print events
                raise
            self.stats[fh] = stats
        return self.stats[fh]

    def getEvents(self, fh, process=True, signal=True):
        if fh not in self.events:
            if process:
                print "No event cache for", fh.name(), "compute.."
                events = self.host.processEvents(fh)
                self.events[fh] = events
                if signal:
                    self.sigEventsChanged.emit(self)
            else:
                return None
        return self.events[fh]
        
    def getAllEvents(self):
        #print "getAllEvents", self.name()
        events = []
        for fh in self.events:
            ev = self.getEvents(fh, process=False)
            if ev is not None and len(ev['events']) > 0:
                events.append(ev['events'])
            #else:
                #print "  ", fh, ev
        #if len(self.events) == 0:
            #print "self.events is empty"
        if len(events) > 0:
            return np.concatenate(events)
        else:
            #print "scan", self.name(), "has no pre-processed events"
            return None
        
    def spots(self):
        gi = self.item
        return gi.points()

    def updateSpot(self, fh, events, stats):
        self.events[fh] = events
        self.stats[fh] = stats

    def getSpot(self, fh):
        if fh not in self.spotDict:
            for s in self.spots():
                self.spotDict[self.host.dataModel.getClampFile(s.data)] = s
        return self.spotDict[fh]
    
    @staticmethod
    def describe(dataModel, source):
        '''Generates a big dictionary of parameters that describe a scan.'''
        rec = {}
        #source = source
        #sinfo = source.info()
        #if 'sequenceParams' in sinfo:
        if dataModel.isSequence(source):
            file = dataModel.getClampFile(source[source.ls()[0]])
            #first = source[source.ls()[0]]
        else:
            file = dataModel.getClampFile(source)
            #first = source
        
        #if next.exists('Clamp1.ma'):
            #cname = 'Clamp1'
            #file = next['Clamp1.ma']
        #elif next.exists('Clamp2.ma'):
            #cname = 'Clamp2'
            #file = next['Clamp2.ma']
        #else:
            #return {}
        
        if file == None:
            return {}
            
        #data = file.read()
        #info = data._info[-1]
        rec['mode'] = dataModel.getClampMode(file)
        rec['holding'] = dataModel.getClampHoldingLevel(file)
        
        #if 'ClampState' in info:
            #rec['mode'] = info['ClampState']['mode']
            #rec['holding'] = info['ClampState']['holding']
        #else:
            #try:
                #rec['mode'] = info['mode']
                #rec['holding'] = float(sinfo['devices'][cname]['holdingSpin'])*1000.
            #except:
                #pass
        
        #cell = source.parent()
        #day = cell.parent().parent()
        #dinfo = day.info()
        #rec['acsf'] = dinfo.get('solution', '')
        rec['acsf'] = dataModel.getACSF(file)
        #rec['internal'] = dinfo.get('internal', '')
        rec['internal'] = dataModel.getInternalSoln(file)
        
        #rec['temp'] = dinfo.get('temperature', '')
        rec['temp'] = dataModel.getTemp(file)
        
        #rec['cellType'] = cell.info().get('type', '')
        rec['cellType'] = dataModel.getCellType(file)
        
        #ninfo = next.info()
        #if 'Temperature.BathTemp' in ninfo:
            #rec['temp'] = ninfo['Temperature.BathTemp']
        return rec
