# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
import numpy as np
import acq4.pyqtgraph as pg
import acq4.pyqtgraph.multiprocess as mp
import six
import time, os
import acq4.util.Canvas as Canvas
import collections
import acq4.util.functions as fn

def loadScanSequence(fh, host):
    ## Load a scan (or sequence of scans) from fh,
    ## return a Scan object (or list of Scan objects)
    
    dataModel = host.dataModel
    
    if dataModel.isSequence(fh):  ## If we are loading a sequence, there will be multiple spot locations and/or multiple scans.
        ## get sequence parameters
        params = dataModel.listSequenceParams(fh).deepcopy()  ## copy is required since this info is read-only.
        if ('Scanner', 'targets') in params:
            #params.remove(('Scanner', 'targets'))  ## removing this key enables us to process other sequence variables independently
            del params[('Scanner', 'targets')]
    
            
        ## Determine the set of subdirs for each scan present in the sequence
        ## (most sequences will have only one scan)
        scans = {}
        for dhName in fh.subDirs():
            dh = fh[dhName]
            key = '_'.join([str(dh.info()[p]) for p in params])
            if key not in scans:
                scans[key] = []
            scans[key].append(dh)

    else:  ## If we are not loading a sequence, then there is only a single spot
        scans = {None: [fh]}
        #seq = False
        #parent = None


    ## Add each scan
    
        
    ret = []
    for key, subDirs in scans.items():
        if len(scans) > 1:
            name = key
            sname = fh.shortName() + '.' + key
        else:
            name = fh.shortName()
            sname = name
        scan = Scan(host, fh, subDirs, name=sname, itemName=name)
        ret.append(scan)
    
    print(ret)
    return ret

            

