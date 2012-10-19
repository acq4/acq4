# -*- coding: utf-8 -*-
"""
I keep data about each cell in cell_overview.ods.

This script reads cell values fomr that file and inserts them into the sqlite DB.
"""

import lib.Manager
import ooolib
import re
import pyqtgraph as pg

odsFile = "/home/luke/data/analysis/cell_overview.ods"

## Functions for massaging cell values into DB values
def splitStd(x):
    ## extract numbers from strings like this: "-16.4pA±7.28pA"
    if x is None or x == '-' or '?' in x:
        return None, None
    if u'±' in x:
        x1, x2 = x.split(u'±')
        return pg.siEval(x1), pg.siEval(x2)
    else:
        return pg.siEval(x.lstrip('~')), None
    
def stripUnits(x):
    if x is None or x == '-' or '?' in x:
        return [None]
    x = x.lstrip('~')
    return [pg.siEval(x)]
    

columns = [
    # ODS column header, DB column name, [filter]
    ('cell', None),
    ('type', [('CellType', 'text')]),
    ('slice plane', None),
    ('atlas ok', None),
    ('morphology', None),
    ('I/V Curves', None),
    ('temp', None),
    ('region', None),
    ('H-current', None),
    ('time post-dissection', None),
    ('electrode res.', None),
    ('input res.', None),
    ('access res.', None),
    ('capacitance', None),
    ('holding cur.', None),
    ('time to peak', None),
    ('decay 1', None),
    ('decay 2', None),
    ('area &gt;0, &gt;20, &gt;100', None),
    ('n spikes', None),
    ('latency', None),
    ('rise',    [('SpontExRise', 'real'),   ('SpontExRiseStd', 'real')],   splitStd ),
    ('decay 1', [('SpontExDecay1', 'real'), ('SpontExDecay1Std', 'real')], splitStd ),
    ('decay 2', [('SpontExDecay2', 'real'), ('SpontExDecay2Std', 'real')], splitStd ),
    ('amp',     [('SpontExAmp', 'real'),    ('SpontExAmpStd', 'real')],    splitStd ),
    ('rate',    [('SpontExRate', 'real')],  stripUnits ),
    ('rise',    [('SpontInRise', 'real'),   ('SpontInRiseStd', 'real')],   splitStd ),
    ('decay',   [('SpontInDecay', 'real'),  ('SpontInDecayStd', 'real')],  splitStd ),
    ('amp',     [('SpontInAmp', 'real'),    ('SpontInAmpStd', 'real')],    splitStd ),
    ('rate',    [('SpontInRate', 'real')],  stripUnits ),
    ('rise', None),
    ('decay', None),
    ('amp', None),
    ('n', None),
    ('rise', None),
    ('decay', None),
    ('amp', None),
    ('n', None),
    ('rise', None),
    ('decay', None),
    ('amp', None),
    ('n', None),
    ('in str', None),
    ('ex str', None),
    ('tv str', None),
    ('ex rate', None),
    ('direct spikes', None),
    ('direct latency', None),
    ('slow direct?', None),
    ('Direct area', None),
    ('AVCN area', None),
    ('DCN area', None),
    ('isofreq aligned', None),
    ('bias', None),
    ('TV?', None),
    ('Ex input?', None),
    ('GCA?', None),
    ('None', None),
    ('age', None),
    ('mcpg', None),
]

## for generating column list
#for h in data[1]:
    #print "    ('%s', None)," % h

def readOds():
    global odsFile
    doc = ooolib.Calc(opendoc=odsFile)
    doc.set_sheet_index(0)
    (cols, rows) = doc.get_sheet_dimensions()
    
    ## make sure ODS data matches column list
    for i in range(cols):
        d = doc.get_cell_value(i+1, 2)
        if d != columns[i]:
            raise Exception('Column %d in ODS (%s) does not match template (%s)' % (i+1, d, columns[i]) )
    if cols != len(columns):
        raise Exception('Expected number of columns (%d) does not match number of columns in ODS (%d)' % (cols, len(columns)))
    
    data = []
    for row in range(3, rows + 1):
        data.append([])
        for col in range(1, cols + 1):
            d = doc.get_cell_value(col, row)
            if isinstance(d, tuple):
                if d[0] == 'string':
                    d = d[1]
                elif d[0] == 'float':
                    d = float(d[1])
                else:
                    raise Exception("unknown cell data type: %s" % d[0])
            data[-1].append(d)
            #print data[-1][-1],
        #print
    return data

    

def sync():
    man = lib.Manager.getManager()
    data = readOds()
    db = man.getModule('Data Manager').currentDatabase() 
    table = 'DirTable_Cell'
    tableCols = db.tableSchema(table)
    
    ## make sure DB has all the columns we need
    for col in columns:
        if col[1] is None:
            continue
        for name, typ in col[1]:
            if name not in tableCols:
                db.addColumn(table, name, typ)
    
    for rec in data[2:]:
        
        ## get the cell's dir handle for this record
        parts = rec[0].split(' ')
        if len(parts) == 2:
            parts = (parts[0], 's0', parts[1])
        day, slice, cell = parts
        if '_' not in day:
            day = day + '_000'
        slice = 'slice_%03d' % int(slice.lstrip('s'))
        cell = 'cell_%03d' % int(cell.lstrip('c'))
        cell = '%s/%s/%s' % (day, slice, cell)
        dh = man.baseDir[cell]
        
        ## generate new record data
        newRec = {}
        for i, col in enumerate(columns):
            
            ## process this cell into storable data
            if col[1] is None:
                continue
            if len(col) == 3:
                vals = col[2](rec[i])
            else:
                vals = [rec[i]]
            
            ## add values to new record
            for j in range(len(col[1])):
                newRec[col[1][j][0]] = vals[j]
        
        
        ## update table
        #print "Update:", dh, newRec
        db.update(table, newRec, where={'Dir': dh})
        
    