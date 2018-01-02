from __future__ import print_function
import six
from six.moves import range

from .database import *
from acq4.util import DataManager
from acq4.pyqtgraph.widgets.ProgressDialog import ProgressDialog
import acq4.util.debug as debug
from acq4.Manager import logExc, logMsg


class AnalysisDatabase(SqliteDatabase):
    """Defines the structure for DBs used for analysis. Essential features are:
     - a table of control parameters "DbParameters"
       these are just key: value pairs used by the database to store configuration variables
     - a table defining relationships between tables "TableRelationships"
       lets you declare "table1.column1 refers to table2.rowid"
     - a table assgning ownership of data tables to analysis modules
       this ensures that analysis modules do not accidentally access tables belonging to another module.
     - Directories created by data manager can be added automatically to DB
       one table for each type of directory (Day, Cell, Protocol, etc)
     - Automatic creation of views that join together directory hierarchies
     - Automatic storage/retrieval of directory and file handles
     """
    
    MetaTypes = {
        'directory': 'int',   # reference to a record in a directory table
        'file': 'text',       # 
    }
    
    Version = '1'


    def __init__(self, dbFile, dataModel, baseDir=None):
        create = False
        self.tableConfigCache = None
        self.columnConfigCache = advancedTypes.CaselessDict()
        
        self.setDataModel(dataModel)
        self._baseDir = None
        if not os.path.exists(dbFile):
            create = True
            if baseDir is None:
                raise Exception("Must specify a base directory when creating a database.")

        #self.db = SqliteDatabase(dbFile)
        
        if not create:
            ## load DB and check version before initializing
            db = SqliteDatabase(dbFile)
            if not db.hasTable('DbParameters'):
                raise Exception("Invalid analysis database -- no DbParameters table.")
            recs = db.select('DbParameters', ['Value'], where={'Param': 'DB Version'})
            db.close()
            if len(recs) == 0:
                version = None
            else:
                version = recs[0]['Value']
            
            if version != AnalysisDatabase.Version:
                self._convertDB(dbFile, version)
        
        SqliteDatabase.__init__(self, dbFile)
        self.file = dbFile
        
        if create:
            self.initializeDb()
            self.setBaseDir(baseDir)
            self.setCtrlParam('DB Version', AnalysisDatabase.Version)
            self.setCtrlParam('Description', '')
            
            
    def setDataModel(self, dm):
        self._dataModel = dm
        
    def dataModel(self):
        return self._dataModel
            
    def _convertDB(self, dbFile, version):
        ## Convert datbase dbFile from version to the latest version
        
        newFileName = dbFile+"version_upgrade"
        if os.path.exists(newFileName):
            raise Exception("A .version_upgrade for %s already exists. Please delete or rename it" %dbFile)
        if version is None:
            prog = ProgressDialog("Converting database...")
            from .AnalysisDatabase_ver0 import AnalysisDatabase as AnalysisDatabaseOld
            oldDb = AnalysisDatabaseOld(dbFile)
            newDb = AnalysisDatabase(newFileName, self.dataModel(), oldDb.baseDir())
            
            dirTypes = ['Day', 'Experiment', 'Slice', 'Cell', 'Site', 'Protocol', 'ProtocolSequence']
            print(oldDb.listTables())
            for table in dirTypes:
                if not oldDb.hasTable(table):
                    continue
                for rec in oldDb.select(table):
                    dh = oldDb.baseDir()[rec['Dir']]
                    try:
                        newDb.addDir(dh)
                    except:
                        print("Can't add directory %s from old DB:" % dh.name())
                        debug.printExc()
                    
            total = len(oldDb.select('Photostim_events')) + len(oldDb.select('Photostim_sites'))
            n=0

            for table in ['Photostim_events', 'Photostim_sites', 'Photostim_events2', 'Photostim_sites2']:
                if prog.wasCanceled():
                    break
                if not oldDb.hasTable(table):
                    continue
                schema = oldDb.tableSchema(table)
                ## SourceDir -> ProtocolSequenceDir     type='directory:ProtocolSequence'
                del schema['SourceDir']
                schema['ProtocolSequenceDir'] = 'directory:ProtocolSequence'
                
                ## add column ProtocolDir
                schema['ProtocolDir'] = 'directory:Protocol'
                
                ## SourceFile -> ?        type='file'
                if 'SourceFile' in schema:
                    schema['SourceFile'] = 'file'
                
                owner = oldDb.tableOwner(table)
                newDb.createTable(table, schema, owner=owner)
                
                
                
                records = oldDb.select(table)
                for r in records:
                    if prog.wasCanceled():
                        break
                ##  SourceFile -> convert to filehandle
                    r['SourceFile']= oldDb.getDir('ProtocolSequence', r['SourceDir'])[r['SourceFile']]
                    del r['SourceDir']
                ##  ProtocolDir, ProtocolSequenceDir -> dirHandles
                    #r['ProtocolSequenceDir'] = oldDb.getDir('ProtocolSequence', r['SourceDir'])
                    r['ProtocolDir'] = r['SourceFile'].parent()
                    r['ProtocolSequenceDir'] = self.dataModel().getParent(r['ProtocolDir'], 'ProtocolSequence')
                    n+=1
                    prog.setValue(n/total)
                
                newDb.insert(table, records)
            
            
            oldDb.close()
            newDb.close()
            if not prog.wasCanceled():
                os.rename(dbFile, dbFile+'version_upgrade_backup')
                os.rename(newFileName, dbFile)
        else:
            raise Exception("Don't know how to convert from version %s" % str(version))
        
            #params = self.select('DbParameters')
            #self.removeTable('DbParameters')
            
            #self.initializeDb()
            
            #for rec in params:
                #self.setCtrlParam(rec['Param'], rec['Value'])
            
            ### update all dir tables
            #for dirType in dirTypes:
                #if not self.hasTable(dirType):
                    #continue
                #newName = self.dirTableName(dirType)
                #self.insert('TableConfig', Table=newName, DirType=dirType)
                
                #ts = self.tableSchema(dirType)
                #link = self.select('TableRelationships', ['Column', 'Table2'], sql='where Table1="%s"' % dirType)[0]
                #linkedType = link['Table2']
                
                #ts[linkedType] = ('directory:%s' % linkedType)
                #del ts[link['Column']]
                #self.createTable(newName, ts.items())
                
                #records = self.select(dirType)
                #for rec in records:
                    #rec[linkedType] = rec[link['Column']]
                    ### TODO: need to convert integers to handles here..
                    #del rec[link['Column']]
                #self.insert(newName, records)
                
                #self.removeTable(dirType)
                
            
            
            ##for link in self.select('TableRelationships'):
                ##self.linkTables(link['Table1'], link['Column'], link['Table2'])
            #self.removeTable('TableRelationships')
            
    def initializeDb(self):
        SqliteDatabase.createTable(self, 'DbParameters', [('Param', 'text', 'unique'), ('Value', 'text')])
        
        ## Table1.Column refers to Table2.ROWID
        ## obsolete--use TableConfig now.
        #self.createTable("TableRelationships", ['"Table1" text', '"Column" text', '"Table2" text'])
        
        ## Stores meta information about tables:
        ##   Owner  - prevents table name collisions, allows users of the DB to be 
        ##            (nearly) assured exclusive access to a table. (I say 'nearly'
        ##            because this is a voluntary restriction--each DB user must check
        ##            for table ownership before accessing the table.)
        ##   DirType - If this is a directory table, then the directory type is stored
        ##             here. Otherwise, the field is blank.
        SqliteDatabase.createTable(self, 'TableConfig', [('Table', 'text', 'unique on conflict abort'), ('Owner', 'text'), ('DirType', 'text')])
        self('create index "TableConfig_byOwner" on "TableConfig" ("Owner")')
        self('create index "TableConfig_byTable" on "TableConfig" ("Table")')
        
        ## stores column arguments used when creating tables
        ## This is similar to the information returned by tableSchema(), but 
        ## contains extra information and data types not supported by SqliteDatabase
        fields = ['Table', 'Column', 'Type', 'Link', 'Constraints']
        SqliteDatabase.createTable(self, 'ColumnConfig', [(field, 'text') for field in fields])
        self('create index "ColumnConfig_byTable" on "ColumnConfig" ("Table")')
        self('create index "ColumnConfig_byTableColumn" on "ColumnConfig" ("Table", "Column")')

    def baseDir(self):
        """Return a dirHandle for the base directory used for all file names in the database."""
        if self._baseDir is None:
            dirName = self.ctrlParam('BaseDirectory')
            self._baseDir = DataManager.getHandle(dirName)
        return self._baseDir
        
    def setBaseDir(self, baseDir):
        """Sets the base dir which prefixes all file names in the database. Must be a DirHandle."""
        self.setCtrlParam('BaseDirectory', baseDir.name())
        self._baseDir = baseDir

    def ctrlParam(self, param):
        res = SqliteDatabase.select(self, 'DbParameters', ['Value'], sql="where Param='%s'"%param)
        if len(res) == 0:
            return None
        else:
            return res[0]['Value']
        
    def setCtrlParam(self, param, value):
        self.replace('DbParameters', {'Param': param, 'Value': value})
        

    def createTable(self, table, columns, sql="", owner=None, dirType=None):
        """
        Extends SqliteDatabase.createTable to allow more descriptve column specifications.
        
        - Columns are specified as either a tuple (name, type, constraints, link)
          or a dict {'name': name, ...}
          
        - The added 'link' column parameter should be the name of a table, indicating
          that this column refers to the rowids of the linked table.
        
        - Two new column type specifications:
            directory:DirType  - the column will be an integer referencing a row from 
                                 the DirType (Protocol, Cell, etc) directory table.
                                 Directory handles stored in this column will be
                                 automatically converted to/from their row ID.
                                 This type implies link=DirTypeTable
            file - the column will be a text file name relative to the DB base directory.
                   File/DirHandles will be automatically converted to/from their
                   text value.
                   
                   
            example: 
            
            columnConfig = [
                ('Column1', 'directory:Protocol'), 
                ('Column2', 'file', 'unique'),
                dict(Name='Column3', Type='int', Link='LinkedTable')
            ]
            db.createTable("TableName", columnConfig)
        """
        
        ## translate directory / file columns into int / text
        ## build records for insertion to ColumnConfig
        columns = parseColumnDefs(columns, keyOrder=['Type', 'Constraints', 'Link'])
            
        records = []
        colTuples = []
        for name, col in columns.items():
            rec = {'Column': name, 'Table': table, 'Link': None, 'Constraints': None}
            rec.update(col)
            
            typ = rec['Type']
            typ, link = self.interpretColumnType(typ)
            if link is not None:
                rec['Link'] = link
            
            tup = (rec['Column'], typ)
            if rec['Constraints'] is not None:
                tup = tup + (rec['Constraints'],)
            colTuples.append(tup)
            records.append(rec)
            
            
        ret = SqliteDatabase.createTable(self, table, colTuples, sql)
        
        self.insert('ColumnConfig', records)
        
        tableRec = dict(Table=table, Owner=owner, DirType=dirType)
        self.insert('TableConfig', tableRec)
        self.tableConfigCache = None
        
        return ret
        
    def interpretColumnType(self, typ):
        ## returns: (Sqlite type, Link)
        link = None
        if typ.startswith('directory'):
            link = self.dirTableName(typ.lstrip('directory:'))
            typ = 'int'
        elif typ == 'file':
            typ = 'text'
        return typ, link
    

    def addColumn(self, table, colName, colType, constraints=None):
        """
        Add a new column to a table.
        """
        typ, link = self.interpretColumnType(colType)
        SqliteDatabase.addColumn(self, table, colName, typ, constraints)
        self.insert('ColumnConfig', {'Column': colName, 'Table': table, 'Type': colType, 'Link': link})
        if table in self.columnConfigCache:
            del self.columnConfigCache[table]
    
    
    def checkTable(self, table, owner, columns, create=False, ignoreUnknownColumns=False, addUnknownColumns=False, indexes=None):
        """
        Checks to be sure that a table has been created with the correct fields and ownership.
        This should generally be run before attempting to access a table.
        If the table does not exist and create==True, then the table will be created with the 
        given columns and owner. 
        
        If ignoreUnknownColumns==True, then any columns in the data
        that are not also in the table will be ignored. (Note: in this case, an insert may fail
        unless ignoreUnknownColumns=True is also specified when calling insert())
        
        If addUnknownColumns==True, then any columns in the data
        that are not also in the table will be created in the table.

        If indexes is supplied and create==True, then the specified indexes will be created
        if they do not already exist by calling db.createIndex(table, index) once for each item in indexes.
        """
        columns = parseColumnDefs(columns, keyOrder=['Type', 'Constraints', 'Link'])
        ## Make sure target table exists and has correct columns, links to input file
        with self.transaction():
            if not self.hasTable(table):
                if create:
                    ## create table
                    self.createTable(table, columns, owner=owner)
                else:
                    raise Exception("Table %s does not exist." % table)
            else:
                ## check table for ownership
                if self.tableOwner(table) != owner:
                    raise Exception("Table %s is not owned by %s." % (table, owner))
                
                ## check table for correct columns
                ts = self.tableSchema(table)
                config = self.getColumnConfig(table)
                
                for colName, col in columns.items():
                    colType = col['Type']
                    if colName not in ts:  ## <-- this is a case-insensitive operation
                        if ignoreUnknownColumns:
                            continue
                        elif addUnknownColumns:
                            self.addColumn(table, colName, colType)
                            ts = self.tableSchema(table) ## re-read schema and column config
                            config = self.getColumnConfig(table)
                        else:
                            raise Exception("Table has different data structure: Missing column %s" % colName)
                    specType = ts[colName]
                    if specType.lower() != colType.lower():  ## type names are case-insensitive too
                        ## requested column type does not match schema; check for directory / file types
                        if (colType == 'file' or colType.startswith('directory')):
                            if (colName in config and config[colName].get('Type',None) == colType):
                                continue
                        raise Exception("Table has different data structure: Column '%s' type is %s, should be %s" % (colName, specType, colType))

            if create is True and indexes is not None:
                for index in indexes:
                    self.createIndex(table, index, ifNotExist=True)   
        
        return True

    def createDirTable(self, dirHandle):
        """Creates a new table for storing directories similar to dirHandle"""
        
        with self.transaction():
            ## Ask manager what columns we think should go with this directory
            columns = list(acq4.Manager.getManager().suggestedDirFields(dirHandle).keys())
            
            ## Add in any other columns present
            #for k in dirHandle.info():   ## Let's leave it to the user to add these if they want
                #if k not in columns:
                    #columns.append(k)
            columns = [(k, 'text') for k in columns]
            columns = [('Dir', 'file')] + columns
            
            tableName = self.dirTableName(dirHandle)
            if self.hasTable(tableName):
                raise Exception('Can not add directory table "%s"; table already exists.' % tableName)
            
            ## Link this table to its parent
            parent = dirHandle.parent()
            if parent.isManaged() and parent is not self.baseDir():
                pType = self.dataModel().dirType(parent)
                pType = "" if pType is None else pType
                colName = pType + "Dir"
                columns = [(colName, 'directory:'+pType)] + columns
                #self.linkTables(tableName, colName, pName)
            
            dirType = self.dataModel().dirType(dirHandle)
            self.createTable(tableName, columns, dirType=dirType)
        
        return tableName
    
    def addDir(self, handle):
        """Create a record based on a DirHandle and its meta-info."""
        info = handle.info().deepcopy()
        for k in info:  ## replace tuple keys with strings
            if isinstance(k, tuple):
                n = "_".join(k)
                info[n] = info[k]
                del info[k]
        
        with self.transaction():
            table = self.dirTableName(handle)
            if not self.hasTable(table):
                self.createDirTable(handle)
            
            ## make sure dir is not already in DB.
            ## if it is, just return the row ID
            rid = self.getDirRowID(handle)
            if rid is not None:
                return table, rid
            
            ## find all directory columns, make sure linked directories are present in DB
            conf = self.getColumnConfig(table)
            for colName, col in conf.items():
                if col['Type'].startswith('directory'):
                    #pTable = col['Link']
                    pType = col['Type'].lstrip('directory:')
                    parent = self.dataModel().getParent(handle, pType)
                    if parent is not None:
                        self.addDir(parent)
                        info[colName] = parent
                    else:
                        info[colName] = None
            
            info['Dir'] = handle
            
            self.insert(table, info, ignoreExtraColumns=True)
            
            return table, self.lastInsertRow()


    def createView(self, viewName, tables):
        """Create a view that joins the tables listed."""
        # db('create view "sites" as select * from photostim_sites inner join DirTable_Protocol on photostim_sites.ProtocolDir=DirTable_Protocol.rowid inner join DirTable_Cell on DirTable_Protocol.CellDir=DirTable_Cell.rowid')

        with self.transaction():
            sel = self.makeJoinStatement(tables)
            cmd = 'create view "%s" as select * from %s' % (viewName, sel)
            #for i in range(1,len(tables)):  ## figure out how to join each table one at a time
                #nextTable = tables[i]
                
                #cols = None
                #for joinTable in tables[:i]:
                    #cols = self.findJoinColumns(nextTable, joinTable)
                    #if cols is not None:
                        #break
                        
                #if cols is None:
                    #raise Exception("Could not find criteria to join table '%s' to any of '%s'" % (joinTable, str(tables[:i])) )
                
                #cmd += ' inner join "%s" on "%s"."%s"="%s"."%s"' % (nextTable, nextTable, cols[0], joinTable, cols[1])
            
            self(cmd)
            
            ## Create column config records for this view
            colNames = list(self.tableSchema(viewName).keys())
            colDesc = []
            colIndex = 0
            for table in tables:
                cols = self.getColumnConfig(table)
                for col, config in cols.items():
                    config = config.copy()
                    config['Column'] = colNames[colIndex]
                    config['Table'] = viewName
                    colDesc.append(config)
                    colIndex += 1
            self.insert('ColumnConfig', colDesc)
    
    def makeJoinStatement(self, tables):
        ### construct an expresion that joins multiple tables automatically
        cmd = '"%s"' % tables[0]
        for i in range(1,len(tables)):  ## figure out how to join each table one at a time
            nextTable = tables[i]
            
            cols = None
            for joinTable in tables[:i]:
                cols = self.findJoinColumns(nextTable, joinTable)
                if cols is not None:
                    break
                    
            if cols is None:
                raise Exception("Could not find criteria to join table '%s' to any of '%s'" % (joinTable, str(tables[:i])) )
            
            cmd += ' inner join "%s" on "%s"."%s"="%s"."%s"' % (nextTable, nextTable, cols[0], joinTable, cols[1])
        return cmd
    
    def findJoinColumns(self, t1, t2):
        """Return the column names that can be used to join two tables.
        If no relationships are found, return None.
        """
        def strlower(x):  # convert strings to lower, everything else stays the same
            if isinstance(x, six.string_types):
                return x.lower()
            return x
            
        links1 = [(strlower(x['Column']), strlower(x['Link'])) for x in self.getColumnConfig(t1).values()]
        links2 = [(strlower(x['Column']), strlower(x['Link'])) for x in self.getColumnConfig(t2).values()]

        for col, link in links1:   ## t1 explicity links to t2.rowid
            if link == t2.lower():
                return col, 'rowid'
        for col, link in links2:   ## t2 explicitly links to t1.rowid
            if link == t1.lower():
                return 'rowid', col
        for col1, link1 in links1:   ## t1 and t2 both link to the same table.rowid
            for col2, link2 in links2:
                if link1 is not None and link1 == link2:
                    return col1, col2
                   
        return None  ## no links found
    
    

    #def linkTables(self, table1, col, table2):
        #"""Declare a key relationship between two tables. Values in table1.column are ROWIDs from table 2"""
        ##self.insert('TableRelationships', Table1=table1, Column=col, Table2=table2)
        #self.insert('TableConfig', Table=table1, Column=col, Key='link', Value=table2)
        #if table1 in self.columnConfigCache:
            #del self.columnConfigCache[table1]


    #def listTableLinks(self, table):
        #"""
        #List all declared relationships for table.
        #returns {columnName: linkedTable, ...}
        #"""
        #links = self.select('TableConfig', ['Column', 'Value'], sql="where \"Table\"='%s' and Key='link'" % table)
        #return dict([(link['Column'], link['Value']) for link in links])

    def getColumnConfig(self, table):
        """Return the column config records for table.
        Records are returned as {columnName: {'Type': t, 'Constraints': c, 'Link': l), ...}
        (Note this is not the same as tableSchema)
        """
        if table not in self.columnConfigCache:
            if not self.hasTable('ColumnConfig'):
                return {}
            recs = SqliteDatabase.select(self, 'ColumnConfig', ['Column', 'Type', 'Constraints', 'Link'], sql="where lower(\"Table\")=lower('%s') order by rowid" % table)
            if len(recs) == 0:
                return {}
            
            self.columnConfigCache[table] = collections.OrderedDict([(r['Column'], r) for r in recs])
        return self.columnConfigCache[table]
        
    def getTableConfig(self, table):
        if self.tableConfigCache is None:
            recs = SqliteDatabase.select(self, 'TableConfig')
            self.tableConfigCache = advancedTypes.CaselessDict()
            for rec in recs:
                self.tableConfigCache[rec['Table']] = rec
        #recs = self.select('TableConfig', sql="where \"Table\"='%s'" % table)
        
        if table not in self.tableConfigCache:
            raise Exception('No config record for table "%s"' % table)
        return self.tableConfigCache[table]


    def getDirRowID(self, dirHandle):
        table = self.dirTableName(dirHandle)
            
        if not self.hasTable(table):
            return None
        name = dirHandle.name(relativeTo=self.baseDir())
        name1 = name.replace('/', '\\')
        name2 = name.replace('\\', '/')
        rec = self.select(table, ['rowid'], sql="where Dir='%s' or Dir='%s'" % (name1, name2))
        if len(rec) < 1:
            return None
        #print rec[0]
        return rec[0]['rowid']

    def getDir(self, table, rowid):
        ## Return a DirHandle given table, rowid
        res = self.select(table, ['Dir'], sql='where rowid=%d'%rowid)
        if len(res) < 1:
            raise Exception('rowid %d does not exist in %s' % (rowid, table)) 
            #logMsg('rowid %d does not exist in %s' % (rowid, table), msgType='error') ### This needs to be caught further up in Photostim or somewhere, not here -- really this shouldn't be caught at all since it means something is wrong with the db
            #return None
        #print res
        #return self.baseDir()[res[0]['Dir']]
        return res[0]['Dir']

    def dirTableName(self, dh):
        """Return the name of the directory table that should hold dh.
        dh may be either a directory handle OR the string result of self.dataModel().dirType(dh)
        """
        if isinstance(dh, DataManager.DirHandle):
            typeName = self.dataModel().dirType(dh)
        elif isinstance(dh, six.string_types):
            typeName = dh
        else:
            raise TypeError(type(dh))
        return "DirTable_" + typeName


    #def dirTypeName(self, dh):
        #info = dh.info()
        #type = info.get('dirType', None)
        #if type is None:
            #if 'protocol' in info:
                #if 'sequenceParams' in info:
                    #type = 'ProtocolSequence'  
                #else:
                    #type = 'Protocol'  ## an individual protocol run, NOT a single run from within a sequence
            #else:
                #try:
                    #if self.dirTypeName(dh.parent()) == 'ProtocolSequence':
                        #type = 'Protocol'
                    #else:
                        #raise Exception()
                #except:
                    #raise Exception("Can't determine type for dir %s" % dh.name())
        #return type

    def listTablesOwned(self, owner):
        res = self.select('TableConfig', ['Table'], sql="where Owner='%s'" % owner)
        return [x['Table'] for x in res]
    
    ## deprecated--use createTable() with owner specified instead.
    #def takeOwnership(self, table, owner):
        #self.insert("DataTableOwners", {'Table': table, "Owner": owner})
    
    def tableOwner(self, table):
        #res = self.select("DataTableOwners", ["Owner"], sql='where "Table"=\'%s\'' % table)
        res = self.select('TableConfig', ['Owner'], sql="where \"Table\"='%s'" % table)
        if len(res) == 0:
            return None
        return res[0]['Owner']

    def describeData(self, data):
        """Given a dict or record array, return a table description suitable for creating / checking tables."""
        columns = collections.OrderedDict()
        if isinstance(data, list):  ## list of dicts is ok
            data = data[0]
            
        if isinstance(data, np.ndarray):
            for i in range(len(data.dtype)):
                name = data.dtype.names[i]
                typ = data.dtype[i].kind
                if typ == 'i':
                    typ = 'int'
                elif typ == 'f':
                    typ = 'real'
                elif typ == 'S':
                    typ = 'text'
                else:
                    if typ == 'O': ## check to see if this is a pointer to a string
                        allStr = 0
                        allHandle = 0
                        for i in range(len(data)):
                            val = data[i][name]
                            if val is None or isinstance(val, six.string_types):
                                allStr += 1
                            elif val is None or isinstance(val, DataManager.FileHandle):
                                allHandle += 1
                        if allStr == len(data):
                            typ = 'text'
                        elif allHandle == len(data):
                            typ = 'file'
                    else:
                        typ = 'blob'
                columns[name] = typ
        elif isinstance(data, dict):
            for name, v in data.items():
                if functions.isFloat(v):
                    typ = 'real'
                elif functions.isInt(v):
                    typ = 'int'
                elif isinstance(v, six.string_types):
                    typ = 'text'
                elif isinstance(v, DataManager.FileHandle):
                    typ = 'file'
                else:
                    typ = 'blob'
                columns[name] = typ
        else:
            raise Exception("Can not describe data of type '%s'" % type(data))
        return columns

    def select(self, table, columns='*', where=None, sql='', toDict=True, toArray=False, distinct=False, limit=None, offset=None):
        """Extends select to convert directory/file columns back into Dir/FileHandles. If the file doesn't exist, you will still get a handle, but it may not be the correct type."""
        prof = debug.Profiler("AnalysisDatabase.select()", disabled=True)
        
        data = SqliteDatabase.select(self, table, columns, where=where, sql=sql, distinct=distinct, limit=limit, offset=offset, toDict=True, toArray=False)
        data = TableData(data)
        prof.mark("got data from SQliteDatabase")
        
        config = self.getColumnConfig(table)
        
        ## convert file/dir handles
        for column, conf in config.items():
            if column not in data.columnNames():
                continue
            
            if conf.get('Type', '').startswith('directory'):
                rids = set([d[column] for d in data])
                linkTable = conf['Link']
                handles = dict([(rid, self.getDir(linkTable, rid)) for rid in rids if rid is not None])
                handles[None] = None
                data[column] = list(map(handles.get, data[column]))
                    
            elif conf.get('Type', None) == 'file':
                def getHandle(name):
                    if name is None:
                        return None
                    else:
                        if os.sep == '/':
                            sep = '\\'
                        else:
                            sep = '/'
                        name = name.replace(sep, os.sep) ## make sure file handles have an operating-system-appropriate separator (/ for Unix, \ for Windows)
                        return self.baseDir()[name]
                data[column] = list(map(getHandle, data[column]))
                
        prof.mark("converted file/dir handles")
                
        ret = data.originalData()
        if toArray:
            ret = data.toArray()
            prof.mark("converted data to array")
        prof.finish()
        return ret
    
    def _prepareData(self, table, data, ignoreUnknownColumns=False, batch=False):
        """
        Extends SqliteDatabase._prepareData():
            - converts DirHandles to the correct rowid for any linked columns
              (and automatically adds directories to their tables if needed)
            - converts filehandles to a string file name relative to the DB base dir.
        """
        #if batch is False:
            #raise Exception("AnalysisDatabase only implements batch mode.")

        #links = self.listTableLinks(table)
        config = self.getColumnConfig(table)
        
        data = TableData(data).copy()  ## have to copy here since we might be changing some values
        dataCols = set(data.columnNames())
        for colName, colConf in config.items():
            if colName not in dataCols:
                continue
            
            if colConf.get('Type', '').startswith('directory'):
                ## Make sure all directories are present in the DB
                handles = data[colName]
                linkTable = colConf['Link']
                if linkTable is None:
                    raise Exception('Column "%s" is type "%s" but is not linked to any table.' % (colName, colConf['Type']))
                rowids = {None: None}
                for dh in set(handles):
                    if dh is None:
                        continue
                    dirTable, rid = self.addDir(dh)
                    if dirTable != linkTable:
                        linkType = self.getTableConfig(linkTable)['DirType']
                        dirType = self.getTableConfig(dirTable)['DirType']
                        raise Exception("Trying to use directory '%s' (type='%s') for column %s.%s, but this column is for directories of type '%s'." % (dh.name(), dirType, table, colName, linkType))
                    rowids[dh] = rid
                    
                ## convert dirhandles to rowids
                data[colName] = list(map(rowids.get, handles))
            elif colConf.get('Type', None) == 'file':
                ## convert filehandles to strings
                files = []
                for f in data[colName]:
                    if f is None:
                        files.append(None)
                    else:
                        try:
                            files.append(f.name(relativeTo=self.baseDir()))
                        except:
                            print("f:", f)
                            raise
                data[colName] = files

        newData = SqliteDatabase._prepareData(self, table, data, ignoreUnknownColumns, batch)
        
        return newData
        
        
        
        
