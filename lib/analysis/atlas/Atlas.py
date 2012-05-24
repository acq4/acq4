# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
import atlasCtrlTemplate

class Atlas(QtCore.QObject):
    
    DBIdentity = None
    
    """An Atlas is responsible for determining the position of images, cells, scan data, etc relative
    to a common coordinate system."""
    def __init__(self, state=None):
        QtCore.QObject.__init__(self)
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
        
class AtlasCtrlWidget(QtGui.QWidget):
    
    def __init__(self, atlas, host):
        QtGui.QWidget.__init__(self)
        
        self.sliceDir = None
        #self.blockUpdate = 0  ## used in CNAtlas to block re-rendering
        self.atlas = atlas
        self.host = host        
        
        self.canvas = host.getElement('Canvas')
        self.dataManager = host.dataManager()
        self.dataModel = self.dataManager.dataModel()
        self.loader = host.getElement('File Loader')
        self.loader.sigBaseChanged.connect(self.baseDirChanged)        
        
        self.ctrl = QtGui.QWidget()
        self.ui = atlasCtrlTemplate.Ui_Form()
        self.ui.setupUi(self)        
        self.ui.setSliceBtn.clicked.connect(self.setSliceClicked)
        self.ui.storeBtn.clicked.connect(self.storeToDB)        
        
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
        
        if dh.info().get('atlas', {}).has_key(self.atlas.name()):
            self.loadState()
        #else:
        #    self.updateAtlas()
    
    def storeToDB(self):
        ## collect list of cells and scans under this slice,
        ## read all positions with userTransform corrections
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
                tr = pg.Transform(info.get('userTransform', None))
                pos = tr.map(*scanInfo['position'])
                prots.append((f, pos))
            elif self.dataModel.dirType(f) == 'ProtocolSequence':
                info = f.info()
                tr = pg.Transform(info.get('userTransform', None))
                for subName in f.subDirs():
                    subf = f[subName]
                    scanInfo = subf.info().get('Scanner', None)
                    if scanInfo is None:
                        continue
                    pos = tr.map(*scanInfo['position'])
                    prots.append((subf, pos))
        
        
        
        for ident, dirType, positions in [('_cell', 'Cell', cells), ('_protocol', 'Protocol', prots)]:
            
            ## map positions, build data tables
            data, fields = self.generateDataArray(positions, dirType)
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
            table = self.ui.dbWidget.getTableName(self.atlas.DBIdentity+ident)
            
            #fields = collections.OrderedDict([
                #('SliceDir', 'directory:Slice'),
                #(dirColumn, 'directory:'+dirType),
                #('right', 'real'),
                #('anterior', 'real'),
                #('dorsal', 'real'),
            #])
            
            ## Make sure target table exists and has correct columns
            db.checkTable(table, owner=self.atlas.DBIdentity+ident, columns=fields, create=True)
            
            # delete old
            for source in set(data[dirColumn]):
                db.delete(table, where={dirColumn: source})
            
            # write new
            db.insert(table, data)
            
    
            
    
    