# -*- coding: utf-8 -*-
from PyQt4 import QtSql, QtCore
import numpy as np
import pickle, re, os
import DataManager


class AnalysisDatabase:
    """Defines the structure for DBs used for analysis. Essential features are:
     - a table of control parameters "DbParameters" 
     - a table defining relationships between tables "TableRelationships"
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

        self.db = SqliteDatabase(dbFile)
        
        if create:
            self.initializeDb()
            self.setBaseDir(baseDir)
            
    def initializeDb(self):
        self.db.createTable("DbParameters", ["'Param' text unique", "'Value' text"])
        
        ## Table1.Column refers to Table2.ROWID
        self.db.createTable("TableRelationships", ["'Table1' text", "'Column' text", "'Table2' text"])

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
        return self.db.select('DbParameters', ['Value'], "where Param='%s'"%param)[0]['Value']
        
    def setCtrlParam(self, param, value):
        self.db.replace('DbParameters', {'Param': param, 'Value': value})
        

    def createDirTable(self, dirHandle, tableName=None, fields=None):
        """Ctrates a new table for storing directories similar to dirHandle"""
        parent = dirHandle.parent()
        fields = ["'Dir' text"] + fields
        
        if tableName is None:
            info = dirHandle.info()
            tableName = info['dirType']
        
        if parent is not self.baseDir():
            fields = ["'Source' int"] + fields
            self.db.insert('TableRelationships', Table1=tableName, Column="Source", Table2=parent.info()['dirType'])
        self.db.createTable(tableName, fields)
        return tableName

    def addDir(self, handle, table=None):
        """Create a record based on a DirHandle and its meta-info.
        If no table is specified, use the dirType attribute as table name"""
        info = handle.info()
        
        ## determine parent directory, make sure parent is in DB.
        parent = handle.parent()
        parentRowId = None
        if parent.isManaged() and parent is not self.baseDir():
            parentRowId = self.addDir(parent)
        
        if table is None:
            table = info['dirType']
            
        if not self.db.hasTable(table):
            spec = ["'%s' text"%k for k in info]
            #db.createTable(table, spec)
            self.createDirTable(handle, table, spec)
            
        ## make sure dir is not already in DB. 
        ## if it is, just return the row ID
        rid = self.getDirRowID(handle, table)
        if rid is not None:
            return rid
            
        if parentRowId is not None:
            info['Source'] = parentRowId
        info['Dir'] = handle.name(relativeTo=self.baseDir())
        self.db.insert(table, info)

        return self.db.lastInsertRow()

    def getDirRowID(self, dirHandle, table=None):
        if table is None:
            info = dirHandle.info()
            if 'dirType' not in info:
                raise Exception("Directory '%s' has no dirType attribute." % dirHandle.name())
            table = info['dirType']
        rec = self.db.select(table, ['rowid'], "where Dir='%s'" % dirHandle.name(relativeTo=self.baseDir()))
        if len(rec) < 1:
            return None
        #print rec[0]
        return rec[0]['rowid']


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
        self.db = QtSql.QSqlDatabase.addDatabase("QSQLITE")
        self.db.setDatabaseName(fileName)
        self.db.open()
        self._readTableList()

    def exe(self, cmd, data=None):
        """Execute an SQL query. If data is provided, it should be a list of dicts and each will be bound to the query and executed sequentially. Returns the query object."""
        q = QtSql.QSqlQuery(self.db)
        if data is None:
            self._exe(q, cmd)
        else:
            res = []
            q.prepare(cmd)
            for d in data:
                for k, v in d.iteritems():
                    q.bindValue(':'+k, v)
                self._exe(q)
        return q
            
    def __call__(self, *args, **kargs):
        return self.exe(*args, **kargs)
            
    def select(self, table, fields='*', sql=''):
        q = self.exe("SELECT %s FROM %s %s" % (','.join(fields), table, sql))
        return self._queryToDict(q)
        
    def insert(self, table, records=None, replaceOnConflict=False, **args):
        """Insert records (a dict or list of dicts) into table.
        if records is None, a simgle record may be specified via keyword arguments."""
        if records is None:
            records = [args]
        if type(records) is not list:
            records = [records]
        if len(records) == 0:
            return
        ret = []
            
        fields = records[0].keys()
        insert = "INSERT"
        if replaceOnConflict:
            insert += " OR REPLACE"
        cmd = "%s INTO %s (%s) VALUES (%s)" % (insert, table, ','.join(fields), ','.join([":"+f for f in fields]))
        records = self._prepareData(table, records)
        self.exe(cmd, records)

    def lastInsertRow(self):
        q = self("select last_insert_rowid()")
        q.first()
        return q.value(0)

    def replace(self, *args, **kargs):
        return self.insert(*args, replaceOnConflict=True, **kargs)

    def createTable(self, table, fields):
        """Create a table in the database."""
        #print "create table", table, ', '.join(fields)
        self('CREATE TABLE %s (%s)' % (table, ', '.join(fields)))
        self._readTableList()

    def hasTable(self, table):
        return table in self.tables
            
    def _exe(self, query, cmd=None):
        """Execute an SQL query, raising an exception if there was an error. (internal use only)"""
        if cmd is None:
            ret = query.exec_()
        else:
            ret = query.exec_(cmd)
        if not ret:
            print "SQL Query:\n    %s" % cmd
            raise Exception("Error executing SQL (query is printed above): %s" % str(query.lastError().text()))
        if str(query.executedQuery())[:6].lower() == 'create':
            self._readTableList()
        
        
    def _prepareData(self, table, data):
        """Massage data so it is ready for insert into the DB. (internal use only)
        This currently just means that data destined for BLOB fields is pickled."""
        rec = data[0]
        blobs = []
        #print data
        for k in rec:
            schema = self.tables[table]
            if k not in schema:
                raise Exception("Table %s has no field named '%s'. Schema is: %s" % (table, k, str(schema)))
            if self.tables[table][k].lower() == 'blob':
                blobs.append(k)
        if len(blobs) == 0:
            return data
        newData = []
        for rec in data:
            newRec = rec.copy()
            for b in blobs:
                newRec[b] = QtCore.QByteArray(pickle.dumps(newRec[b]))
            newData.append(newRec)
        return newData

    def _queryToDict(self, q):
        res = []
        while q.next():
            res.append(self._readRecord(q.record()))
        return res


    def _queryToArray(self, q):
        pass


    def _readRecord(self, rec):
        data = {}
        for i in range(rec.count()):
            f = rec.field(i)
            n = str(f.name())
            if rec.isNull(i):
                val = None
            else:
                v = rec.value(i)
                t = v.type()
                if t in [QtCore.QVariant.Int, QtCore.QVariant.LongLong]:
                    val = v.toInt()[0]
                if t in [QtCore.QVariant.Double]:
                    val = v.toDouble()[0]
                elif t == QtCore.QVariant.String:
                    val = str(v.toString())
                elif t == QtCore.QVariant.ByteArray:
                    val = pickle.loads(str(v.toByteArray()))
            data[n] = val
        return data

    def _readTableList(self):
        res = self.select('sqlite_master', ['name', 'sql'], "where type = 'table'")
        ident = r"(\w+|'[^']+'|\"[^\"]+\")"
        #print "READ:"
        tables = {}
        for rec in res:
            sql = rec['sql'].replace('\n', ' ')
            #print sql
            m = re.match(r"\s*create\s+table\s+%s\s*\(([^\)]+)\)" % ident, sql, re.I)
            #print m.groups()
            fieldstr = m.groups()[1].split(',')
            fields = {}
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





if __name__ == '__main__':
    print "Avaliable DB drivers:", list(QtSql.QSqlDatabase.drivers())

    db = SqliteDatabase()
    db("create table 't' ('int' int, 'real' real, 'text' text, 'blob' blob)")
    
    
    ## Test insertion and retrieval of different data types into each field type
    vals = [('int', 1), ('float', 1.5), ('int-float', 10.0), ('int-string', '10'), ('float-string', '3.1415'), ('string', 'Stringy'), ('object', [1,'x']), ('byte-string', 'str\1\2\0str')]
    
    for name, val in vals:
        db('delete from t')
        db.insert('t', int=val, real=val, text=val, blob=val)
        print "Insert %s (%s):" % (name, repr(val))
        print "  ", db.select('t')[0]