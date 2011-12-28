# -*- coding: utf-8 -*-
if __name__ == '__main__':
    import os, sys
    path = os.path.dirname(os.path.abspath(__file__))
    sys.path.append(os.path.join(path, '..', '..'))

from PyQt4 import QtSql, QtCore
## Results from DB operations may vary depending on the API version in use.
if hasattr(QtCore, 'QVariant'):
    HAVE_QVARIANT = True
else:
    HAVE_QVARIANT = False


import numpy as np
import pickle, re, os
import DataManager, lib.Manager
import collections
import functions
import advancedTypes
import debug

def quoteList(strns):
    """Given a list of strings, return a single string like '"string1", "string2",...'
        Note: in SQLite, double quotes are for escaping table and column names; 
              single quotes are for string literals.
    """
    return ','.join(['"'+s+'"' for s in strns])


class SqliteDatabase:
    """Encapsulates an SQLITE database through QtSql to make things a bit more pythonic.
    Arbitrary SQL may be executed by calling the db object directly, eg: db('select * from table')
    Using the select() and insert() methods will do automatic type conversions and allows
    any picklable objects to be directly stored in BLOB type columns. (it is not necessarily
    safe to store pickled objects in TEXT columns)
    
    NOTE: Data types in SQLITE work differently than in most other DBs--each value may take any type
    regardless of the type specified by its column.
    """
    def __init__(self, fileName=':memory:'):
        self.db = QtSql.QSqlDatabase.addDatabase("QSQLITE")
        self.db.setDatabaseName(fileName)
        self.db.open()
        self.tables = {}
        self._readTableList()
        
    def close(self):
        self.db.close()

    def exe(self, cmd, data=None, batch=False, toDict=True, toArray=False):
        """Execute an SQL query. If data is provided, it should be a list of dicts and each will 
        be bound to the query and executed sequentially. Returns the query object.
        Arguments:
            cmd     - The SQL query to execute
            data    - List of dicts, one per record to be processed
                      For each record, data is bound to the query by key name
                      {"key1": "value1"}  =>  ":key1"="value1"
            batch   - If True, then all input data is processed in a single execution.
                      In this case, data must be provided as a dict-of-lists or record array.
            toDict  - If True, return a list-of-dicts representation of the query results
            toArray - If True, return a record array representation of the query results
        """
        p = debug.Profiler('SqliteDatabase.exe', disabled=True)
        p.mark('Command: %s' % cmd)
        q = QtSql.QSqlQuery(self.db)
        if data is None:
            self._exe(q, cmd)
            p.mark("Executed with no data")
        else:
            data = TableData(data)
            res = []
            if not q.prepare(cmd):
                print "SQL Query:\n    %s" % cmd
                raise Exception("Error preparing SQL query (query is printed above): %s" % str(q.lastError().text()))
            p.mark("Prepared query")
            if batch:
                for k in data.columnNames():
                    q.bindValue(':'+k, data[k])
                self._exe(q, batch=True)
                    
            else:
                for d in data:
                    #print len(d)
                    for k, v in d.iteritems():
                        q.bindValue(':'+k, v)
                        #print k, v, type(v)
                    p.mark("bound values for record")
                    #print "==execute with bound data=="
                    #print cmd
                    #print q.boundValues()
                    #for k, v in q.boundValues().iteritems():
                        #print str(k), v.typeName()
                    self._exe(q)
                    p.mark("executed with data")
                
        if toArray:
            ret = self._queryToArray(q)
        elif toDict:
            ret = self._queryToDict(q)
        else:
            ret = q
        p.finish("Generated result")
        return ret
            
    def __call__(self, *args, **kargs):
        return self.exe(*args, **kargs)
            
    def select(self, table, columns='*', sql='', toDict=True, toArray=False):
        """columns should be a list of column names"""
        p = debug.Profiler("SqliteDatabase.select", disabled=True)
        if columns != '*':
            if isinstance(columns, basestring):
                columns = columns.split(',')
            qf = []
            for f in columns:
                if f == '*':
                    qf.append(f)
                else:
                    qf.append('"'+f+'"')
            columns = ','.join(qf)
            #columns = quoteList(columns)
        cmd = "SELECT %s FROM %s %s" % (columns, table, sql)
        p.mark("generated command")
        q = self.exe(cmd, toDict=toDict, toArray=toArray)
        p.finish("Execution finished.")
        return q
        
    def insert(self, table, records=None, replaceOnConflict=False, ignoreExtraColumns=False, addExtraColumns=False, **args):
        """Insert records (a dict or list of dicts) into table.
        If records is None, a single record may be specified via keyword arguments.
        
        Arguments:
            ignoreExtraColumns:  If True, ignore any extra columns in the data that do not exist in the table
            addExtraColumns:   If True, add any columns that exist in the data but do not yet exist in the table
                              (NOT IMPLEMENTED YET)
        """
        
        ## can we optimize this by using batch execution?
        
        p = debug.Profiler("SqliteDatabase.insert", disabled=True)
        if records is None:
            records = [args]
        if type(records) is not list:
            records = [records]
        if len(records) == 0:
            return
        ret = []
            
        ## Rememember that _prepareData may change the number of columns!
        records = self._prepareData(table, records, removeUnknownColumns=ignoreExtraColumns, batch=True)
        p.mark("prepared data")
        
        columns = records.keys()
        insert = "INSERT"
        if replaceOnConflict:
            insert += " OR REPLACE"
        #print "Insert:", columns
        cmd = "%s INTO %s (%s) VALUES (%s)" % (insert, table, quoteList(columns), ','.join([':'+f for f in columns]))
        
        #print len(columns), len(records[0]), len(self.tableSchema(table))
        self.exe(cmd, records, batch=True)
        p.finish("Executed.")

    def delete(self, table, where):
        cmd = "DELETE FROM %s WHERE %s" % (table, where)
        return self(cmd)

    def update(self, table, vals, where=None, rowid=None):
        """Update records in the DB.
        Arguments:
            vals: dict of {column: value} pairs
            where: SQL clause specifying rows to update
            rowid: int row IDs. Used instead of 'where'"""
        if where is None:
            if rowid is None:
                raise Exception("Must specify 'where' or 'rowids'")
            else:
                where = "rowid=%d" % rowid
        setStr = ', '.join(['"%s"=:%s' % (k, k) for k in vals])
        data = self._prepareData(table, [vals], batch=True)
        cmd = "UPDATE %s SET %s WHERE %s" % (table, setStr, where)
        return self(cmd, data, batch=True)

    def lastInsertRow(self):
        q = self("select last_insert_rowid()")
        return q[0].values()[0]

    def replace(self, *args, **kargs):
        return self.insert(*args, replaceOnConflict=True, **kargs)

    def createTable(self, table, columns, sql=""):
        """Create a table in the database.
          table: (str) the name of the table to create
          columns: (list) a list of tuples (name, type, constraints) defining columns in the table. 
                   all 3 elements othe tuple are strings; constraints are optional. 
                   Types may be any string, but are typically int, real, text, or blob.
        """
        #print "create table", table, ', '.join(columns)
        columnStr = []
        for col in columns:
            if len(col) == 2:
                columnStr.append('"%s" %s' % col)
            elif len(col) == 3:
                columnStr.append('"%s" %s %s' % col)
        columnStr = ','.join(columnStr)

        self('CREATE TABLE %s (%s) %s' % (table, columnStr, sql))
        self._readTableList()
 
    def listTables(self):
        return self.tables.keys()
 
    def removeTable(self, table):
        self('DROP TABLE "%s"' % table)

    def hasTable(self, table):
        return table in self.tables  ## this is a case-insensitive operation
    
    def tableSchema(self, table):
        return self.tables[table]  ## this is a case-insensitive operation
    
    def _exe(self, query, cmd=None, batch=False):
        """Execute an SQL query, raising an exception if there was an error. (internal use only)"""
        if batch:
            fn = query.execBatch
        else:
            fn = query.exec_
            
        if cmd is None:
            ret = fn()
        else:
            ret = fn(cmd)
        if not ret:
            if cmd is not None:
                print "SQL Query:\n    %s" % cmd
                raise Exception("Error executing SQL (query is printed above): %s" % str(query.lastError().text()))
            else:
                raise Exception("Error executing SQL: %s" % str(query.lastError().text()))
                
        if str(query.executedQuery())[:6].lower() == 'create':
            self._readTableList()
    
    
    def _prepareData(self, table, data, removeUnknownColumns=False, converters=None, batch=False):
        ## Massage data so it is ready for insert into the DB. (internal use only)
        ##   - data destined for BLOB columns is pickled
        ##   - numerical columns convert to int or float
        ##   - text columns convert to unicode
        ## converters may be a dict of {'columnName': function} 
        ## that overrides the default conversion funcitons.
        
        ## Returns a TableData object
        
        
        data = TableData(data)
        
        if converters is not None:
            converters = {}
            
        ## determine the conversion functions to use for each column.
        schema = self.tableSchema(table)
        for k in schema:
            if k in converters:
                continue
            
            typ = schema[k].lower()
            if typ == 'blob':
                converters[k] = lambda obj: QtCore.QByteArray(pickle.dumps(obj))
            elif typ == 'int':
                converters[k] = int
            elif typ == 'real':
                converters[k] = float
            elif typ == 'text':
                converters[k] = str
            else:
                converters[k] = lambda obj: obj
                
        if batch:
            newData = dict([(k,[]) for k in data[0] if not (removeUnknownColumns and (k not in schema))])
        else:
            newData = []
            
        for rec in data:
            newRec = {}
            for k in rec:
                if removeUnknownColumns and (k not in schema):
                    continue
                
                try:
                    newRec[k] = converters[k](rec[k])
                except:
                    newRec[k] = rec[k]
                    if k.lower() != 'rowid':
                        if k not in schema:
                            raise Exception("Column '%s' not present in table '%s'" % (k, table))
                        print "Warning: Setting %s column %s.%s with type %s" % (schema[k], table, k, str(type(rec[k])))
            if batch:
                for k in newData:
                    newData[k].append(newRec.get(k, None))
            else:
                newData.append(newRec)
        #print "new data:", newData
        return newData

    def _queryToDict(self, q):
        res = []
        while q.next():
            res.append(self._readRecord(q.record()))
        return res


    def _queryToArray(self, q):
        recs = self._queryToDict(q)
        if len(recs) < 1:
            #return np.array([])  ## need to return empty array *with correct columns*, but this is very difficult, so just return None
            return None
        rec1 = recs[0]
        dtype = functions.suggestRecordDType(rec1)
        #print rec1, dtype
        arr = np.empty(len(recs), dtype=dtype)
        arr[0] = tuple(rec1.values())
        for i in xrange(1, len(recs)):
            arr[i] = tuple(recs[i].values())
        return arr


    def _readRecord(self, rec):
        data = collections.OrderedDict()
        for i in range(rec.count()):
            f = rec.field(i)
            n = str(f.name())
            if rec.isNull(i):
                val = None
            else:
                val = rec.value(i)
                ## If we are using API 1 for QVariant (ie not PySide)
                ## then val is a QVariant and must be coerced back to a python type
                if HAVE_QVARIANT and isinstance(val, QtCore.QVariant):
                    t = val.type()
                    if t in [QtCore.QVariant.Int, QtCore.QVariant.LongLong]:
                        val = val.toInt()[0]
                    if t in [QtCore.QVariant.Double]:
                        val = val.toDouble()[0]
                    elif t == QtCore.QVariant.String:
                        val = unicode(val.toString())
                    elif t == QtCore.QVariant.ByteArray:
                        val = val.toByteArray()
                        
                ## Unpickle byte arrays into their original objects.
                ## (Hopefully they were stored as pickled data in the first place!)
                if isinstance(val, QtCore.QByteArray):
                    val = pickle.loads(str(val))
            data[n] = val
        return data

    def _readTableList(self):
        """Reads the schema for each table, extracting the column names and types."""
        
        res = self.select('sqlite_master', ['name', 'sql'], "where type = 'table'")
        ident = r"(\w+|'[^']+'|\"[^\"]+\")"
        #print "READ:"
        tables = advancedTypes.CaselessDict()
        for rec in res:
            #print rec
            sql = rec['sql'].replace('\n', ' ')
            #print sql
            m = re.match(r"\s*create\s+table\s+%s\s*\(([^\)]+)\)" % ident, sql, re.I)
            #print m.groups()
            columnstr = m.groups()[1].split(',')
            columns = advancedTypes.CaselessDict()
            #print columnstr
            #print columnstr
            for f in columnstr:
                #print "   ", f
                m = re.findall(ident, f)
                #print "   ", m
                if len(m) < 2:
                    typ = ''
                else:
                    typ = m[1].strip('\'"')
                column = m[0].strip('\'"')
                columns[column] = typ
            tables[rec['name']] = columns
        self.tables = tables
        #print tables




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
        self.columnConfigCache = {}
        
        self.setDataModel(dataModel)
        self._baseDir = None
        if not os.path.exists(dbFile):
            create = True
            if baseDir is None:
                raise Exception("Must specify a base directory when creating a database.")

        #self.db = SqliteDatabase(dbFile)
        SqliteDatabase.__init__(self, dbFile)
        self.file = dbFile
        
        if create:
            self.initializeDb()
            self.setBaseDir(baseDir)
            self.setCtrlParam('DB Version', AnalysisDatabase.Version)
            self.setCtrlParam('Description', '')
            
        ver = self.ctrlParam('DB Version')
        if ver != AnalysisDatabase.Version:
            self._convertDB()
            
    def setDataModel(self, dm):
        self._dataModel = dm
        
    def dataModel(self):
        return self._dataModel
            
    def _convertDB(self):
        
        ver = self.ctrlParam('DB Version')
        
        if ver is None:  ## upgrade to version 1
            dirTypes = ['Day', 'Experiment', 'Slice', 'Cell', 'Site', 'Protocol', 'ProtocolSequence']
            params = self.select('DbParameters')
            self.removeTable('DbParameters')
            
            self.initializeDb()
            
            for rec in params:
                self.setCtrlParam(rec['Param'], rec['Value'])
            
            ## update all dir tables
            for dirType in dirTypes:
                if not self.hasTable(dirType):
                    continue
                newName = self.dirTableName(dirType)
                self.insert('TableConfig', Table=newName, DirType=dirType)
                
                ts = self.tableSchema(dirType)
                link = self.select('TableRelationships', ['Column', 'Table2'], 'where Table1="%s"' % dirType)[0]
                linkedType = link['Table2']
                
                ts[linkedType] = ('directory:%s' % linkedType)
                del ts[link['Column']]
                self.createTable(newName, ts.items())
                
                records = self.select(dirType)
                for rec in records:
                    rec[linkedType] = rec[link['Column']]
                    ## TODO: need to convert integers to handles here..
                    del rec[link['Column']]
                self.insert(newName, records)
                
                self.removeTable(dirType)
                
            
            
            #for link in self.select('TableRelationships'):
                #self.linkTables(link['Table1'], link['Column'], link['Table2'])
            self.removeTable('TableRelationships')
            
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
        res = SqliteDatabase.select(self, 'DbParameters', ['Value'], "where Param='%s'"%param)
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
        records = []
        colTuples = []
        for col in columns:
            if isinstance(col, dict):
                rec = col
            else:
                rec = dict(Column=col[0], Type=col[1])
                if len(col) > 2:
                    rec['Constraints'] = col[2]
                if len(col) > 3:
                    rec['Link'] = col[3]
                    
            rec['Table'] = table
            records.append(rec)
            typ = rec['Type']
            if typ.startswith('directory'):
                dirType = typ.lstrip('directory:')
                dirTable = self.dirTableName(dirType)
                rec['Link'] = dirTable
                typ = 'int'
            elif typ == 'file':
                typ = 'text'
            tup = (rec['Column'], typ)
            if 'Constraints' in rec:
                tup = tup + (rec['Constraints'],)
            colTuples.append(tup)
            
            
        ret = SqliteDatabase.createTable(self, table, colTuples, sql)
        
        self.insert('ColumnConfig', records)
        
        tableRec = dict(Table=table, Owner=owner, DirType=dirType)
        self.insert('TableConfig', tableRec)
        self.tableConfigCache = None
        
        return ret

    def checkTable(self, table, owner, columns, create=False):
        """
        Checks to be sure that a table has been created with the correct fields and ownership.
        This should generally be run before attempting to access a table.
        If the table does not exist and create==True, then the table will be created with the 
        given columns and owner. 
        """
        
        ## Make sure target table exists and has correct columns, links to input file
        if not self.hasTable(table):
            if create:
                ## create table
                self.createTable(table, columns, owner=owner)
                #for column, ptable in links:
                    #self.linkTables(table, column, ptable)
            else:
                raise Exception("Table %s does not exist." % table)
        else:
            ## check table for ownership, columns
            if self.tableOwner(table) != owner:
                raise Exception("Table %s is not owned by %s." % (table, owner))
            
            ts = self.tableSchema(table)
            config = self.getTableConfig(table)
            
            for colName, colType, extra in columns:
                if colName not in ts:  ## <-- this is a case-insensitive operation
                    raise Exception("Table has different data structure: Missing column %s" % f)
                specType = ts[colName]
                if specType.lower() != colType.lower():  ## type names are case-insensitive too
                    if colType.startswith('directory'):
                        dirType = colType.lstrip('directory:')
                        dirTable = self.dirTableName(dirType)
                        if (
                            specType == 'int' and 
                            colName in config and 
                            config[colName].get('type',None) == 'directory' and 
                            config[colName].get('link',None) == dirTable):
                            continue
                    elif columns[f] == 'file':
                        if ( 
                            specType == 'text' and
                            config[colName].get('type',None) == 'file'):
                            continue
                        pass
                    raise Exception("Table has different data structure: Column '%s' type is %s, should be %s" % (f, ts[f], columns[f]))
        return True

    def createDirTable(self, dirHandle):
        """Creates a new table for storing directories similar to dirHandle"""
        
        ## Ask manager what columns we think should go with this directory
        columns = lib.Manager.getManager().suggestedDirFields(dirHandle).keys()
        
        ## Add in any other columns present 
        for k in dirHandle.info():
            if k not in columns:
                columns.append(k)
        columns = [(k, 'text') for k in columns]
        columns = [('Dir', 'file')] + columns
        
        tableName = self.dirTableName(dirHandle)
        if self.hasTable(tableName):
            raise Exception('Can not add directory table "%s"; table already exists.' % tableName)
        
        ## Link this table to its parent
        parent = dirHandle.parent()
        if parent.isManaged() and parent is not self.baseDir():
            pType = self.dataModel().dirType(parent)
            colName = pType + "Dir"
            columns = [(colName, 'directory:'+pType)] + columns
            #self.linkTables(tableName, colName, pName)
            
        self.createTable(tableName, columns)
        return tableName

    def addDir(self, handle):
        """Create a record based on a DirHandle and its meta-info."""
        info = handle.info().deepcopy()
        for k in info:  ## replace tuple keys with strings
            if isinstance(k, tuple):
                n = "_".join(k)
                info[n] = info[k]
                del info[k]
        
        ### determine parent directory, make sure parent is in DB.
        #parent = handle.parent()
        #parentRowId = None
        #if parent.isManaged() and parent is not self.baseDir():
            #pTable, parentRowId = self.addDir(parent)
            
        table = self.dirTableName(handle)
        if not self.hasTable(table):
            self.createDirTable(handle)
            
        ## find all directory columns, make sure linked directories are present in DB
        conf = self.getColumnConfig(table)
        for col in conf:
            if col['Type'].startswith('directory'):
                #pTable = col['Link']
                pType = col['Type'].lstrip('directory:')
                parent = self.dataModel().getParent(handle, pType)
                if parent is not None:
                    self.addDir(parent)
                    info[col['Column']] = parent
                else:
                    info[col['Column']] = None
        
        ## make sure dir is not already in DB. 
        ## if it is, just return the row ID
        rid = self.getDirRowID(handle)
        if rid is not None:
            return table, rid
            
        #if parentRowId is not None:
            #pType = self.getTableConfig(pTable)['DirType']
            #info[pType+'Dir'] = parentRowId
        info['Dir'] = handle.name(relativeTo=self.baseDir())
        
        self.insert(table, info, ignoreExtraColumns=True)

        return table, self.lastInsertRow()



    def linkTables(self, table1, col, table2):
        """Declare a key relationship between two tables. Values in table1.column are ROWIDs from table 2"""
        #self.insert('TableRelationships', Table1=table1, Column=col, Table2=table2)
        self.insert('TableConfig', Table=table1, Column=col, Key='link', Value=table2)
        if table1 in self.columnConfigCache:
            del self.columnConfigCache[table1]


    def listTableLinks(self, table):
        """
        List all declared relationships for table.
        returns {columnName: linkedTable, ...}
        """
        links = self.select('TableConfig', ['Column', 'Value'], "where \"Table\"='%s' and Key='link'" % table)
        return dict([(link['Column'], link['Value']) for link in links])

    def getColumnConfig(self, table):
        """Return the column config records for table."""
        if table not in self.columnConfigCache:
            if not self.hasTable('ColumnConfig'):
                return []
            recs = SqliteDatabase.select(self, 'ColumnConfig', ['Column', 'Type', 'Constraints', 'Link'], "where \"Table\"='%s'" % table)
            if len(recs) == 0:
                return []
            self.columnConfigCache[table] = recs
        return self.columnConfigCache[table]
        
    def getTableConfig(self, table):
        if self.tableConfigCache is None:
            recs = SqliteDatabase.select(self, 'TableConfig')
            self.tableConfigCache = {}
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
        rec = self.select(table, ['rowid'], "where Dir='%s'" % dirHandle.name(relativeTo=self.baseDir()))
        if len(rec) < 1:
            return None
        #print rec[0]
        return rec[0]['rowid']

    def getDir(self, table, rowid):
        ## Return a DirHandle given table, rowid
        res = self.select(table, ['Dir'], 'where rowid=%d'%rowid)
        if len(res) < 1:
            raise Exception('rowid %d does not exist in %s' % (rowid, table))
        #print res
        #return self.baseDir()[res[0]['Dir']]
        return res[0]['Dir']

    def dirTableName(self, dh):
        """Return the name of the directory table that should hold dh.
        dh may be either a directory handle OR the string result of self.dataModel().dirType(dh)
        """
        if isinstance(dh, DataManager.DirHandle):
            typeName = self.dataModel().dirType(dh)
        elif isinstance(dh, basestring):
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
        res = self.select('TableConfig', ['Table'], "where Owner='%s'" % owner)
        return [x['Table'] for x in res]
    
    ## deprecated--use createTable() with owner specified instead.
    #def takeOwnership(self, table, owner):
        #self.insert("DataTableOwners", {'Table': table, "Owner": owner})
    
    def tableOwner(self, table):
        #res = self.select("DataTableOwners", ["Owner"], sql='where "Table"=\'%s\'' % table)
        res = self.select('TableConfig', ['Owner'], "where \"Table\"='%s'" % table)
        if len(res) == 0:
            return None
        return res[0]['Owner']

    def describeData(self, data):
        """Given a dict or record array, return a table description suitable for creating / checking tables."""
        columns = collections.OrderedDict()
        if isinstance(data, list):  ## list of dicts is ok
            data = data[0]
            
        if isinstance(data, np.ndarray):
            for i in xrange(len(data.dtype)):
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
                        for i in xrange(len(data)):
                            if isinstance(data[i][name], basestring):
                                allStr += 1
                        if allStr == len(data):
                            typ = 'text'
                    else:
                        typ = 'blob'
                columns[name] = typ
        elif isinstance(data, dict):
            for name, v in data.iteritems():
                if functions.isFloat(v):
                    typ = 'real'
                elif functions.isInt(v):
                    typ = 'int'
                elif isinstance(v, basestring):
                    typ = 'text'
                else:
                    typ = 'blob'
                columns[name] = typ
        else:
            raise Exception("Can not describe data of type '%s'" % type(data))
        return columns

    def select(self, table, columns='*', sql='', toDict=True, toArray=False):
        """Extends select to convert directory/file columns back into Dir/FileHandles"""
        
        
        data = SqliteDatabase.select(self, table, columns, sql, toDict=toDict, toArray=toArray)
        data = TableData(data)
        
        config = self.getColumnConfig(table)
        
        ## convert file/dir handles
        for conf in config:
            column = conf['Column']
            if column not in data.columnNames():
                continue
            
            if conf.get('Type', '').startswith('directory'):
                rids = set([d[column] for d in data])
                linkTable = conf['Link']
                handles = dict([(rid, self.getDir(linkTable, rid)) for rid in rids])
                data[column] = map(handles.get, data[column])
                    
            elif conf.get('Type', None) == 'file':
                data[column] = map(self.baseDir().__getitem__, data[column])
        
        return data.originalData()
    
    def _prepareData(self, table, data, removeUnknownColumns=False, batch=False):
        """
        Extends SqliteDatabase._prepareData():
            - converts DirHandles to the correct rowid for any linked columns
              (and automatically adds directories to their tables if needed)
            - converts filehandles to a string file name relative to the DB base dir.
        """
        if batch is False:
            raise Exception("AnalysisDatabase only implements batch mode.")

        #links = self.listTableLinks(table)
        config = self.getColumnConfig(table)
        
        data = TableData(data)
        dataCols = set(data.columnNames())
        
        for col in config:
            column = col['Column']
            if column not in dataCols:
                continue
            
            if col.get('Type', '').startswith('directory'):
                ## Make sure all directories are present in the DB
                handles = data[column]
                linkTable = col['Link']
                rowids = {}
                for dh in set(handles):
                    dirTable, rid = self.addDir(dh)
                    if dirTable != linkTable:
                        linkType = self.getTableConfig(linkTable)['DirType']
                        dirType = self.getTableConfig(dirTable)['DirType']
                        raise Exception("Trying to add directory '%s' (type='%s') to column %s.%s, but this column is for directories of type '%s'." % (dh.name(), dirType, table, column, linkType))
                    rowids[dh] = rid
                    
                ## convert dirhandles to rowids
                data[column] = map(rowids.get, handles)
            elif col.get('type', None) == 'file':
                ## convert filehandles to strings
                data[column] = map(lambda fh: fh.name(relativeTo=self.baseDir()), data['column'])

        newData = SqliteDatabase._prepareData(self, table, data, removeUnknownColumns, batch)
        
        return data
        
        
        
        
        
