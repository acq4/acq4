# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
from . import atlasCtrlTemplate
import acq4.pyqtgraph as pg
from acq4.util.debug import Profiler

class Atlas(Qt.QObject):
    
    DBIdentity = None
    
    """An Atlas is responsible for determining the position of images, cells, scan data, etc relative
    to a common coordinate system."""
    def __init__(self, state=None):
        Qt.QObject.__init__(self)
        if state is not None:
            self.restoreState(state)
    
    def ctrlWidget(self, host):
        raise Exception("Must be reimplemented in subclass.")
    
    def mapToAtlas(self, obj):
        """Maps obj into atlas coordinates. Obj can be any object mappable by QMatrix4x4"""
        raise Exception("Must be reimplemented in subclass.")

    def getState(self):
        raise Exception("Must be reimplemented in subclass.")

    def setState(self, state):
        raise Exception("Must be reimplemented in subclass.")

    def restoreState(self, state):
        raise Exception("Must be reimplemented in subclass.")
    
    def name(self):
        """Returns the name of the atlas"""
        raise Exception("Must be reimplemented in subclass.")
    #def close(self):
        #pass
        
class AtlasCtrlWidget(Qt.QWidget):
    
    def __init__(self, atlas, host):
        Qt.QWidget.__init__(self)
        
        self.sliceDir = None
        #self.blockUpdate = 0  ## used in CNAtlas to block re-rendering
        self.atlas = atlas
        self.host = host        
        
        self.canvas = host.getElement('Canvas')
        self.dataManager = host.dataManager()
        self.dataModel = self.dataManager.dataModel()
        self.loader = host.getElement('File Loader')
        self.loader.sigBaseChanged.connect(self.baseDirChanged)        
        
        self.ctrl = Qt.QWidget()
        self.ui = atlasCtrlTemplate.Ui_Form()
        self.ui.setupUi(self)        
        self.ui.setSliceBtn.clicked.connect(self.setSliceClicked)
        self.ui.storeBtn.clicked.connect(self.storeBtnClicked)        
        
        #self.baseDirChanged()
                
        ## set up two tables for storing atlas positions of cells and stimulation sites
        
        if atlas.DBIdentity == None:
            raise Exception("Atlas needs to have a DBIdentity specified." )
        
        tables = {
            atlas.DBIdentity+"_cell": "%s_Cell" %atlas.name(),
            atlas.DBIdentity+"_protocol": "%s_Protocol" %atlas.name(),
        }                
        self.ui.dbWidget.setDataManager(self.dataManager)
        self.ui.dbWidget.setTables(tables)    
    
    def loadState(self):
        raise Exception("Must be re-implemented in subclass.")
        
    def saveState(self):
        raise Exception("Must be re-implemented in subclass.")     
 
    def generateDataArray(self, positions, dirType):
        """Return a tuple (data, fields). Data should be a record array with the column names/values to be stored. 
        Fields should be an OrderedDict of column names : sql datatype."""
        raise Exception("Must be re-implemented in subclass")    
        
    def baseDirChanged(self):
        ## file loader base dir changed; if it s a slice, set it now.
        try:
            self.setSliceDir(self.loader.baseDir())
        except:
            pass    
        
    def setSliceClicked(self):
            dh = self.loader.selectedFiles()
            if len(dh) != 1:
                raise Exception('Select a slice directory from the file tree.')
            self.setSliceDir(dh[0])
            
    def setSliceDir(self, dh):
        if not dh.isDir() or not self.dataModel.dirType(dh) == 'Slice':
            #self.sliceRoi.setVisible(False)
            self.sliceDir = None
            self.ui.sliceLabel.setText('None')
            raise Exception('Selected file is not a slice directory')
        
        self.sliceDir = dh
        #self.sliceRoi.setVisible(True)
        base = self.loader.baseDir()
        if dh is base:
            name = dh.shortName()
        else:
            name = dh.name(relativeTo=base)
        self.ui.sliceLabel.setText(name)
        
        if self.atlas.name() in dh.info().get('atlas', {}):
            self.loadState()
        #else:
        #    self.updateAtlas()
        
    def storeBtnClicked(self):
        self.ui.storeBtn.processing("Storing...")
        try:
            self.storeToDB()
            self.ui.storeBtn.success("Stored!")
        except:
            self.ui.storeBtn.failure()
            raise
    
    def storeToDB(self):
        ## collect list of cells and scans under this slice,
        ## read all positions with userTransform corrections
        prof = Profiler("Atlas.storeToDB", disabled=True)
        loaded = self.host.getLoadedFiles()
        cells = []
        prots = []
        for f in loaded:
            if not f.isDir() or not f.isGrandchildOf(self.sliceDir):
                continue
            if self.dataModel.dirType(f) == 'Cell':
                info = f.info()
                if 'userTransform' not in info:
                    continue
                cells.append((f, info['userTransform']['pos']))
            elif self.dataModel.dirType(f) == 'Protocol':
                info = f.info()
                scanInfo = info.get('Scanner', None)
                if scanInfo is None:
                    continue
                tr = pg.SRTTransform(info.get('userTransform', None))
                pos = tr.map(*scanInfo['position'])
                prots.append((f, pos))
            elif self.dataModel.dirType(f) == 'ProtocolSequence':
                info = f.info()
                tr = pg.SRTTransform(info.get('userTransform', None))
                for subName in f.subDirs():
                    subf = f[subName]
                    scanInfo = subf.info().get('Scanner', None)
                    if scanInfo is None:
                        continue
                    pos = tr.map(*scanInfo['position'])
                    prots.append((subf, pos))
        
        prof.mark("made list of positions")
        
        
        for ident, dirType, positions in [('_cell', 'Cell', cells), ('_protocol', 'Protocol', prots)]:
            
            ## map positions, build data tables
            data, fields = self.generateDataArray(positions, dirType)
            prof.mark("got data arrays for %s" %dirType)
            #dirColumn = dirType + 'Dir'
            #data = np.empty(len(positions), dtype=[('SliceDir', object), (dirColumn, object), ('right', float), ('anterior', float), ('dorsal', float)])
            
            #for i in range(len(positions)):
                #dh, pos = positions[i]
                #mapped = self.atlas.mapToAtlas(pg.Point(pos))
                ##print dh, pos
                ##print "  right:", mapped.x()
                ##print "  anter:", mapped.y()
                ##print "  dorsl:", mapped.z()
                #data[i] = (self.sliceDir, dh, mapped.x(), mapped.y(), mapped.z())
            
            ## write to DB
            db = self.ui.dbWidget.getDb()
            prof.mark('got db')
            table = self.ui.dbWidget.getTableName(self.atlas.DBIdentity+ident)
            prof.mark('got table')
            
            #fields = collections.OrderedDict([
                #('SliceDir', 'directory:Slice'),
                #(dirColumn, 'directory:'+dirType),
                #('right', 'real'),
                #('anterior', 'real'),
                #('dorsal', 'real'),
            #])
            
            ## Make sure target table exists and has correct columns
            db.checkTable(table, owner=self.atlas.DBIdentity+ident, columns=fields, create=True)
            prof.mark('checked table')
            
            ## delete old -- This is the slow part!
            old = db.select(table, where={'SliceDir':self.sliceDir}, toArray=True)
            if old is not None: ## only do deleting if there is already data stored for this slice -- try to speed things up
                for source in set(data[dirType+'Dir']):
                    if source in old[dirType+'Dir']: ## check that source is in the old data before we delete it - try to speed things up
                        db.delete(table, where={dirType+'Dir': source})
            prof.mark('deleted old data') 
            
            ## write new
            db.insert(table, data)
            prof.mark("added %s data to db" %dirType)
            
        prof.finish()
            
    
            
    
    