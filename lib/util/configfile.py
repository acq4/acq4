# -*- coding: utf-8 -*-
"""
configfile.py - Human-readable text configuration file library 
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

Used for reading and writing dictionary objects to a python-like configuration
file format. Data structures may be nested and contain any data type as long
as it can be converted to/from a string using repr and eval.
"""

import re, os
from advancedTypes import OrderedDict
GLOBAL_PATH = None # so not thread safe.

def writeConfigFile(data, fname):
    s = genString(data)
    fd = open(fname, 'w')
    fd.write(s)
    fd.close()
    
def readConfigFile(fname):
    #cwd = os.getcwd()
    global GLOBAL_PATH
    if GLOBAL_PATH is not None:
        fname2 = os.path.join(GLOBAL_PATH, fname)
        if os.path.exists(fname2):
            fname = fname2
            
    GLOBAL_PATH = os.path.dirname(os.path.abspath(fname))
        
    try:
        #os.chdir(newDir)  ## bad.
        fd = open(fname)
        s = unicode(fd.read(), 'UTF-8')
        fd.close()
        s = s.replace("\r", "")
        data = parseString(s)[1]
    except:
        print "Error while reading config file %s:"% fname
        raise
    #finally:
        #os.chdir(cwd)
    return data

def appendConfigFile(data, fname):
    s = genString(data)
    fd = open(fname, 'a')
    fd.write(s)
    fd.close()


def genString(data, indent=''):
    s = ''
    for k in data:
        sk = str(k)
        if len(sk) == 0:
            print data
            raise Exception('blank dict keys not allowed (see data above)')
        if sk[0] == ' ' or ':' in sk:
            print data
            raise Exception('dict keys must not contain ":" or start with spaces [offending key is "%s"]' % sk)
        if isinstance(data[k], dict):
            s += indent + sk + ':\n'
            s += genString(data[k], indent + '    ')
        else:
            s += indent + sk + ': ' + repr(data[k]) + '\n'
    return s
    
def parseString(lines, start=0):
    
    data = OrderedDict()
    if isinstance(lines, basestring):
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
        if k[0] == '(' and k[-1] == ')':
            try:
                k1 = eval(k)
                if type(k1) is tuple:
                    k = k1
            except:
                pass
        if re.search(r'\S', v):
            try:
                val = eval(v)
            except:
                print "Error evaluating expression at config line %d" % (ln+1)
                raise
        else:
            if ln+1 >= len(lines) or measureIndent(lines[ln+1]) <= indent:
                #print "blank dict"
                val = {}
            else:
                #print "Going deeper..", ln+1
                (ln, val) = parseString(lines, start=ln+1)
        data[k] = val
        #print k, repr(val)
    #print "Returning shallower..", ln+1
    return (ln, data)
    
def measureIndent(s):
    n = 0
    while n < len(s) and s[n] == ' ':
        n += 1
    return n