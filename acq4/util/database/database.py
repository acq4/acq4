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
import acq4.Manager
import acq4.util.DataManager as DataManager
import collections
import acq4.util.functions as functions
import acq4.util.advancedTypes as advancedTypes
import acq4.util.debug as debug

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
        ## decide on an appropriate name for this connection.
        ## For file connections, the name should always be the name of the file
        ## to avoid opening more than one connection to the same file.
        if fileName == ':memory:':
            c = 0
            while True:
                self._connectionName = ':memory:%d' % c
                if self._connectionName not in QtSql.QSqlDatabase.connectionNames():
                    break
                c += 1
        else:
            self._connectionName = os.path.abspath(fileName)
            
        if self._connectionName not in QtSql.QSqlDatabase.connectionNames():
            self.db = QtSql.QSqlDatabase.addDatabase("QSQLITE", self._connectionName)
        else:
            self.db = QtSql.QSqlDatabase.database(self._connectionName)
            
            
        self.db.setDatabaseName(fileName)
        self.db.open()
        self.tables = None
        self._transactions = []
        self._readTableList()
        
    def close(self):
        if self.db is None:
            return
        self.db.close()
        self.db = None
        
        ## no need to remove the connection entirely.
        #import gc
        #gc.collect()  ## try to convince python to clean up the db immediately so we can remove the connection
        #QtSql.QSqlDatabase.removeDatabase(self._connectionName)

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
        #print cmd
        #import traceback
        #traceback.print_stack()
        
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
            
    def select(self, table, columns='*', where=None, sql='', toDict=True, toArray=False, distinct=False, limit=None, offset=None):
        """
        Construct and execute a SELECT statement, returning the results.
        
        ============== ================================================================
        **Arguments:**
        table          The name of the table from which to read data
        columns        (list or str) List of column names to read from table. The default is '*', which reads all columns
                       If *columns* is given as a string, it is inserted verbatim into the SQL command.
                       If *columns* is given as a list, it is converted to a string of comma-separated, quoted names.
        where          Optional dict of {column: value} pairs. only results where column=value will be returned
        distinct       (bool) If true, omit all redundant results
        limit          (int) Limit the number of results that may be returned (best used with offset argument)
        offset         (int) Omit a certain number of results from the beginning of the list
        sql            Optional string to be appended to the SQL query (will be inserted before limit/offset arguments)
        toDict         If True, return a list-of-dicts (this is the default)
        toArray        if True, return a numpy record array
        ============== ================================================================
        """
        p = debug.Profiler("SqliteDatabase.select", disabled=True)
        if columns != '*':
            #if isinstance(columns, basestring):
                #columns = columns.split(',')
            if not isinstance(columns, basestring):
                qf = []
                for f in columns:
                    if f == '*':
                        qf.append(f)
                    else:
                        qf.append('"'+f+'"')
                columns = ','.join(qf)
            #columns = quoteList(columns)
            
        whereStr = self._buildWhereClause(where, table)
        distinct = "distinct" if (distinct is True) else ""
        limit = ("limit %d" % limit) if (limit is not None) else ""
        offset = ("offset %d" % offset) if (offset is not None) else ""
        
        cmd = "SELECT %s %s FROM %s %s %s %s %s" % (distinct, columns, table, whereStr, sql, limit, offset)
        p.mark("generated command")
        q = self.exe(cmd, toDict=toDict, toArray=toArray)
        p.finish("Execution finished.")
        return q
        
    def iterSelect(self, *args, **kargs):
        """
        Return a generator that iterates through the results of a select query using limit/offset arguments.
        This is useful for select queries that would otherwise return a very large list of results.
        
        All arguments are passed through to select(). By default, limit=1000 and offset=0.
        Note that if you specify limit or offset, they MUST be given as keyword arguments.
        """
        if 'chunkSize' in kargs:  ## for compatibility with iterInsert
            kargs['limit'] = kargs['chunkSize']
            del kargs['chunkSize']
        if 'offset' not in kargs:
            kargs['offset'] = 0
        if 'limit' not in kargs:
            kargs['limit'] = 1000
            
            
        while True:
            res = self.select(*args, **kargs)
            if res is None or len(res) == 0:
                break
            yield res
            kargs['offset'] += kargs['limit']
        
        
        
    def insert(self, table, records=None, replaceOnConflict=False, ignoreExtraColumns=False, addExtraColumns=False, **args):
        """Insert records (a dict or list of dicts) into table.
        If records is None, a single record may be specified via keyword arguments.
        
        ====================  =======================================
        **Arguments:**
        table                 Name of the table to insert into
        records               Data to insert. May be a variety of formats: numpy record array, list of dicts,
                              dict of lists, dict of values (single record)
        replaceOnConflict     If True, inserts which conflict with pre-existing data will overwrite the
                              pre-existing data. This occurs, for example, when a column has a 'unique' 
                              constraint.
        ignoreExtraColumns    If True, ignore any extra columns in the data that do not exist in the table
        ====================  =======================================
        """
        for n,nmax in self.iterInsert(table=table, records=records, replaceOnConflict=replaceOnConflict, ignoreExtraColumns=ignoreExtraColumns, chunkAll=True, **args):
            pass
        
        
    def iterInsert(self, table, records=None, replaceOnConflict=False, ignoreExtraColumns=False, chunkSize=500, chunkAll=False, **args):
        """
        Iteratively insert chunks of data into a table while yielding a tuple (n, max)
        indicating progress. This *must* be used inside a for loop::
        
            for n,nmax in db.iterInsert(table, data):
                print "Insert %d%% complete" % (100. * n / nmax)
        
        Use the chunkSize argument to determine how many records are inserted at per iteration.
        See insert() for a description of all other options.
        """
        
        p = debug.Profiler("SqliteDatabase.insert", disabled=True)
        if records is None:
            records = [args]
        #if type(records) is not list:
            #records = [records]
        if len(records) == 0:
            return
        ret = []

        with self.transaction():
            ## Rememember that _prepareData may change the number of columns!
            records = TableData(self._prepareData(table, records, ignoreUnknownColumns=ignoreExtraColumns, batch=True))
            p.mark("prepared data")

            columns = records.keys()
            insert = "INSERT"
            if replaceOnConflict:
                insert += " OR REPLACE"
            #print "Insert:", columns
            cmd = "%s INTO %s (%s) VALUES (%s)" % (insert, table, quoteList(columns), ','.join([':'+f for f in columns]))

            numRecs = len(records)
            if chunkAll: ## insert all records in one go.
                self.exe(cmd, records, batch=True)
                yield (numRecs, numRecs)
                return


            chunkSize = int(chunkSize) ## just make sure
            offset = 0
            i = 0
            while offset < len(records):
                #print len(columns), len(records[0]), len(self.tableSchema(table))
                chunk = records[offset:offset+chunkSize]
                self.exe(cmd, chunk, batch=True)
                offset += len(chunk)
                yield (offset, numRecs)
            p.mark("Transaction done")

        p.finish("Executed.")

    def delete(self, table, where):
        with self.transaction():
            whereStr = self._buildWhereClause(where, table)
            cmd = "DELETE FROM %s %s" % (table, whereStr)
            return self(cmd)

    def update(self, table, vals, where=None, rowid=None, sql=''):
        """Update records in the DB.
        Arguments:
            vals: dict of {column: value} pairs
            where: SQL clause specifying rows to update
            rowid: int row IDs. Used instead of 'where'
            sql: SQL string to append to end of statement"""
        if rowid is not None:
            if where is not None:
                raise Exception("'where' and 'rowid' are mutually exclusive arguments.")
            where = {'rowid': rowid}
        
        with self.transaction():
            whereStr = self._buildWhereClause(where, table)
            setStr = ', '.join(['"%s"=:%s' % (k, k) for k in vals])
            cmd = "UPDATE %s SET %s %s %s" % (table, setStr, whereStr, sql)
            data = self._prepareData(table, [vals], batch=True)
            return self(cmd, data, batch=True)

    def transaction(self, name=None):
        """Return an enterable Transaction instance.
        Use thusly::

            with db.transaction():
                db.doStuff()
                db.doMoreStuff()

        If an exception is raised while the transaction is active, all changes will be rolled back.
        Note that wrapping multiple database operations in a transaction can *greatly* increase
        performance.
        """
        return Transaction(self, name)
        
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
        (see sqlite 'CREATE TABLE')
        """
        #print "create table", table, ', '.join(columns)
        
        columns = parseColumnDefs(columns)
        
        columnStr = []
        for name, conf in columns.iteritems():
            columnStr.append('"%s" %s %s' % (name, conf['Type'], conf.get('Constraints', '')))
        columnStr = ','.join(columnStr)

        self('CREATE TABLE "%s" (%s) %s' % (table, columnStr, sql))
        self._readTableList()

    def createIndex(self, table, columns, ifNotExist=True):
        """
        Create an index on table (columns)
        *columns* may be the name of a single column or a list of column names.
        (see sqlite 'CREATE INDEX')
        """
        ine = "IF NOT EXISTS" if ifNotExist else ""
        if isinstance(columns, basestring):
            columns = [columns]
        name = table + '__' + '_'.join(columns)
        colStr = quoteList(columns)
        cmd = 'CREATE INDEX %s "%s" ON "%s" (%s)' % (ine, name, table, colStr)
        self(cmd)

    def addColumn(self, table, colName, colType, constraints=None):
        """
        Add a column to a table.
        """
        if constraints is None:
            constraints = ''
        self('ALTER TABLE "%s" ADD COLUMN "%s" %s %s' % (table, colName, colType, constraints))
        self.tables = None
 
    def listTables(self):
        """
        Return a list of the names of tables in the DB.
        """
        if self.tables is None:
            self._readTableList()
        return self.tables.keys()
 
    def removeTable(self, table):
        self('DROP TABLE "%s"' % table)

    def hasTable(self, table):
        self.listTables()  ## make sure table list has been generated
        return table in self.tables  ## this is a case-insensitive operation
    
    def tableSchema(self, table):
        """
        Return a dict {'columnName': 'type', ...} for the specified table.
        """
        if self.tables is None:
            self._readTableList()
        return self.tables[table].copy()  ## this is a case-insensitive operation
    
    def tableLength(self, table):
        return self('select count(*) from "%s"' % table)[0]['count(*)']
    
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
            self.tables = None  ## clear table cache
    
    def _buildWhereClause(self, where, table):
        if where is None or len(where) == 0:
            return ''
            
        where = self._prepareData(table, where)[0]
        conds = []
        for k,v in where.iteritems():
            if isinstance(v, basestring):
                conds.append('"%s"=\'%s\'' % (k, v))
            else:
                conds.append('"%s"=%s' % (k,v))
        whereStr = "WHERE " + " AND ".join(conds)
        return whereStr

    
    def _prepareData(self, table, data, ignoreUnknownColumns=False, batch=False):
        ## Massage data so it is ready for insert into the DB. (internal use only)
        ##   - data destined for BLOB columns is pickled
        ##   - numerical columns convert to int or float
        ##   - text columns convert to unicode
        ## converters may be a dict of {'columnName': function} 
        ## that overrides the default conversion funcitons.
        
        ## Returns a dict-of-lists if batch=True, otherwise list-of-dicts
        
        
        data = TableData(data)
        
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
            newData = dict([(k,[]) for k in data.columnNames() if not (ignoreUnknownColumns and (k not in schema))])
        else:
            newData = []
            
        for rec in data:
            newRec = {}
            for k in rec:
                if k not in schema:
                    if ignoreUnknownColumns:
                        continue
                    #if addUnknownColumns:  ## Is this just a bad idea?
                        #dtyp = self.suggestColumnType(rec[k])
                        #self.addColumn(table, k, dtyp)
                if rec[k] is None:
                    newRec[k] = None
                else:
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
        prof = debug.Profiler("_queryToDict", disabled=True)
        res = []
        while q.next():
            res.append(self._readRecord(q.record()))
        return res


    def _queryToArray(self, q):
        prof = debug.Profiler("_queryToArray", disabled=True)
        recs = self._queryToDict(q)
        prof.mark("got records")
        if len(recs) < 1:
            #return np.array([])  ## need to return empty array *with correct columns*, but this is very difficult, so just return None
            return None
        rec1 = recs[0]
        dtype = functions.suggestRecordDType(rec1, singleRecord=True)
        #print rec1, dtype
        arr = np.empty(len(recs), dtype=dtype)
        arr[0] = tuple(rec1.values())
        for i in xrange(1, len(recs)):
            arr[i] = tuple(recs[i].values())
        prof.mark('converted to array')
        prof.finish()
        return arr


    def _readRecord(self, rec):
        prof = debug.Profiler("_readRecord", disabled=True)
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
        prof.finish()
        return data

    def _readTableList(self):
        """Reads the schema for each table, extracting the column names and types."""
        
        ### Removed: use pragma table_info rather than parsing sqlite_master manually.
        #res = self.select('sqlite_master', ['name', 'sql'], sql="where type = 'table'")
        #ident = r"(\w+|'[^']+'|\"[^\"]+\")"
        ##print "READ:"
        #tables = advancedTypes.CaselessDict()
        #for rec in res:
            ##print rec
            #sql = rec['sql'].replace('\n', ' ')
            ##print sql
            #m = re.match(r"\s*create\s+table\s+%s\s*\(([^\)]+)\)" % ident, sql, re.I)
            ##print m.groups()
            #columnstr = m.groups()[1].split(',')
            #columns = advancedTypes.CaselessDict()
            ##print columnstr
            ##print columnstr
            #for f in columnstr:
                ##print "   ", f
                #m = re.findall(ident, f)
                ##print "   ", m
                #if len(m) < 2:
                    #typ = ''
                #else:
                    #typ = m[1].strip('\'"')
                #column = m[0].strip('\'"')
                #columns[column] = typ
            #tables[rec['name']] = columns
        
        names = self("select name from sqlite_master where type='table' or type='view'")
        tables = advancedTypes.CaselessDict()
        for table in names:
            table = table['name']
            columns = advancedTypes.CaselessDict()
            recs = self('PRAGMA table_info(%s)' % table)
            for rec in recs:
                columns[rec['name']] = rec['type']
            tables[table] = columns
            
        self.tables = tables
        #print tables


class Transaction:
    """See SQLiteDatabase.transaction()"""
    def __init__(self, db, name=None):
        self.db = db
        self.name = name
        
    def __enter__(self):
        if self.name is None:
            self.name = 'transaction%d' % len(self.db._transactions)
        self.db('SAVEPOINT %s' % self.name)
        self.db._transactions.append(self)

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.db('RELEASE SAVEPOINT %s' % self.name)
        else:
            self.db('ROLLBACK TRANSACTION TO %s' % self.name)
            self.db.tables = None  ## make sure we are forced to re-read the table list after the rollback.
        
        if self.db._transactions[-1] is not self:
            print self, self.db._transactions
            raise Exception('Tried to exit transaction before another nested transaction has finished.')
        self.db._transactions.pop(-1)


class TableData:
    """
    Class for presenting multiple forms of tabular data through a consistent interface.
    May contain:
        - numpy record array
        - list-of-dicts (all dicts are _not_ required to have the same keys)
        - dict-of-lists
        - dict (single record)
               Note: if all the values in this record are lists, it will be interpreted as multiple records
        
    Data can be accessed and modified by column, by row, or by value
        data[columnName]                        # returns list or array
        data[rowId]                             # returns dict or ordereddict
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
            types = set(map(type, data.values()))
            ## dict may be a dict-of-lists or a single record
            types -= set([list, np.ndarray]) ## if dict contains any non-sequence values, it is probably a single record.
            if len(types) != 0:
                self.data = [self.data]
                self.mode = 'list'
            else:
                self.mode = 'dict'
        elif isinstance(data, TableData) or 'TableData' in str(type(data)):
            self.data = data.data
            self.mode = data.mode
        else:
            raise Exception("Cannot create TableData from object '%s' (type='%s')" % (str(data), type(data)))
        
        for fn in ['__getitem__', '__setitem__']:
            setattr(self, fn, getattr(self, '_TableData'+fn+self.mode))
        self.copy = getattr(self, 'copy_' + self.mode)
        
    def originalData(self):
        return self.data
    
    def toArray(self):
        if self.mode == 'array':
            return self.data
        if len(self) < 1:
            #return np.array([])  ## need to return empty array *with correct columns*, but this is very difficult, so just return None
            return None
        rec1 = self[0]
        #dtype = functions.suggestRecordDType(self)
        ## Need to look through all data before deciding on dtype.
        ## It is not sufficient to look at just the first record,
        ## nor to look at the column types.
        types = {k:set() for k in self.keys()}
        for rec in self:
            for k,v in rec.items():
                types[k].add(type(v))
        dtype = []
        for k in self.keys():
            t = types[k]
            if t == set([float]) or t == set([float, type(None)]):
                dtype.append((k, float))
            elif t == set([int]):
                dtype.append((k, int))
            else:
                dtype.append((k, object))
        
        #print rec1, dtype
        arr = np.empty(len(self), dtype=dtype)
        arr[0] = tuple(rec1.values())
        for i in xrange(1, len(self)):
            arr[i] = tuple(self[i].values())
        return arr
            
    def __getitem__array(self, arg):
        if isinstance(arg, basestring):
            return self.data[arg]
        elif isinstance(arg, int):
            return collections.OrderedDict([(k, self.data[k][arg]) for k in self.columnNames()])
        elif isinstance(arg, tuple):
            return self.data[arg[0]][arg[1]]
        elif isinstance(arg, slice):
            return TableData(self.data[arg])
        else:
            raise Exception("Cannot index TableData with object '%s' (type='%s')" % (str(arg), type(arg)))
            
    def __getitem__list(self, arg):
        if isinstance(arg, basestring):
            return [d.get(arg, None) for d in self.data]
        elif isinstance(arg, int):
            return self.data[arg]
        elif isinstance(arg, tuple):
            arg = self._orderArgs(arg)
            return self.data[arg[0]][arg[1]]
        elif isinstance(arg, slice):
            return TableData(self.data[arg])
        else:
            raise Exception("Cannot index TableData with object '%s' (type='%s')" % (str(arg), type(arg)))
        
    def __getitem__dict(self, arg):
        if isinstance(arg, basestring):
            return self.data[arg]
        elif isinstance(arg, int):
            return collections.OrderedDict([(k, v[arg]) for k, v in self.data.iteritems()])
        elif isinstance(arg, tuple):
            arg = self._orderArgs(arg)
            return self.data[arg[1]][arg[0]]
        elif isinstance(arg, slice):
            return TableData(collections.OrderedDict([(k, v[arg]) for k, v in self.data.iteritems()]))
        else:
            raise Exception("Cannot index TableData with object '%s' (type='%s')" % (str(arg), type(arg)))

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
        
    def copy_array(self):
        return TableData(self.data.copy())
        
    def copy_list(self):
        return TableData([rec.copy() for rec in self.data])
        
    def copy_dict(self):
        return TableData({k:v[:] for k,v in self.data.iteritems()})
        
        
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
            if len(self.data) == 0:
                return []
            return self.data[0].keys()  ## all records must have all keys. 
            #names = set()
            #for row in self.data:
                #names.update(row.keys())
            #return list(names)
        elif self.mode == 'dict':
            return self.data.keys()
            
    def keys(self):
        return self.columnNames()
    
    
