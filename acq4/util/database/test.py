from __future__ import print_function
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
    columns = list(db.tableSchema('t').keys())
    print(columns)


    ## Test insertion and retrieval of different data types into each column type
    vals = [
        ('int', (1,)*5), 
        ('float', (1.5,)*5), 
        ('int-float', (10.0,)*5), 
        ('int-string', ('10',)*5), 
        ('float-string', ('3.1415',)*5), 
        ('string', ('Stringy',)*5), 
        ('object', (None, None, [1,'x'], [1,'x'], None)), 
        ('byte-string', ('str\1\2\0str',)*5),
        ('None', (None,)*5),
    ]

    expect = [
        (1, 1.0, u'1', 1, 1),
        (1, 1.5, u'1.5', 1.5, 1.5),
        (10, 10.0, u'10.0', 10.0, 10),
        (10, 10.0, u'10', '10', 10),
        (3.1415, 3.1415, u'3.1415', '3.1415', 3.1415),
        (u'Stringy', u'Stringy', u'Stringy', 'Stringy', u'Stringy',),
        (None, None, u"[1, 'x']", [1, 'x'], None),
        (u'str\1\2\0str', u'str\1\2\0str', u'str\1\2\0str', 'str\x01\x02\x00str', u'str\1\2\0str'),
        (None,)*5,
    ]

    for i, nv in enumerate(vals):
        name, val = nv
        db('delete from t')
        db.insert('t', **dict(zip(columns, val)))
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
        db.insert('t', **dict(zip(columns, val)))
    result =  db.select('t', toArray=True)

    expect = np.array([(None,)*5] + expect, 
       dtype=[('int', 'O'), ('real', 'O'), ('text', 'O'), ('blob', 'O'), ('other', 'O')])
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