class TableData:
    """
    Class for presenting multiple forms of tabular data through a consistent interface.
    May contain:
        - numpy record array
        - list-of-dicts (all dicts are _not_ required to have the same keys)
        - dict-of-lists
        
    Data can be accessed and modified by column, by row, or by value
        data[columnName]
        data[rowId]
        data[columnName, rowId] = value
        data[columnName] = [value, value, ...]
        data[rowId] = {columnName: value, ...}
    """
    
    def __init__(self, data):
        self.data = data
        if isinstance(data, np.ndarray):
            self.mode = 'array'
        elif isinstance(data, list):
            self.mode = 'list'
        elif isinstance(data, dict):
            self.mode = 'dict'
        elif isinstance(data, TableData):
            self.data = data.data
            self.mode = data.mode
        else:
            raise TypeError(type(data))
        
        for fn in ['__getitem__', '__setitem__']:
            setattr(self, fn, getattr(self, '_TableData'+fn+self.mode))
        
    def originalData(self):
        return self.data
            
    def __getitem__array(self, arg):
        if isinstance(arg, tuple):
            return self.data[arg[0]][arg[1]]
        else:
            return self.data[arg]
            
    def __getitem__list(self, arg):
        if isinstance(arg, basestring):
            return [d.get(arg, None) for d in self.data]
        elif isinstance(arg, int):
            return self.data[arg]
        elif isinstance(arg, tuple):
            arg = self._orderArgs(arg)
            return self.data[arg[0]][arg[1]]
        else:
            raise TypeError(type(arg))
        
    def __getitem__dict(self, arg):
        if isinstance(arg, basestring):
            return self.data[arg]
        elif isinstance(arg, int):
            return dict([(k, v[arg]) for k, v in self.data.iteritems()])
        elif isinstance(arg, tuple):
            arg = self._orderArgs(arg)
            return self.data[arg[1]][arg[0]]
        else:
            raise TypeError(type(arg))

    def __setitem__array(self, arg, val):
        if isinstance(arg, tuple):
            self.data[arg[0]][arg[1]] = val
        else:
            self.data[arg] = val

    def __setitem__list(self, arg, val):
        if isinstance(arg, basestring):
            if len(val) != len(self.data):
                raise Exception("Values (%d) and data set (%d) are not the same length." % (len(val), len(self.data)))
            for i, rec in enumerate(self.data):
                rec[arg] = val[i]
        elif isinstance(arg, int):
            self.data[arg] = val
        elif isinstance(arg, tuple):
            arg = self._orderArgs(arg)
            self.data[arg[0]][arg[1]] = val
        else:
            raise TypeError(type(arg))
        
    def __setitem__dict(self, arg, val):
        if isinstance(arg, basestring):
            if len(val) != len(self.data[arg]):
                raise Exception("Values (%d) and data set (%d) are not the same length." % (len(val), len(self.data[arg])))
            self.data[arg] = val
        elif isinstance(arg, int):
            for k in self.data:
                self.data[k][arg] = val[k]
        elif isinstance(arg, tuple):
            arg = self._orderArgs(arg)
            self.data[arg[1]][arg[0]] = val
        else:
            raise TypeError(type(arg))

    def _orderArgs(self, args):
        ## return args in (int, str) order
        if isinstance(args[0], basestring):
            return (args[1], args[0])
        else:
            return args
        
    def __iter__(self):
        for i in xrange(len(self)):
            yield self[i]

    def __len__(self):
        if self.mode == 'array' or self.mode == 'list':
            return len(self.data)
        else:
            return max(map(len, self.data.values()))

    def columnNames(self):
        """returns column names in no particular order"""
        if self.mode == 'array':
            return self.data.dtype.names
        elif self.mode == 'list':
            names = set()
            for row in self.data:
                names.update(row.keys())
            return list(names)
        elif self.mode == 'dict':
            return self.data.keys()
            
    def keys(self):
        return self.columnNames()
    
    
    
        

if __name__ == '__main__':
    print "Avaliable DB drivers:", list(QtSql.QSqlDatabase.drivers())
    db = SqliteDatabase()
    db("create table 't' ('int' int, 'real' real, 'text' text, 'blob' blob, 'other' other)")
    columns = db.tableSchema('t').keys()
    
    ## Test insertion and retrieval of different data types into each column type
    vals = [
        ('int', 1), 
        ('float', 1.5), 
        ('int-float', 10.0), 
        ('int-string', '10'), 
        ('float-string', '3.1415'), 
        ('string', 'Stringy'), 
        ('object', [1,'x']), 
        ('byte-string', 'str\1\2\0str'),
        ('None', None),
    ]
    
    for name, val in vals:
        db('delete from t')
        db.insert('t', **dict([(f, val) for f in columns]))
        print "\nInsert %s (%s):" % (name, repr(val))
        print "  ", db.select('t')[0]
        
    print "\nTable extraction test:"
    #db('delete from t')
    for name, val in vals:
        db.insert('t', **dict([(f, val) for f in columns]))
        print "Insert %s (%s):" % (name, repr(val))
    result =  db.select('t', toArray=True)
    print "DATA:", result
    print "DTYPE:", result.dtype
    


