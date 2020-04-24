# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
import numpy as np
import pickle, re, os
import acq4.Manager
import acq4.util.DataManager as DataManager
import collections
import acq4.util.functions as functions
import acq4.util.advancedTypes as advancedTypes
import six
from six.moves import range

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
    any picklable objects to be directly stored in BLOB type fields. (it is not necessarily
    safe to store pickled objects in TEXT fields)
    
    NOTE: Data types in SQLITE work differently than in most other DBs--each value may take any type
    regardless of the type specified by its column.
    """
    def __init__(self, fileName=':memory:'):
        self.db = Qt.QSqlDatabase.addDatabase("QSQLITE")
        self.db.setDatabaseName(fileName)
        self.db.open()
        self._readTableList()
        
    def close(self):
        self.db.close()

    def exe(self, cmd, data=None, toDict=True, toArray=False):
        """Execute an SQL query. If data is provided, it should be a list of dicts and each will 
        be bound to the query and executed sequentially. Returns the query object."""
        q = Qt.QSqlQuery(self.db)
        if data is None:
            self._exe(q, cmd)
        else:
            res = []
            if not q.prepare(cmd):
                print("SQL Query:\n    %s" % cmd)
                raise Exception("Error preparing SQL query (query is printed above): %s" % str(q.lastError().text()))
            for d in data:
                #print len(d)
                for k, v in d.items():
                    q.bindValue(':'+k, v)
                    #print k, v, type(v)
                #print "==execute with bound data=="
                #print cmd
                #print q.boundValues()
                #for k, v in iteritems(q.boundValues()):
                    #print str(k), v.typeName()
                self._exe(q)
                
        if toArray:
            return self._queryToArray(q)
        elif toDict:
            return self._queryToDict(q)
        else:
            return q
            
    def __call__(self, *args, **kargs):
        return self.exe(*args, **kargs)
            
    def select(self, table, fields='*', sql='', toDict=True, toArray=False):
        """fields should be a list of field names"""
        if fields != '*':
            if isinstance(fields, six.string_types):
                fields = fields.split(',')
            qf = []
            for f in fields:
                if f == '*':
                    qf.append(f)
                else:
                    qf.append('"'+f+'"')
            fields = ','.join(qf)
            #fields = quoteList(fields)
        cmd = "SELECT %s FROM %s %s" % (fields, table, sql)
        #print cmd
        q = self.exe(cmd, toDict=toDict, toArray=toArray)
        #return self._queryToDict(q)
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
        
        if records is None:
            records = [args]
        if type(records) is not list:
            records = [records]
        if len(records) == 0:
            return
        ret = []
            
        ## Rememember that _prepareData may change the number of columns!
        records = self._prepareData(table, records, removeUnknownColumns=ignoreExtraColumns)
        
        fields = list(records[0].keys())
        insert = "INSERT"
        if replaceOnConflict:
            insert += " OR REPLACE"
        #print "Insert:", fields
        cmd = "%s INTO %s (%s) VALUES (%s)" % (insert, table, quoteList(fields), ','.join([':'+f for f in fields]))
        
        #print len(fields), len(records[0]), len(self.tableSchema(table))
        self.exe(cmd, records)

    def delete(self, table, where):
        cmd = "DELETE FROM %s WHERE %s" % (table, where)
        return self(cmd)

    def update(self, table, vals, where=None, rowid=None):
        """Update records in the DB.
        Arguments:
            vals: dict of {field: value} pairs
            where: SQL clause specifying rows to update
            rowid: int row IDs. Used instead of 'where'"""
        if where is None:
            if rowid is None:
                raise Exception("Must specify 'where' or 'rowids'")
            else:
                where = "rowid=%d" % rowid
        setStr = ', '.join(['"%s"=:%s' % (k, k) for k in vals])
        data = self._prepareData(table, [vals])
        cmd = "UPDATE %s SET %s WHERE %s" % (table, setStr, where)
        return self(cmd, data)

    def lastInsertRow(self):
        q = self("select last_insert_rowid()")
        return list(q[0].values())[0]

    def replace(self, *args, **kargs):
        return self.insert(*args, replaceOnConflict=True, **kargs)

    def createTable(self, table, fields, sql=""):
        """Create a table in the database.
          table: (str) the name of the table to create
          fields: (list) a list of strings defining columns in the table. 
                  These usually look like '"FieldName" type' 
                  OR
                  (dict) a dictionary of 'FieldName': 'type' pairs
                  Types may be any string, but are typically int, real, text, or blob.
                  """
        #print "create table", table, ', '.join(fields)
        if isinstance(fields, list):
            fieldStr = ','.join(fields)
        elif isinstance(fields, dict):
            fieldStr = ', '.join(['"%s" %s' % (n, t) for n,t in fields.items()])
        self('CREATE TABLE %s (%s) %s' % (table, fieldStr, sql))
        self._readTableList()

    def hasTable(self, table):
        return table in self.tables  ## this is a case-insensitive operation
    
    def tableSchema(self, table):
        return self.tables[table]  ## this is a case-insensitive operation
    
    def _exe(self, query, cmd=None):
        """Execute an SQL query, raising an exception if there was an error. (internal use only)"""
        if cmd is None:
            ret = query.exec_()
        else:
            ret = query.exec_(cmd)
        if not ret:
            if cmd is not None:
                print("SQL Query:\n    %s" % cmd)
                raise Exception("Error executing SQL (query is printed above): %s" % str(query.lastError().text()))
            else:
                raise Exception("Error executing SQL: %s" % str(query.lastError().text()))
                
        if str(query.executedQuery())[:6].lower() == 'create':
            self._readTableList()
    
    
    def _prepareData(self, table, data, removeUnknownColumns=False):
        """Massage data so it is ready for insert into the DB. (internal use only)
         - data destined for BLOB fields is pickled
         - numerical fields convert to int or float
         - text fields convert to unicode
         
         """
         
         ## This can probably be optimized a bit..
        #rec = data[0]
        funcs = {}
        ## determine the functions to use for each field.
        schema = self.tableSchema(table)
        for k in schema:
            #if k not in schema:
                #raise Exception("Table %s has no field named '%s'. Schema is: %s" % (table, k, str(schema)))
            typ = schema[k].lower()
            if typ == 'blob':
                funcs[k] = lambda obj: Qt.QByteArray(pickle.dumps(obj))
            elif typ == 'int':
                funcs[k] = int
            elif typ == 'real':
                funcs[k] = float
            elif typ == 'text':
                funcs[k] = str
            else:
                funcs[k] = lambda obj: obj
        newData = []
        for rec in data:
            newRec = {}
            for k in rec:
                if removeUnknownColumns and (k not in schema):
                    #print "skip column", k
                    continue
                #print "include column", k
                
                try:
                    newRec[k] = funcs[k](rec[k])
                except:
                    newRec[k] = rec[k]
                    if k.lower() != 'rowid':
                        if k not in schema:
                            raise Exception("Field '%s' not present in table '%s'" % (k, table))
                        print("Warning: Setting %s field %s.%s with type %s" % (schema[k], table, k, str(type(rec[k]))))
            newData.append(newRec)
        #print "new data:", newData
        return newData

    def _queryToDict(self, q):
        res = []
        while next(q):
            res.append(self._readRecord(q.record()))
        return res


    def _queryToArray(self, q):
        recs = self._queryToDict(q)
        if len(recs) < 1:
            #return np.array([])  ## need to return empty array *with correct fields*, but this is very difficult, so just return None
            return None
        rec1 = recs[0]
        dtype = functions.suggestRecordDType(rec1)
        #print rec1, dtype
        arr = np.empty(len(recs), dtype=dtype)
        arr[0] = tuple(rec1.values())
        for i in range(1, len(recs)):
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
                if isinstance(val, Qt.QByteArray):
                    val = pickle.loads(str(val))
                #v = rec.value(i)   ## required when not using V2 API for QVariant
                #t = v.type()
                #if t in [Qt.QVariant.Int, Qt.QVariant.LongLong]:
                    #val = v.toInt()[0]
                #if t in [Qt.QVariant.Double]:
                    #val = v.toDouble()[0]
                #elif t == Qt.QVariant.String:
                    #val = str(v.toString())
                #elif t == Qt.QVariant.ByteArray:
                    #val = pickle.loads(str(v.toByteArray()))
            data[n] = val
        return data

    def _readTableList(self):
        """Reads the schema for each table, extracting the field names and types."""
        
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
            fieldstr = m.groups()[1].split(',')
            fields = advancedTypes.CaselessDict()
            #print fieldstr
            #print fieldstr
            for f in fieldstr:
                #print "   ", f
                m = re.findall(ident, f)
                #print "   ", m
                if len(m) < 2:
                    typ = ''
                else:
                    typ = m[1].strip('\'"')
                field = m[0].strip('\'"')
                fields[field] = typ
            tables[rec['name']] = fields
        self.tables = tables
        #print tables


class AnalysisDatabase(SqliteDatabase):
    """Defines the structure for DBs used for analysis. Essential features are:
     - a table of control parameters "DbParameters" 
     - a table defining relationships between tables "TableRelationships"
     - a table assgning ownership of data tables to analysis modules
     - Directories created by data manager can be added automatically to DB
     - Automatic creation of views that join together directory hierarchies
     """
    
    def __init__(self, dbFile, baseDir=None):
        create = False
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
            
    def initializeDb(self):
        self.createTable("DbParameters", ['"Param" text unique', '"Value" text'])
        
        ## Table1.Column refers to Table2.ROWID
        self.createTable("TableRelationships", ['"Table1" text', '"Column" text', '"Table2" text'])
        
        self.createTable("DataTableOwners", ['"Owner" text', '"Table" text unique on conflict abort'])

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
        return self.select('DbParameters', ['Value'], "where Param='%s'"%param)[0]['Value']
        
    def setCtrlParam(self, param, value):
        self.replace('DbParameters', {'Param': param, 'Value': value})
        

    def createDirTable(self, dirHandle, tableName=None, fields=None):
        """Creates a new table for storing directories similar to dirHandle"""
        parent = dirHandle.parent()
        fields = ['"Dir" text'] + fields
        
        if tableName is None:
            #info = dirHandle.info()
            #tableName = info['dirType']
            tableName = self.dirTypeName(dirHandle)
        
        if parent is not self.baseDir():
            fields = ['"Source" int'] + fields
            self.linkTables(tableName, "Source", self.dirTypeName(parent))
        self.createTable(tableName, fields)
        return tableName

    def linkTables(self, table1, col, table2):
        """Declare a key relationship between two tables. Values in table1.column are ROWIDs from table 2"""
        self.insert('TableRelationships', Table1=table1, Column=col, Table2=table2)

    def addDir(self, handle, table=None):
        """Create a record based on a DirHandle and its meta-info.
        If no table is specified, use the dirType attribute as table name"""
        info = handle.info().deepcopy()
        
        ## determine parent directory, make sure parent is in DB.
        parent = handle.parent()
        parentRowId = None
        if parent.isManaged() and parent is not self.baseDir():
            pTable, parentRowId = self.addDir(parent)
        
        #if table is None:
            #table = info.get('dirType', None)
        #if table is None:
            #raise Exception("Dir %s has no dirType; can not add to DB automatically." % handle.name())
        if table is None:
            table = self.dirTypeName(handle)
            
        if not self.hasTable(table):
            fields = list(acq4.Manager.getManager().suggestedDirFields(handle).keys())
            for k in info:
                if k not in fields:
                    fields.append(k)
            spec = ["'%s' text"%k for k in fields]
            #db.createTable(table, spec)
            self.createDirTable(handle, table, spec)
            
        ## make sure dir is not already in DB. 
        ## if it is, just return the row ID
        rid = self.getDirRowID(handle, table)
        if rid is not None:
            return table, rid
            
        if parentRowId is not None:
            info['Source'] = parentRowId
        info['Dir'] = handle.name(relativeTo=self.baseDir())
        
        self.insert(table, info, ignoreExtraColumns=True)

        return table, self.lastInsertRow()

    def getDirRowID(self, dirHandle, table=None):
        if table is None:
            #info = dirHandle.info()
            #if 'dirType' not in info:
                #raise Exception("Directory '%s' has no dirType attribute." % dirHandle.name())
            #table = info['dirType']
            table = self.dirTypeName(dirHandle)
            
        if not self.hasTable(table):
            return None
        rec = self.select(table, ['rowid'], "where Dir='%s'" % dirHandle.name(relativeTo=self.baseDir()))
        if len(rec) < 1:
            return None
        #print rec[0]
        return rec[0]['rowid']

    def getDir(self, table, rowid):
        res = self.select(table, ['Dir'], 'where rowid=%d'%rowid)
        if len(res) < 1:
            raise Exception('rowid %d does not exist in %s' % (rowid, table))
        #print res
        return self.baseDir()[res[0]['Dir']]

    def dirTypeName(self, dh):
        info = dh.info()
        type = info.get('dirType', None)
        if type is None:
            if 'protocol' in info:
                if 'sequenceParams' in info:
                    type = 'ProtocolSequence'  
                else:
                    type = 'Protocol'  ## an individual protocol run, NOT a single run from within a sequence
            else:
                try:
                    if self.dirTypeName(dh.parent()) == 'ProtocolSequence':
                        type = 'Protocol'
                    else:
                        raise Exception()
                except:
                    raise Exception("Can't determine type for dir %s" % dh.name())
        return type

    ### TODO: No more 'purpose', just use 'owner.purpose' instead
    def listTablesOwned(self, owner):
        res = self.select("DataTableOwners", ["Table"], sql="where Owner='%s'" % owner)
        return [x['Table'] for x in res]
    
    def listTables(self):
        return list(self.tables.keys())
        
    def takeOwnership(self, table, owner):
        self.insert("DataTableOwners", {'Table': table, "Owner": owner})
    
    def tableOwner(self, table):
        res = self.select("DataTableOwners", ["Owner"], sql='where "Table"=\'%s\'' % table)
        if len(res) == 0:
            return None
        return res[0]['Owner']

    def describeData(self, data):
        """Given a dict or record array, return a table description suitable for creating / checking tables."""
        fields = collections.OrderedDict()
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
                    typ = 'blob'
                fields[name] = typ
        elif isinstance(data, dict):
            for name, v in data.items():
                if functions.isFloat(v):
                    typ = 'real'
                elif functions.isInt(v):
                    typ = 'int'
                elif isinstance(v, six.string_types):
                    typ = 'text'
                else:
                    typ = 'blob'
                fields[name] = typ
        else:
            raise Exception("Can not describe data of type '%s'" % type(data))
        return fields

    def checkTable(self, table, owner, fields, links=[], create=False):
        ## Make sure target table exists and has correct columns, links to input file
        if not self.hasTable(table):
            if create:
                ## create table
                self.createTable(table, fields)
                for field, ptable in links:
                    self.linkTables(table, field, ptable)
                self.takeOwnership(table, owner)
            else:
                raise Exception("Table %s does not exist." % table)
        else:
            ## check table for ownership, columns
            if self.tableOwner(table) != owner:
                raise Exception("Table %s is not owned by %s." % (table, owner))
            
            ts = self.tableSchema(table)
            for f in fields:
                if f not in ts:  ## this is a case-insensitive operation
                    raise Exception("Table has different data structure: Missing field %s" % f)
                elif ts[f].lower() != fields[f].lower():  ## type names are case-insensitive too
                    raise Exception("Table has different data structure: Field '%s' type is %s, should be %s" % (f, ts[f], fields[f]))
        return True

if __name__ == '__main__':
    print("Avaliable DB drivers:", list(Qt.QSqlDatabase.drivers()))

    db = SqliteDatabase()
    db("create table 't' ('int' int, 'real' real, 'text' text, 'blob' blob)")
    
    
    ## Test insertion and retrieval of different data types into each field type
    vals = [('int', 1), ('float', 1.5), ('int-float', 10.0), ('int-string', '10'), ('float-string', '3.1415'), ('string', 'Stringy'), ('object', [1,'x']), ('byte-string', 'str\1\2\0str')]
    
    for name, val in vals:
        db('delete from t')
        db.insert('t', int=val, real=val, text=val, blob=val)
        print("Insert %s (%s):" % (name, repr(val)))
        print("  ", db.select('t')[0])
        
    print("Table extraction test:")
    for name, val in vals:
        #db('delete from t')
        db.insert('t', int=val, real=val, text=val, blob=val)
        #print "Insert %s (%s):" % (name, repr(val))
        #print "  ", db.select('t')[0]
    print(db.select('t', toArray=True))
    