class Scan(Qt.QObject):
    ### This class represents a single photostim scan (one set of non-overlapping points)
    ### It handles processing and caching data 
    sigEventsChanged = Qt.Signal(object)
    sigLockStateChanged = Qt.Signal(object)  # self
    sigItemVisibilityChanged = Qt.Signal(object)
    sigStorageStateChanged = Qt.Signal(object) #self
    
    def __init__(self, host, source, dirHandles, name=None, itemName=None):
        Qt.QObject.__init__(self)
        self._source = source           ## DirHandle to data for this scan
        self.dirHandles = []            ## List of DirHandles, one per spot
        
        for d in dirHandles:       ## filter out any dirs which lack the proper data
            info = d.info()
            if 'Scanner' in info and 'position' in info['Scanner']:
                self.dirHandles.append(d)
        
        self._canvasItem = None
        
        self.host = host                          ## the parent Photostim object
        self.dataModel = host.dataModel
        self.givenName = name
        self.itemName = itemName
        self.events = {}    ## {'events': ...}
        self.stats = {}     ## {protocolDir: stats}
        self.spotDict = {}  ## protocolDir: spot 
        self.statsLocked = False  ## If true, cache of stats can not be overwritten
        self.eventsLocked = False  ## If true, cache of events can not be overwritten
        self.statCacheValid = set()  ## If dh is in set, stat flowchart has not changed since stats were last computed
        self.eventCacheValid = set() ## if fh is in set, event flowchart has not changed since events were last computed
        self.statsStored = False 
        self.eventsStored = False
        self.canvasItem() ## create canvas item
        self.loadFromDB()
        
    def canvasItem(self):
        if self._canvasItem is None:
            self._canvasItem = Canvas.items.ScanCanvasItem.ScanCanvasItem(handle=self.source(), subDirs=self.dirHandles, name=self.itemName)
            self._canvasItem.graphicsItem().scan = self  ## mark the graphicsItem so that we can trace back to here when it is clicked
            self._canvasItem.sigVisibilityChanged.connect(self.itemVisibilityChanged)
            self.item = self._canvasItem.graphicsItem()     ## graphics item
        return self._canvasItem

        
    def itemVisibilityChanged(self):
        self.sigItemVisibilityChanged.emit(self)
        
    def source(self):
        return self._source
        
    def handles(self):
        return self.dirHandles
        
    def getTimes(self):
        """
        Return a list of (dirHandle, start, end) time values for each spot.
        """
        times = []
        for dh in self.handles():
            fh = self.dataModel.getClampFile(dh)
            if fh is None:
                continue
            start = fh.info()['__timestamp__']
            p = dh.parent()
            if self.dataModel.isSequence(p):
                stop = start + dh.parent().info()['protocol']['conf']['duration']
            else:
                stop = start + dh.info()['protocol']['conf']['duration']
            times.append((dh, start, stop))
        return times
        
        
    #def locked(self):
        #return self._locked
        
    #def lock(self, lock=True):
        #### If the scan is locked, it will no longer automatically invalidate its own cache.
        #if self.locked() == lock:
            #return
        #self._locked = lock
        #self.sigLockChanged.emit(self)
    
    #def unlock(self):
        #self.lock(False)
        
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
        sourceDir = self.source()
        #print "Loading scan data for", sourceDir
        self.events = {}
        self.stats = {}
        self.statExample = None
        haveAll = True
        haveAny = False
        
        if self.host.dataModel.dirType(sourceDir) == 'ProtocolSequence':
            allEvents, allStats = self.host.loadScanFromDB(sourceDir)
        else:
            allEvents, allStats = self.host.loadSpotFromDB(sourceDir)
            
        if allEvents is None and allStats is None:
            return 
        
     
        if allEvents is not None:
            for ev in allEvents:
                fh = ev['SourceFile'] ## sourceFile has already been converted to file handle.
                if fh not in self.events:
                    self.events[fh] = []
                self.events[fh].append(ev.reshape(1))
            for k in self.events:
                self.events[k] = {'events': np.concatenate(self.events[k])}
        
        if allStats is not None:   
            for st in allStats:
                self.stats[st['ProtocolDir']] = st
                
            for dh in self.dirHandles:
                fh = self.dataModel.getClampFile(dh)
                if fh not in self.events:
                    if allEvents is None:
                        self.events[fh] = {'events': []} ## what to do?? not sure how to get the dtype in this case.
                    else:
                        self.events[fh] = {'events': np.empty(0, dtype=allEvents.dtype)}
                    
                if dh not in self.stats:
                    haveAll = False
                    for spot in self.spots():
                        if spot.data() is dh:
                            spot.setPen((100,0,0,200))
                    continue
                else:
                    haveAny = True
                    self.statExample = self.stats[dh]
                    
            if haveAll:
                #print "  have data for all spots; locking."
                self.lockEvents()
                self.lockStats()
                self.statsStored = True
                self.eventsStored = True
                self.sigStorageStateChanged.emit(self)
            
            ## If there is _no_ data for this scan, recolor spots grey.
            if not haveAny:
                for s in self.item.points():
                    s.setPen((50,50,50,200))
                
                

    def getStatsKeys(self):
        if self.statExample is None:
            return None
        else:
            return list(self.statExample.keys())

    
    def lockStats(self, lock=True):
        emit = self.statsLocked != lock
        self.statsLocked = lock
        
        if lock:
            self.lockEvents()
        if emit:
            self.sigLockStateChanged.emit(self)
            
        
    def lockEvents(self, lock=True):
        emit = self.eventsLocked != lock
        self.eventsLocked = lock
            
        if not lock:
            self.lockStats(False)
        if emit:
            self.sigLockStateChanged.emit(self)
        
        
    def getLockState(self):
        return self.eventsLocked, self.statsLocked
        
    def getStorageState(self):
        return self.eventsStored, self.statsStored
        
    def invalidateEvents(self):
        #print "events invalidated"
        self.eventCacheValid = set()
        self.invalidateStats()
            
    def invalidateStats(self):
        #print "stats invalidated"
        self.statCacheValid = set()
            
    ## 'forget' methods are no longer allowed.
    #def forgetEvents(self):
        #if not self.locked():
            #self.events = {}
            #self.forgetStats()
        
    #def forgetStats(self):
        #self.stats = {}
        
    def isVisible(self):
        return self.item.isVisible()
        
    def recolor(self, n, nMax, parallel=False):
        if not self.item.isVisible():
            return
        spots = self.spots()
        handles = [(spot.data(), self.host.dataModel.getClampFile(spot.data())) for spot in spots]
        result = []
        
        ## This can be very slow; try to run in parallel (requires fork(); runs serially on windows).
        start = time.time()
        workers = None if parallel else 1
        msg = "Processing scan (%d / %d)" % (n+1, nMax)
        with mp.Parallelize(tasks=enumerate(handles), result=result, workers=workers, progressDialog=msg) as tasker:
            for i, dhfh in tasker:
                dh, fh = dhfh
                events = self.getEvents(fh, signal=False)
                stats = self.getStats(dh, signal=False)
                color = self.host.getColor(stats)
                tasker.result.append((i, color, stats, events))
                
        print("recolor took %0.2fsec" % (time.time() - start))
        
        ## Collect all results, store to caches, and recolor spots
        for i, color, stats, events in result:
            dh, fh = handles[i]
            self.updateStatCache(dh, stats)
            self.updateEventCache(fh, events, signal=False)
            spot = spots[i]
            spot.setBrush(color)
        
        self.sigEventsChanged.emit(self)  ## it's possible events didn't actually change, but meh.
        
        
            
    def getStats(self, dh, signal=True):
        ## Return stats for a single file. (cached if available)
        ## fh is the clamp file
        #print "getStats", dh
        spot = self.getSpot(dh)
        #print "  got spot:", spot
        #except:
            #raise Exception("File %s is not in this scan" % fh.name())
        if dh not in self.stats or (not self.statsLocked and dh not in self.statCacheValid):
            #print "No stats cache for", dh.name(), "compute.."
            fh = self.host.dataModel.getClampFile(dh)
            events = self.getEvents(fh, signal=signal)
            try:
                stats = self.host.processStats(events, spot)
            except:
                print(events)
                raise
            
            ## NOTE: Cache update must be taken care of elsewhere if this function is run in a parallel process!
            self.updateStatCache(dh, stats)
            
        return self.stats[dh].copy()
        
    def updateStatCache(self, dh, stats):
        self.stats[dh] = stats
        self.statCacheValid.add(dh)
        self.statsStored = False
        self.sigStorageStateChanged.emit(self)

    def getEvents(self, fh, process=True, signal=True):
        if fh not in self.events or (not self.eventsLocked and fh not in self.eventCacheValid):
            
            ## this should never happen
            #p = fh.parent()  ## If we have stats but no events, then just return an empty list.
            #if p in self.stats:
                #return []
            
            if process:
                #print "No event cache for", fh.name(), "compute.."
                events = self.host.processEvents(fh)  ## need ALL output from the flowchart; not just events
                ## NOTE: Cache update must be taken care of elsewhere if this function is run in a parallel process!
                self.updateEventCache(fh, events, signal)
            else:
                return None
        return self.events[fh]
        
    def updateEventCache(self, fh, events, signal=True):
        self.events[fh] = events
        self.eventCacheValid.add(fh)
        self.eventsStored = False
        self.sigStorageStateChanged.emit(self)
        if signal:
            self.sigEventsChanged.emit(self)
        
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

    def updateSpot(self, dh, events, stats):
        ## called from photostim.storeDBSpot
        self.events[self.host.dataModel.getClampFile(dh)] = events
        self.stats[dh] = stats
        for spot in self.spots():
            if spot.data() is dh:
                spot.setPen((50,50,50))
        

    def getSpot(self, dh):
        if dh not in self.spotDict:
            for s in self.spots():
                self.spotDict[s.data()] = s
        return self.spotDict[dh]
    
    @staticmethod
    def describe(dataModel, source):
        '''Generates a big dictionary of parameters that describe a scan.'''
        rec = {}
        #source = source
        #sinfo = source.info()
        #if 'sequenceParams' in sinfo:
        if dataModel.isSequence(source):
            file = dataModel.getClampFile(source[source.ls(sortMode=None)[0]])
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

    def storeToDB(self):
        if self.eventsStored and self.statsStored:
            return
        self.host.storeDBScan(self, storeEvents=(not self.eventsStored))
        self.eventsStored = True
        self.statsStored = True
        self.sigStorageStateChanged.emit(self)
        self.lockEvents(True)
        self.lockStats(True)
        for s in self.item.points():
            s.setPen((50,50,50,200))
        
    def clearFromDB(self):
        self.host.clearDBScan(self)
        self.eventsStored = False
        self.statsStored = False
        self.sigStorageStateChanged.emit(self)
        self.lockEvents(False)
        self.lockStats(False)
        
        
    def displayData(self, fh, plot, pen, evTime=None, eventFilter=None):
        """
        Display data for a single site in a plot--ephys trace, detected events
        Returns all items added to the plot.
        """
        pen = pg.mkPen(pen)
        
        items = []
        if isinstance(fh, six.string_types):
            fh = self.source()[fh]
        if fh.isDir():
            fh = self.dataModel.getClampFile(fh)
            
        ## plot all data, incl. events
        data = fh.read()['primary']
        data = fn.besselFilter(data, 4e3)
        pc = plot.plot(data, pen=pen, clear=False)
        items.append(pc)
        
        ## mark location of event if an event index was given
        if evTime is not None:
            #pos = float(index)/len(data)
            pos = evTime / data.xvals('Time')[-1]
            #print evTime, data.xvals('Time')[-1], pos
            #print index
            arrow = pg.CurveArrow(pc, pos=pos)
            plot.addItem(arrow)
            items.append(arrow)
            
        events = self.getEvents(fh)['events']
        
        if eventFilter is not None:
            events = eventFilter(events)
        
        ## draw ticks over all detected events
        if len(events) > 0:
            if 'fitTime' in events.dtype.names:
                times = events['fitTime']
                ticks = pg.VTickGroup(times, [0.9, 1.0], pen=pen)
                plot.addItem(ticks)
                items.append(ticks)
                #self.mapTicks.append(ticks)
                
            ## draw event fits
            evPen = pg.mkPen(pen)
            c = evPen.color()
            c.setAlpha(c.alpha()/2)
            evPen.setColor(c)
            for ev in events:
                time = ev['fitTime']
                try:
                    fitLen = ev['fitDecayTau']*ev['fitLengthOverDecay']
                except IndexError:
                    fitLen = ev['fitDecayTau']*4.
                x = np.linspace(time, time+fitLen, fitLen * 50e3)
                v = [ev['fitAmplitude'], ev['fitTime'], ev['fitRiseTau'], ev['fitDecayTau']]
                y = fn.pspFunc(v, x, risePower=2.0) + data[np.argwhere(data.xvals('Time')>time)[0]-1]
                evc = plot.plot(x, y, pen=evPen)
                evc.setZValue(pc.zValue()-100)
                
        return items

