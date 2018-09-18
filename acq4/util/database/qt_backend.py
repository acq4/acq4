from __future__ import print_function
import six
from six.moves import range


"""
Deprecated class based on QtSql; new implementation uses builtin sqlite3 package.
"""

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
                if self._connectionName not in Qt.QSqlDatabase.connectionNames():
                    break
                c += 1
        else:
            self._connectionName = os.path.abspath(fileName)
            
        if self._connectionName not in Qt.QSqlDatabase.connectionNames():
            self.db = Qt.QSqlDatabase.addDatabase("QSQLITE", self._connectionName)
        else:
            self.db = Qt.QSqlDatabase.database(self._connectionName)
            
            
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
        #Qt.QSqlDatabase.removeDatabase(self._connectionName)

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
        
        q = Qt.QSqlQuery(self.db)
        if data is None:
            self._exe(q, cmd)
            p.mark("Executed with no data")
        else:
            data = TableData(data)
            res = []
            if not q.prepare(cmd):
                print("SQL Query:\n    %s" % cmd)
                raise Exception("Error preparing SQL query (query is printed above): %s" % str(q.lastError().text()))
            p.mark("Prepared query")
            if batch:
                for k in data.columnNames():
                    q.bindValue(':'+k, data[k])
                self._exe(q, batch=True)
                    
            else:
                for d in data:
                    #print len(d)
                    for k, v in d.items():
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
        p.finish()
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
            #if isinstance(columns, six.string_types):
                #columns = columns.split(',')
            if not isinstance(columns, six.string_types):
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
        p.finish()
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
        
    def insert(self, table, records=None, replaceOnConflict=False, ignoreExtraColumns=False, **args):
        """Insert records (a dict or list of dicts) into table.
        If records is None, a single record may be specified via keyword arguments.
        
        ====================  =======================================
        **Arguments:**
        table                 Name of the table to insert into
        records               Data to insert. May be a variety of formats: numpy record array, list of dicts,
                              dict of lists, dict of values (single record)
        replaceOnConflict     If True, inserts that conflict with pre-existing data will overwrite the
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
                print("Insert %d%% complete" % (100. * n / nmax))
        
        Use the chunkSize argument to determine how many records are inserted per iteration.
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

            columns = list(records.keys())
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

        p.finish()

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
        return list(q[0].values())[0]

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
        for name, conf in columns.items():
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
        if isinstance(columns, six.string_types):
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
        return list(self.tables.keys())
 
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
                print("SQL Query:\n    %s" % cmd)
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
        for k,v in where.items():
            if isinstance(v, six.string_types):
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
                converters[k] = lambda obj: Qt.QByteArray(pickle.dumps(obj))
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
                            print("Warning: Setting %s column %s.%s with type %s" % (schema[k], table, k, str(type(rec[k]))))
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
        while next(q):
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
        for i in range(1, len(recs)):
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
                if HAVE_QVARIANT and isinstance(val, Qt.QVariant):
                    t = val.type()
                    if t in [Qt.QVariant.Int, Qt.QVariant.LongLong]:
                        val = val.toInt()[0]
                    if t in [Qt.QVariant.Double]:
                        val = val.toDouble()[0]
                    elif t == Qt.QVariant.String:
                        val = six.text_type(val.toString())
                    elif t == Qt.QVariant.ByteArray:
                        val = val.toByteArray()
                        
                ## Unpickle byte arrays into their original objects.
                ## (Hopefully they were stored as pickled data in the first place!)
                if isinstance(val, Qt.QByteArray):
                    val = pickle.loads(str(val))
            data[n] = val
        prof.finish()
        return data

    def _readTableList(self):
        """Reads the schema for each table, extracting the column names and types."""
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