def parseColumnDefs(defs, keyOrder=None):
    """
    Translate a few different forms of column definitions into a single common format.
    These formats are accepted for all methods which request column definitions (createTable,
    checkTable, etc)
        list of tuples:  [(name, type, <constraints>), ...]
        dict of strings: {name: type, ...}
        dict of tuples:  {name: (type, <constraints>), ...}
        dict of dicts:   {name: {'Type': type, ...}, ...}
        
    Returns dict of dicts as the common format.
    """
    if keyOrder is None:
        keyOrder = ['Type', 'Constraints']
    def isSequence(x):
        return isinstance(x, list) or isinstance(x, tuple)
    def toDict(args):
        d = collections.OrderedDict()
        for i,v in enumerate(args):
            d[keyOrder[i]] = v
            if i >= len(keyOrder) - 1:
                break
        return d
        
    if isSequence(defs) and all(map(isSequence, defs)):
        return collections.OrderedDict([(c[0], toDict(c[1:])) for c in defs])
        
    if isinstance(defs, dict):
        ret = collections.OrderedDict()
        for k, v in defs.iteritems():
            if isSequence(v):
                ret[k] = toDict(v)
            elif isinstance(v, dict):
                ret[k] = v
            elif isinstance(v, basestring):
                ret[k] = {'Type': v}
            else:
                raise Exception("Invalid column-list specification: %s" % str(defs))
        return ret
        
    else:
        raise Exception("Invalid column-list specification: %s" % str(defs))

    
        

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
    


