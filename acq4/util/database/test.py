import os, sys
path = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(path, '..', '..', '..'))

import numpy as np
from acq4.util.database.database import SqliteDatabase


def testDataRetrieval():
    """Check that data can be inserted and retrieved from a table correctly
    """
    db = SqliteDatabase()
    db("create table 't' ('int' int, 'real' real, 'text' text, 'blob' blob, 'other' other)")
    columns = db.tableSchema('t').keys()
    print columns


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

    expect = [
        (1L, 1.0, u'1', 1, 1L),
        (1L, 1.5, u'1.5', 1.5, 1.5),
        (10L, 10.0, u'10.0', 10.0, 10L),
        (10L, 10.0, u'10', '10', 10L),
        (3.1415, 3.1415, u'3.1415', '3.1415', 3.1415),
        (u'Stringy', u'Stringy', u'Stringy', 'Stringy', u'Stringy',),
        (u'', u'', u"[1, 'x']", [1, 'x'], u''),
        (u'str\x01\x02', u'str\x01\x02', u'str\x01\x02', 'str\x01\x02\x00str', u'str\x01\x02'),
        (None,)*5,
    ]

    for i, nv in enumerate(vals):
        name, val = nv
        db('delete from t')
        db.insert('t', **dict([(f, val) for f in columns]))
        result = db.select('t')[0]
        for j,v in enumerate(result.values()):
            assert type(v) == type(expect[i][j])
            assert v == expect[i][j]
        
    #print "\nTable extraction test:"
    db('delete from t')
    # insert Nones as first row; this causes array to be created with object dtype for all fields 
    # (otherwise we get an error because in this test, we insert the wrong data types
    # into fields..)
    db.insert('t', **dict([(f, None) for f in columns]))

    for name, val in vals:
        db.insert('t', **dict([(f, val) for f in columns]))
    result =  db.select('t', toArray=True)

    expect = np.array([
        (None, None, None, None, None),
        (1L, 1.0, u'1', 1, 1L),
        (1L, 1.5, u'1.5', 1.5, 1.5),
        (10L, 10.0, u'10.0', 10.0, 10L),
        (10L, 10.0, u'10', '10', 10L),
        (3.1415, 3.1415, u'3.1415', '3.1415', 3.1415),
        (u'Stringy', u'Stringy', u'Stringy', 'Stringy', u'Stringy'),
        (u'', u'', u"[1, 'x']", [1, 'x'], u''),
        (u'str\x01\x02', u'str\x01\x02', u'str\x01\x02', 'str\x01\x02\x00str', u'str\x01\x02'),
        (None, None, None, None, None)
    ], dtype=[('int', 'O'), ('real', 'O'), ('text', 'O'), ('blob', 'O'), ('other', 'O')])
    assert all(result == expect)


def testBatchInsert():
    db = SqliteDatabase()
    db("create table 't' ('int' int, 'real' real, 'text' text, 'blob' blob, 'other' other)")
    
    data = np.array([
        (1, 27.3, u'x', [5], None),
        (3, 23.4, u'yy', None, None),
        (5, 21.3, u'zzz', [(5,3), 'q'], None),
        (7, 24.3, u'wwww', 'q', None),
    ], dtype=[('int', int), ('real', float), ('text', object), ('blob', object), ('other', object)])
    
    db.insert('t', data)
    
    result = db.select('t', toArray=True)
    assert np.all(result == data)
    
    for i, row in enumerate(db.iterSelect('t', limit=1)):
        assert tuple(row[0].values()) == tuple(data[i])
