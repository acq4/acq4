# -*- coding: utf-8 -*-
import re, os
from advancedTypes import OrderedDict

def writeConfigFile(data, fname):
    s = genString(data)
    fd = open(fname, 'w')
    fd.write(s)
    fd.close()
    
def readConfigFile(fname):
    cwd = os.getcwd()
    (newDir, fname) = os.path.split(os.path.abspath(fname))
    try:
        os.chdir(newDir)
        fd = open(fname)
        s = fd.read()
        fd.close()
        data = parseString(s)[1]
    finally:
        os.chdir(cwd)
    return data




def genString(data, indent=''):
    s = ''
    for k in data:
        sk = str(k)
        if len(sk) == 0:
            raise Exception('blank dict keys not allowed')
        if sk[0] == ' ' or ':' in sk:
            raise Exception('dict keys must not contain ":" or start with spaces [offending key is "%s"]' % sk)
        if type(data[k]) in [dict, OrderedDict]:
            s += indent + sk + ':\n'
            s += genString(data[k], indent + '    ')
        else:
            s += indent + sk + ': ' + repr(data[k]) + '\n'
    return s
    
def parseString(lines, start=0):
    #data = {'__order__': []}
    data = OrderedDict()
    if type(lines) is str:
        lines = lines.split('\n')
        
    indent = measureIndent(lines[start])
    ln = start - 1
    
    while True:
        ln += 1
        #print ln
        if ln >= len(lines):
            break
        
        l = lines[ln]
        
        ## Skip blank lines or lines starting with #
        if re.match(r'\s*#', l) or not re.search(r'\S', l):
            continue
        
        ## Measure line indentation, make sure it is correct for this level
        lineInd = measureIndent(l)
        if lineInd < indent:
            
            ln -= 1
            break
        if lineInd > indent:
            #print lineInd, indent
            raise Exception('Error processing config file around line %d (indent is too deep)' % (ln+1), lineInd, indent)
        
        
        if ':' not in l:
            raise Exception('config line %d has no colon' % (ln+1))
        
        (k, p, v) = l.partition(':')
        k = k.lstrip()
        if re.search(r'\S', v):
            try:
                val = eval(v)
            except:
                print "Error evaluating expression at config line %d" % (ln+1)
                raise
        else:
            if ln+1 >= len(lines) or measureIndent(lines[ln+1]) == indent:
                val = {}
            else:
                #print "Going deeper..", ln+1
                (ln, val) = parseString(lines, start=ln+1)
        data[k] = val
        #print k, repr(val)
        #data['__order__'].append(k)
    #print "Returning shallower..", ln+1
    return (ln, data)
    
def measureIndent(s):
    n = 0
    while n < len(s) and s[n] == ' ':
        n += 1
    return n