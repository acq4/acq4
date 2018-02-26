# -*- coding: utf-8 -*-
from __future__ import print_function
"""
I keep data about each cell in cell_overview.ods.

This script reads cell values fomr that file and inserts them into the sqlite DB.
"""

import acq4.Manager
import ooolib
import re
import acq4.pyqtgraph as pg

## Read data from this ODS file:
odsFile = "/home/luke/data/analysis/cell_overview.ods"
## Write data into this DB table:
DBTable = 'DirTable_Cell'

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
    x.replace('%', '')  
    return [pg.siEval(x)]
    
def splitPair(x):
    ## extract two values from strings like "10ms 30pA"
    if x is None or x == '-' or '?' in x:
        return None, None
    a,b = x.strip().split(' ')
    return stripUnits(a)[0], stripUnits(b)[0]

def splitCsv3(x):
    ## extract 3 comma-separated values
    if x is None or x == '-' or '?' in x:
        return None, None, None
    return list(map(float, x.strip().split(',')))
    
def toInt(x):
    if not isinstance(x, float) and (x is None or x == '-' or '?' in x):
        return [None]
    return [int(x)]

def fiType(x):
    ## Convert B/S IVcurve types to 0 or 1
    if x == 'B':
        return [0]
    elif x == 'S':
        return [1]
    else:
        return [None]
    
def temperature(x):
    try: 
        return[float(x)]
    except:
        if x == 'RT':
            return [20.]
        else:
            return [None]

def yesno(x):
    if x.startswith('yes'):
        return [1.0]
    elif x.startswith('no'):
        return [-1.0]
    else:
        return [None]
    
def access(x):
    if x == '-':
        return [None]
    else:
        return [float(x) * 1e6]

## List of all columns in the ODS file.
## Each column name is followed by one of:
##    None, indicating the column should be ignored
##    List of ('fieldName', 'type') and an optional function for mapping from the ODS cell's value to the DB value(s).

columns = [
    # ODS column header, DB column name, [filter]
    ('cell', None),
    ('type', [('CellType', 'text')]),
    ('slice plane', [('SlicePlane', 'text')]),
    ('internal', [('Internal', 'text')]),
    ('mcpg', [('MCPG', 'real')], yesno),
    ('atlas ok', [('AtlasOK', 'real')], yesno),
    ('mapping ok', [('MapOK', 'real')], yesno),
    ('DCN map ok', [('DCNMapOK', 'real')], yesno),
    ('Ex map OK', [('ExMapOK', 'real')], yesno),
    ('morphology ok', [('MorphologyOK', 'real')], yesno),
    ('Ra IV', None),
    ('Ra ex', None),
    ('Ra in', None),
    ('Ra', [('AccessResistance', 'real')], access),
    ('VC IH decay @ -100mV', [('IVCurve_VC_100_Htau', 'real')], stripUnits),
    ('VC IH fast decay @ -130mV', [('IVCurve_VC_130_Htau_fast', 'real')], stripUnits),
    ('morphology', [('Morphology', 'text')]),
    ('Mean', [('MorphologyBSMean', 'real')]),
    ('Stdev', [('MorphologyBSStdev', 'real')]),
    ('Mean', [('MorphologyTDMean', 'real')]),
    ('Stdev', [('MorphologyTDStdev', 'real')]),
    ('tracing', None),
    ('Ex Profile', None),
    ('I/V Curves', [('FIType', 'real')], fiType),
    ('temp', [('Temperature', 'real')], temperature),
    ('age', [('Age', 'real')]),
    #('region', None),
    #('time post-dissection', None),
    #('electrode res.', None),
    #('access res.', None),
    #('holding cur.', None),
    ('time to peak', [('DirectTimeToPeak', 'real')], stripUnits),
    ('decay 1', [('DirectDecayTau1', 'real'), ('DirectDecayAmp1', 'real')], splitPair),
    ('decay 2', [('DirectDecayTau2', 'real'), ('DirectDecayAmp2', 'real')], splitPair),
    ('area &gt;0, &gt;20, &gt;100', [('DirectAreaGt0', 'int'), ('DirectAreaGt20', 'int'), ('DirectAreaGt100', 'int')], splitCsv3),
    ('n spikes', [('DirectNSpikes', 'int')], toInt),
    ('latency', [('DirectSpikeLatency', 'real')], stripUnits),
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
    ('decay', [('EvokedExDecay', 'real')], stripUnits),
    ('amp', [('EvokedExAmp', 'real')], stripUnits),
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
    ('AVCN area', None),
    ('DCN area', None),
    ('isofreq aligned', None),
    ('bias', None),
    ('TV?', None),
    ('Ex input?', None),
    ('GCA?', None),
]

## for initially generating column list:
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
        if d is not None:
            d = d[1]
        if d != columns[i][0]:
            raise Exception('Column %d in ODS (%s) does not match template (%s)' % (i+1, d, columns[i][0]) )
    if cols != len(columns):
        raise Exception('Expected number of columns (%d) does not match number of columns in ODS (%d)' % (cols, len(columns)))
    
    data = []
    for row in range(3, rows + 1):
        if doc.get_cell_value(1, row) == ('string', '__end__'):
            break
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
    global DBTable
    man = acq4.Manager.getManager()
    data = readOds()
    db = man.getModule('Data Manager').currentDatabase() 
    table = DBTable
    tableCols = db.tableSchema(table)
    
    ## make sure DB has all the columns we need
    for col in columns:
        if col[1] is None:
            continue
        for name, typ in col[1]:
            if name not in tableCols:
                db.addColumn(table, name, typ)
    
    for rec in data:
        
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
        
    