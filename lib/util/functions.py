# -*- coding: utf-8 -*-
"""
functions.py - Miscellaneous homeless functions 
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

import os, re, math, time, threading
from metaarray import *
from scipy import *
from scipy.optimize import leastsq


## Number <==> string conversion functions

SI_PREFIXES = u'yzafpnµm kMGTPEZY'

def siFormat(x, precision=3, space=True, error=None, minVal=1e-25, suffix=''):
    """Return the number x formatted in engineering notation with SI prefix."""
    if space is True:
        space = ' '
    if space is False:
        space = ''
        
    if abs(x) < minVal:
        m = 0
        x = 0
    else:
        m = int(clip(floor(log(abs(x))/log(1000)), -9.0, 9.0))
    
    if m == 0:
        pref = space
    elif m < -8 or m > 8:
        pref = 'e%d' % (m*3)
    else:
        pref = space + SI_PREFIXES[m+8]
    p = .001**m
    if error is None:
        fmt = "%." + str(precision) + "g%s%s"
        return fmt % (x*p, pref, suffix)
    else:
        plusminus = space + u"±" + space
        fmt = "%." + str(precision) + u"g%s%s%s%s"
        return fmt % (x*p, pref, suffix, plusminus, siFormat(error, precision, space, minVal=minVal, suffix=suffix))
    
def siEval(s):
    """Convert a value written in SI notation to its equivalent prefixless value"""
    m = re.match(r'(-?((\d+(\.\d*)?)|(\.\d+))([eE]-?\d+)?)\s*([u' + SI_PREFIXES + r']?)', s)
    if m is None:
        raise Exception("Can't convert string '%s' to number." % s)
    v = float(m.groups()[0])
    p = m.groups()[6]
    #if p not in SI_PREFIXES:
        #raise Exception("Can't convert string '%s' to number--unknown prefix." % s)
    if p ==  '':
        n = 0
    elif p == 'u':
        n = -2
    else:
        n = SI_PREFIXES.index(p) - 8
    return v * 1000**n
    








## the built in logspace function is pretty much useless.
def logSpace(start, stop, num):
    num = int(num)
    d = (stop / start) ** (1./num)
    return start * (d ** arange(0, num+1))

def linSpace(start, stop, num):
    return linspace(start, stop, num)

def alpha(t, tau):
    """Return the value of an alpha function at time t with width tau."""
    t = max(t, 0)
    return (t / tau) * math.exp(1.0 - (t / tau));

def alphas(t, tau, starts):
    tot = 0.0
    for s in starts:
        tot += alpha(t-s, tau)
    return tot

### TODO: replace with faster scipy filters
def smooth(data, it=1):
    data = data.view(ndarray)
    d = empty((len(data)), dtype=data.dtype)
    for i in range(0, len(data)):
        start = max(0, i-1)
        stop = min(i+1, len(data)-1)
        d[i] = mean(data[start:stop+1])
    if it > 1:
        return smooth(d, it-1)
    else:
        return d

def maxDenoise(data, it):
    return smooth(data, it).max()

def absMax(data):
    mv = 0.0
    for v in data:
        if abs(v) > abs(mv):
            mv = v
    return mv

# takes data in form of [[t1, y1], [t2, y2], ...]
def triggers(data, trig):
    """Return a list of places where data crosses trig
    Requires 2-column array:  array([[time...], [voltage...]])"""
    
    tVals = []
    for i in range(0, data.shape[1]-1):
        v1 = data[1, i]
        v2 = data[1, i+1]
        if v1 <= trig and v2 > trig:
            g1 = data[0,i]
            g2 = data[0,i+1]
            tVals.append(g1 + (g2-g1)*((0.5-v1)/(v2-v1)))
    return tVals


def rmsMatch(template, data, thresh=0.75):
    data = data.view(ndarray)
    template = template.view(ndarray)
    tlen = template.shape[0]
    length = data.shape[0] - tlen
    devs = empty((length), dtype=float)
    
    for i in range(0, length):
        dif = template - data[i:i+tlen]
        devs[i] = dif.std()
    
    tstd = template.std()
    blocks = argwhere(devs < thresh * tstd)[:, 0]
    if len(blocks) == 0:
        return []
    inds = list(argwhere(blocks[1:] - blocks[:-1] > 1)[:,0] + 1)
    inds.insert(0, 0)
    return blocks[inds]


def fastRmsMatch(template, data, thresholds=[0.85, 0.75], scales=[0.2, 1.0], minTempLen=4):
    """Do multiple rounds of rmsMatch on scaled-down versions of the data set"""
    
    data = data.view(ndarray)
    template = template.view(ndarray)
    tlen = template.shape[0]
    
    inds = None
    inds2 = None
    lastScale = None
    
    for i in range(0, len(scales)):
        ## Decide on scale to use for this iteration
        t1len = max(minTempLen, int(scales[i]*tlen))
        scale = float(t1len)/float(tlen)
        
        ## scale down data sets
        if scale == 1.0:
            t1 = template
            data1 = data
        else:
            t1 = signal.signaltools.resample(template, t1len)
            data1 = signal.signaltools.resample(data, int(data.shape[0] * scale))
        
        ## find RMS matches
        if inds is None:
            inds = rmsMatch(t1, data1, thresholds[i])
        else:
            ix = ceil(scale/lastScale)
            inds = ((inds*scale) - ix).astype(int)
            span = 2*ix + t1len
            inds2 = []
            for ind in inds:
                d = data1[ind:ind+span]
                m = rmsMatch(t1, d, thresholds[i])
                for n in m:
                    inds2.append(ind+n)
            inds = inds2
        lastScale = scale
        inds = (array(inds) / scale).round()
    return inds.astype(int)




## generates a command data structure from func with n points
def cmd(func, n, time):
    return [[i*(time/float(n-1)), func(i*(time/float(n-1)))] for i in range(0,n)]


def inpRes(data, v1Range, v2Range):
    r1 = filter(lambda r: r['Time'] > v1Range[0] and r['Time'] < v1Range[1], data)
    r2 = filter(lambda r: r['Time'] > v2Range[0] and r['Time'] < v2Range[1], data)
    v1 = mean([r['voltage'] for r in r1])
    v2 = min(smooth([r['voltage'] for r in r2], 10))
    c1 = mean([r['current'] for r in r1])
    c2 = mean([r['current'] for r in r2])
    return (v2-v1)/(c2-c1)


def findActionPots(data, lowLim=-20e-3, hiLim=0, maxDt=2e-3):
    """Returns a list of indexes of action potentials from a voltage trace
    Requires 2-column array:  array([[time...], [voltage...]])
    Defaults specify that an action potential is when the voltage trace crosses 
    from -20mV to 0mV in 2ms or less"""
    data = data.view(ndarray)
    lastLow = None
    ap = []
    for i in range(0, data.shape[1]):
        if data[1,i] < lowLim:
            lastLow = data[0,i]
        if data[1,i] > hiLim:
            if lastLow != None and data[0,i]-lastLow < maxDt:
                ap.append(i)
                lastLow = None
    return ap

def getSpikeTemplate(ivc, traces):
    """Returns the trace of the first spike in an IV protocol"""
    
    ## remove all negative currents
    posCurr = argwhere(ivc['current'] > 0.)[:, 0]
    ivc = ivc[:, posCurr]
    
    ## find threshold index
    ivd = ivc['max voltage'] - ivc['mean voltage']
    ivdd = ivd[1:] - ivd[:-1]
    thrIndex = argmax(ivdd) + 1 + posCurr[0]
    
    ## subtract spike trace from previous trace
    minlen = min(traces[thrIndex].shape[1], traces[thrIndex-1].shape[1])
    di = traces[thrIndex]['Inp0', :minlen] - traces[thrIndex-1]['Inp0', :minlen]
    
    ## locate tallest spike
    ind = argmax(di)
    maxval = di[ind]
    start = ind
    stop = ind
    while di[start] > maxval*0.5:
        start -= 1
    while di[stop] > maxval*0.5:
        stop += 1
    
    return traces[thrIndex][['Time', 'Inp0'], start:stop]
    
def fitSigmoid(xVals, yVals, guess=[1.0, 0.0, 1.0, 0.0]):
    """Returns least-squares fit parameters for function v[2] / (1.0 + exp(-v[0] * (x-v[1]))) + v[3]"""
    fn = lambda v, x: v[2] / (1.0 + exp(-v[0] * (x-v[1]))) + v[3]
    err = lambda v, x, y: fn(v, x)-y
    return leastsq(err, guess, args=(xVals, yVals))


STRNCMP_REGEX = re.compile(r'(-?\d+(\.\d*)?((e|E)-?\d+)?)')
def strncmp(a, b):
    """Compare strings based on the numerical values they represent (for sorting). Each string may have multiple numbers."""
    global STRNCMP_REGEX
    am = STRNCMP_REGEX.findall(a)
    bm = STRNCMP_REGEX.findall(b)
    if len(am) > 0 and len(bm) > 0:
        for i in range(0, len(am)):
            c = cmp(float(am[i][0]), float(bm[i][0]))
            if c != 0:
                return c
    return cmp(a, b)

def downsample(data, n, axis):
    nPts = int(data.shape[axis] / n)
    s = list(data.shape)
    s[axis] = nPts
    s.insert(axis+1, n)
    sl = [slice(None)] * data.ndim
    sl[axis] = slice(0, nPts*n)
    d1 = data[tuple(sl)]
    #print d1.shape, s
    d1.shape = tuple(s)
    return d1.mean(axis+1)
        


