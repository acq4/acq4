# -*- coding: utf-8 -*-
"""
functions.py - Miscellaneous homeless functions 
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

Most Interesting Contents:
siFormat / siEval  - functions for dealing with numbers in SI notation
downsample - multidimensional downsampling by mean
rmsMatch / fastRmsMatch - recursive template matching
makeDispMap / matchDistortImg - for measuring and correcting motion/distortion between two images


"""
import sys
import os, re, math, time, threading
from metaarray import *
from scipy import *
from scipy.optimize import leastsq
from scipy.ndimage import gaussian_filter, generic_filter
import scipy.signal
import numpy.ma

## Number <==> string conversion functions

SI_PREFIXES = u'yzafpnµm kMGTPEZY'

def siScale(x, minVal=1e-25):
    """Return the recommended scale factor and SI prefix string for x."""
    if abs(x) < minVal:
        m = 0
        x = 0
    else:
        m = int(clip(floor(log(abs(x))/log(1000)), -9.0, 9.0))
    
    if m == 0:
        pref = ''
    elif m < -8 or m > 8:
        pref = 'e%d' % (m*3)
    else:
        pref = SI_PREFIXES[m+8]
    p = .001**m
    
    return (p, pref)
    

def siFormat(x, precision=3, space=True, error=None, minVal=1e-25, suffix=''):
    """Return the number x formatted in engineering notation with SI prefix."""
    if space is True:
        space = ' '
    if space is False:
        space = ''
        
    (p, pref) = siScale(x, minVal)
    if not (len(pref) > 0 and pref[0] == 'e'):
        pref = space + pref
    
    if error is None:
        fmt = "%." + str(precision) + "g%s%s"
        return fmt % (x*p, pref, suffix)
    else:
        plusminus = space + u"±" + space
        fmt = "%." + str(precision) + u"g%s%s%s%s"
        return fmt % (x*p, pref, suffix, plusminus, siFormat(error, precision, space, minVal=minVal, suffix=suffix))
    
def siEval(s):
    """Convert a value written in SI notation to its equivalent prefixless value"""
    m = re.match(r'(-?((\d+(\.\d*)?)|(\.\d+))([eE]-?\d+)?)\s*([u' + SI_PREFIXES + r']?)$', s)
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

def sigmoid(v, x):
    """Sigmoid function value at x. the parameter v is [slope, x-offset, amplitude, y-offset]"""
    return v[2] / (1.0 + exp(-v[0] * (x-v[1]))) + v[3]
    
def gaussian(v, x):
    """Gaussian function value at x. The parameter v is [amplitude, x-offset, sigma, y-offset]"""
    return v[0] * exp(-((x-v[1])**2) / (2 * v[2]**2)) + v[3]

def fit(function, xVals, yVals, guess, errFn=None, generateResult=False, resultXVals=None):
    """fit xVals, yVals to the specified function. 
    If generateResult is True, then the fit is used to generate an array of points from function
    with the xVals supplied (useful for plotting the fit results with the original data). 
    The result x values can be explicitly set with resultXVals."""
    if errFn is None:
        errFn = lambda v, x, y: function(v, x)-y
    fit = leastsq(errFn, guess, args=(xVals, yVals))
    
    result = None
    if generateResult:
        if resultXVals is not None:
            xVals = resultXVals
        fn = lambda i: function(fit[0], xVals[i.astype(int)])
        result = fromfunction(fn, xVals.shape)
    return fit + (result,)
        
def fitSigmoid(xVals, yVals, guess=[1.0, 0.0, 1.0, 0.0], **kargs):
    """Returns least-squares fit for sigmoid"""
    return fit(sigmoid, xVals, yVals, guess, **kargs)

def fitGaussian(xVals, yVals, guess=[1.0, 0.0, 1.0, 0.0], **kargs):
    """Returns least-squares fit parameters for function v[0] * exp(((x-v[1])**2) / (2 * v[2]**2)) + v[3]"""
    return fit(gaussian, xVals, yVals, guess, **kargs)


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
    """Downsample by averaging points together across axis.
    If multiple axes are specified, runs once per axis."""
    if hasattr(axis, '__len__'):
        if not hasattr(n, '__len__'):
            n = [n]*len(axis)
        for i in range(len(axis)):
            data = downsample(data, n[i], axis[i])
        return data
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
        
def downsamplend(data, div):
    """Downsample multiple axes at once. Probably slower than just using downsample multiple times."""
    shape = [float(data.shape[i]) / div[i] for i in range(0, data.ndim)]
    res = empty(tuple(shape), dtype=float)
    
    for ind, i in ndenumerate(res):
        sl = [slice(ind[j]*div[j], (ind[j]+1)*div[j]) for j in range(0, data.ndim)]
        res[tuple(ind)] = data[tuple(sl)].mean()
    
    return res


def recursiveRegisterImages(i1, i2, hint=(0,0), maxDist=None, objSize=None):
    """Given images i1 and i2, recursively find the offset for i2 that best matches with i1"""
    time1 = time.clock()
    ## float images
    im1 = i1.mean(axis=2).astype(float)
    im2 = i2.mean(axis=2).astype(float)
    
    ## Decide how many iterations to perform, scale images
    if objSize != None:
        nit = int(floor(log(objSize)/log(2)) + 1)
    else:
        nit = 5
    print "Doing %d iterations" % nit
    
    spow = 2.0
    scales = map(lambda x: 1.0 / spow**x, range(nit-1,-1,-1))
    imScale = [[None, None]] * nit
    imScale[-1] = [im1, im2]
    time2 = time.clock()
    for i in range(nit-2,-1,-1):
        imScale[i] = [ndimage.zoom(imScale[i+1][0], 1.0/spow, order=1), ndimage.zoom(imScale[i+1][1], 1.0/spow, order=1)]
    print scales

    time3 = time.clock()
    lastSf = None
    if maxDist != None:
        start = (array(hint) - ceil(maxDist / 2.)) * scales[0]
        end = (array(hint) + ceil(maxDist / 2.)) * scales[0]
    else:
        start = array([0,0])
        end = None
        
    print "Checking range %s - %s" % (str(start), str(end))
    for i in range(0, nit):
        sf = scales[i]
        im1s = imScale[i][0]
        im2s = imScale[i][1]
        
        if lastSf != None:
            start = floor(floor(center-0.5) * sf / lastSf)
            end = ceil(ceil(center+0.5) * sf / lastSf)
        ## get prediction
        #print "Scale %f: start: %s  end: %s" % (sf, str(start), str(end))
        if any(start != end):
            center = registerImages(im1s, im2s, start, end)
        #print "   center = %s" % str(center/sf)
        
        
        lastSf = sf
    time4 = time.clock()
    print "Scale time: %f   Corr time: %f    Total: %f" % (time3-time2, time4-time3, time4-time1)
    return center

def xcMax(xc):
    mi = scipy.where(xc == xc.max())
    mi = scipy.array([mi[0][0], mi[1][0]])
    return mi

def registerImages(im1, im2, searchRange):
    #print "Registering images %s and %s, %s-%s" % (str(im1.shape), str(im2.shape), str(start), str(end))
    (sx, sy) = searchRange
    start=[sx[0], sy[0]]
    end = [sx[1], sy[1]]
    if end == None:
        mode='full'
        im1c = im1
        im2c = im2
        #print "Searching full images."
    else:
        mode='valid'
        s1x = max(0, start[0])
        s1y = max(0, start[1])
        e1x = min(im1.shape[0], im2.shape[0]+end[0])
        e1y = min(im1.shape[1], im2.shape[1]+end[1])
        #print "%d,%d - %d,%d" % (s1x, s1y, e1x, e1y)
        
        s2x = max(0, -start[0])
        s2y = max(0, -start[1])
        e2x = min(im2.shape[0], im1.shape[0]-end[0])
        e2y = min(im2.shape[1], im1.shape[1]-end[1])
        #print "%d,%d - %d,%d" % (s2x, s2y, e2x, e2y)
        
        ## Crop images
        im1c = im1[s1x:e1x, s1y:e1y]
        im2c = im2[s2x:e2x, s2y:e2y]
            
        #print "Images cropped to %d,%d-%d,%d   %d,%d-%d,%d" % (s1x, s1y, e1x, e1y, s2x, s2y, e2x, e2y)

    #showImage(im1c)
    #showImage(im2c)
    
    ## get full scale correlation
    
    #turns out cross-correlation is a really lousy way to register images.
    #xc = scipy.signal.signaltools.correlate2d(im1c, im2c, boundary='fill', fillvalue=im1c.mean(), mode=mode)
    def err(img):
        img.shape = im2c.shape
        return abs(im2c - img).sum()
    xc = generic_filter(im1c, err, footprint=im2c) 
    print xc.min(), xc.max()
    #xcb = ndimage.filters.gaussian_filter(xc, 20)
    #xc -= xcb
    
    xcm = argmin(xc)
    #xcm = xcMax(xc)
    #xcc = concatenate((xc[...,newaxis], xc[...,newaxis], xc[...,newaxis]), axis=2)
    #xcc[xcm[0], xcm[1], 0:2] = xc.min()
    #showImage(xcc)
    #showImage(xcb)
    
    #print "Best match at " + str(xcm)
    if mode == 'full':
        xcm -= array(im1c.shape)-1
    else:
        xcm += start
    #print "  ..corrected to " + str(xcm)
    
    #showImage(regPair(im1, im2, xcm))
    return xcm

def regPair(im1, im2, reg):
    if len(im1.shape) > 2:
        im1 = im1[...,0]
        im2 = im2[...,0]
    ## prepare blank images
    mn = min(im1.min(), im2.min())
    mx = max(im1.max(), im2.max())
    w = (im1.shape[0]+im2.shape[0])/2 + abs(reg[0]) + 2
    h = (im1.shape[1]+im2.shape[1])/2 + abs(reg[1]) + 2
    r = scipy.empty((w, h))
    g = scipy.empty((w, h))
    b = scipy.empty((w, h))
    r[...] = mn
    g[...] = mn
    b[...] = mn
    
    ## draw borders
    im1 = im1.copy()
    im2 = im2.copy()
    im1[0,:] = mx
    im1[-1,:] = mx
    im1[:,0] = mx
    im1[:,-1] = mx
    im2[0,:] = mx
    im2[-1,:] = mx
    im2[:,0] = mx
    im2[:,-1] = mx
    
    ## copy in
    i1sx = max(0, -int(reg[0]))
    i1sy = max(0, -int(reg[1]))
    i2sx = max(0, int(reg[0]))
    i2sy = max(0, int(reg[1]))
    
    r[i1sx:i1sx+im1.shape[0], i1sy:i1sy+im1.shape[1]] = im1
    g[i2sx:i2sx+im2.shape[0], i2sy:i2sy+im2.shape[1]] = im2
    
    return scipy.concatenate((r[...,newaxis], g[...,newaxis], b[...,newaxis]), axis=2)



def slidingOp(template, data, op):
    data = data.view(ndarray)
    template = template.view(ndarray)
    tlen = template.shape[0]
    length = data.shape[0] - tlen
    result = empty((length), dtype=float)
    for i in range(0, length):
        result[i] = op(template, data[i:i+tlen])
    return result

def ratio(a, b):
    r1 = a/b
    r2 = b/a
    return where(r1>1.0, r1, r2)

def rmsMatch(template, data, thresh=0.75, scaleInvariant=False, noise=0.0):
    ## better to use scipy.ndimage.generic_filter ?
    if scaleInvariant:
        devs = slidingOp(template, data, lambda t,d: (t/d).std())
    else:
        devs = slidingOp(template, data, lambda t,d: (t-d).std())
    
    tstd = template.std()
    blocks = argwhere(devs < thresh * tstd)[:, 0]
    if len(blocks) == 0:
        return []
    inds = list(argwhere(blocks[1:] - blocks[:-1] > 1)[:,0] + 1) #remove adjacent points
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



def besselFilter(data, cutoff, order=1, dt=None, btype='low'):
    """return data passed through bessel filter"""
    if dt is None:
        try:
            tvals = data.xvals('Time')
            dt = (tvals[-1]-tvals[0]) / (len(tvals)-1)
        except:
            raise Exception('Must specify dt for this data.')
    
    b,a = scipy.signal.bessel(order, cutoff * 2 * dt, btype=btype) 
    return scipy.signal.lfilter(b, a, data.view(ndarray))

def highPass(data, cutoff, order=1, dt=None):
    """return data passed through high-pass bessel filter"""
    return besselFilter(data, cutoff, order, dt, 'high')

def lowPass(data, cutoff, order=1, dt=None):
    """return data passed through low-pass bessel filter"""
    return besselFilter(data, cutoff, order, dt, 'low')

def bandPass(data, low, high, lowOrder=1, highOrder=1, dt=None):
    """return data passed through low-pass bessel filter"""
    if dt is None:
        try:
            tvals = data.xvals('Time')
            dt = (tvals[-1]-tvals[0]) / (len(tvals)-1)
        except:
            raise Exception('Must specify dt for this data.')
    return lowPass(highPass(data, low, lowOrder, dt), high, highOrder, dt)

def gaussDivide(data, sigma):
    return data.astype(float32) / gaussian_filter(data, sigma=sigma)
    
def meanDivide(data, axis, inplace=False):
    if not inplace:
        d = empty(data.shape, dtype=float32)
    ind = [slice(None)] * data.ndim
    for i in range(0, data.shape[axis]):
        ind[axis] = i
        if inplace:
            data[tuple(ind)] /= data[tuple(ind)].mean()
        else:
            d[tuple(ind)] = data[tuple(ind)].astype(float32) / data[tuple(ind)].mean()
    if not inplace:
        return d

def medianDivide(data, axis, inplace=False):
    if not inplace:
        d = empty(data.shape, dtype=float32)
    ind = [slice(None)] * data.ndim
    for i in range(0, data.shape[axis]):
        ind[axis] = i
        if inplace:
            data[tuple(ind)] /= data[tuple(ind)].median()
        else:
            d[tuple(ind)] = data[tuple(ind)].astype(float32) / data[tuple(ind)].mean()
    if not inplace:
        return d

def blur(data, sigma):
    return gaussian_filter(data, sigma=sigma)


def findTriggers(data, spacing=None, highpass=True, devs=1.5):
    if highpass:
        d1 = data - median_filter(data, size=spacing)
    else:
        d1 = data
    stdev = d1.std() * devs
    ptrigs = (d1[1:] > stdev*devs) * (d1[:-1] <= stdev)
    ntrigs = (d1[1:] < -stdev*devs) * (d1[:-1] >= -stdev)
    return (argwhere(ptrigs)[:, 0], argwhere(ntrigs)[:, 0])

def triggerStack(data, triggers, axis=0, window=None):
    if window is None:
        dt = (triggers[1:] - triggers[:-1]).mean()
        window = [int(-0.5 * dt), int(0.5 * dt)]
    shape = list(data.shape)
    shape[axis] = window[1] - window[0]
    total = zeros((len(triggers),) + tuple(shape), dtype=data.dtype)
    readIndex = [slice(None)] * data.ndim
    writeIndex = [0] + ([slice(None)] * data.ndim)
    
    for i in triggers:
        rstart = i+window[0]
        rend = i+window[1]
        wstart = 0
        wend = shape[axis]
        if rend < 0 or rstart > data.shape[axis]:
            continue
        if rstart < 0:
            wstart = -rstart
            rstart = 0
        if rend > data.shape[axis]:
            wend = data.shape[axis] - rstart
            rend = data.shape[axis]
        readIndex[axis] = slice(rstart, rend)
        writeIndex[axis+1] = slice(wstart, wend)
        total[tuple(writeIndex)] += data[tuple(readIndex)]
        writeIndex[0] += 1
    return total

    
def generateSphere(radius):
    radius2 = radius**2
    w = int(radius*2 + 1)
    d = empty((w, w), dtype=float32)
    for x in range(0, w):
        for y in range(0, w):
            r2 = (x-radius)**2+(y-radius)**2
            if r2 > radius2:
                d[x,y] = 0.0
            else:
                d[x,y] = sqrt(radius2 - r2)
    return d

def make3Color(r=None, g=None, b=None):
    i = r
    if i is None:
        i = g
    if i is None:
        i = b
        
    img = zeros(i.shape + (3,), dtype=i.dtype)
    if r is not None:
        img[..., 2] = r
    if g is not None:
        img[..., 1] = g
    if b is not None:
        img[..., 0] = b
    return img


def imgDeconvolve(data, div):
    ## pad data past the end with the minimum value for each pixel
    data1 = empty((data.shape[0]+len(div),) + data.shape[1:])
    data1[:data.shape[0]] = data
    dmin = data.min(axis=0)
    dmin.shape = (1,) + dmin.shape
    data1[data.shape[0]:] = dmin
    
    ## determine shape of deconvolved image
    dec = deconvolve(data1[:, 0, 0], div)
    shape1 = (dec[0].shape[0], data.shape[1], data.shape[2])
    shape2 = (dec[1].shape[0], data.shape[1], data.shape[2])
    dec1 = empty(shape1)
    dec2 = empty(shape2)
    
    ## deconvolve
    for i in range(0, shape1[1]):
        for j in range(0, shape1[2]):
            dec = deconvolve(data1[:,i,j], div)
            dec1[:,i,j] = dec[0]
            dec2[:,i,j] = dec[1]
    return (dec1, dec2)

def xColumn(data, col):
    """Take a column out of a 2-D MetaArray and turn it into the axis values for axis 1. (Used for correcting older rtxi files)"""
    yCols = range(0, data.shape[0])
    yCols.remove(col)
    b = data[yCols].copy()
    b._info[1] = data.infoCopy()[0]['cols'][col]
    b._info[1]['values'] = data[col].view(ndarray)
    return b



def stdFilter(data, kernShape):
    shape = data.shape
    if len(kernShape) != data.ndim:
        raise Exception("Kernel shape must have length = data.ndim")
    res = empty(tuple(shape), dtype=float)
    for ind, i in ndenumerate(res):
        sl = [slice(max(0, ind[j]-kernShape[j]/2), min(shape[j], ind[j]+(kernShape[j]/2))) for j in range(0, data.ndim)]
        res[tuple(ind)] = std(data[tuple(sl)])
    return res

def makeDispMap(im1, im2, maxDist=10, searchRange=None, normBlur=5.0, matchSize=10., printProgress=False, showProgress=False, method="diffNoise"):
    """Generate a displacement map that can be used to distort one image to match another. 
    Return a tuple of two images (displacement, goodness).
    
    maxDist is the maximum distance to search in any direction for matches.
    Alternatively, searchRange can be specified [[minX, maxX], [minY, maxY]] to set the exact locations to be searched.
    
    normBlur is the amount of blur to apply when normalizing the image to identify well-matched regions. May need to be tweaked to improve performance.
    
    matchSize is the amount of blur to apply when smoothing out the displacement map--it should be roughly equivalent to the size of the well-matched region at any displacement. May need to be tweaked to improve performance.
    
    Recommended approach for matching two images:
        dm = makeDispMap(im1, im2)
        dmb = scipy.ndimage.gaussian_filter(dm, (20, 20))
        im1dist = scipy.ndimage.geometric_transform(im1, lambda x: (x[0]-dmb[x[0]], x[1]-dmb[x[1]]))
        
        (See also: matchDistortImg)
    """
    im1 = im1.astype(float32)
    im2 = im2.astype(float32)
    
    if searchRange is None:
        searchRange = [[-maxDist, maxDist+1], [-maxDist, maxDist+1]]
    
    bestMatch = empty(im2.shape, dtype=float)
    bmSet = False
    matchOffset = zeros(im2.shape + (2,), dtype=int)
    
    if showProgress:
        imw1 = showImg(zeros(im2.shape), title="errMap")
        imw2 = showImg(zeros(im2.shape), title="matchOffset")
        imw3 = showImg(zeros(im2.shape), title="goodness")
    
    for i in range(searchRange[0][0], searchRange[0][1]):
        for j in range(searchRange[1][0], searchRange[1][1]):
            # determine im1 and im2 slices
            #   (im1 slides over im2)
            s1 = [max(0, -i), min(im1.shape[0], im2.shape[0]-i), max(0, -j), min(im1.shape[1], im2.shape[1]-j)]
            s2 = [max(0, i), min(im2.shape[0], im1.shape[0]+i), max(0, j), min(im2.shape[1], im1.shape[1]+j)]
            rgn1 = im1[s1[0]:s1[1], s1[2]:s1[3]]
            rgn2 = im2[s2[0]:s2[1], s2[2]:s2[3]]
            #print s1, s2
            
            if method == 'diffNoise':
                # compute the difference between im1 region and im2 region
                diff = (rgn1 - rgn2)
                
                # measure how well the images match
                errMap = blur(abs(diff - blur(diff, (normBlur,normBlur))), (matchSize/2, matchSize/2))
            elif method == 'diff':
                errMap = abs(rgn1-rgn2)
                
            
            if not bmSet:
                bestMatch[...] = errMap.max()*5.
                bmSet = True
                
            # get bestMatch slice
            bmRgn = bestMatch[s2[0]:s2[1], s2[2]:s2[3]]
            
            # compare std map to bestMatch
            stdCmp = errMap < bmRgn
            
            # Set new values in bestMatch
            bestMatch[s2[0]:s2[1], s2[2]:s2[3]] = where(stdCmp, errMap, bmRgn)
            
            # set matchOffset to i,j wherever std is lower than previously seen
            stdCmpInds = argwhere(stdCmp) + array([[s2[0],s2[2]]])
            
            matchOffset[stdCmpInds[:,0], stdCmpInds[:,1]] = array([i,j])
            #v = array([i,j])
            #for ind in stdCmpInds:
                #matchOffset[tuple(ind)] = v
            
            if printProgress:
                print "Displacement %d, %d: %d matches" % (i,j, len(stdCmpInds))
            
            if showProgress:
                imw1.updateImage(errMap, autoRange=True)
                imw3.updateImage(bestMatch, autoRange=True)
                imw2.updateImage(make3Color(r=matchOffset[...,0], g=matchOffset[...,1]), autoRange=True)
                qapp.processEvents()
    
    if showProgress:
        imw1.hide()
        imw2.hide()
        imw3.hide()
        
    return (matchOffset, bestMatch)


            
def matchDistortImg(im1, im2, scale=4, maxDist=40, mapBlur=30, showProgress=False):
    """Distort im2 to fit optimally over im1. Searches scaled-down images first to determine range"""

    ## Determine scale and offset factors needed to match histograms
    for i in range(3):
        im1 -= im1.mean()
        im2 -= im2.mean()
    im1 /= im1.std()
    im2 /= im2.std()
    
    imws = []
    if showProgress:
        imws.append(showImg(im1, title="Original image 1"))
        imws.append(showImg(im2, title="Original image 2"))
    
    
    ## Scale down image to quickly find a rough displacement map
    print "Scaling images down for fast displacement search"
    #im1s = downsamplend(im1, (scale,scale))
    #im2s = downsamplend(im2, (scale,scale))
    im1s = downsample(downsample(im1, scale), scale)
    imss = downsample(downsample(im2, scale), scale)
    (dispMap, goodMap) = makeDispMap(im1s, im2s, maxDist=maxDist/scale, normBlur=5.0, matchSize=10., showProgress=showProgress)
    #showImg(make3Color(r=dispMap[..., 0], g=dispMap[..., 1], b=goodMap), title="Rough displacement map")
    
    
    border = 20
    ## clean up border of displacement map
    #for i in range(border-1,-1,-1):
        #dispMap[i] = dispMap[i+1]
        #dispMap[-i] = dispMap[-i-1]
        #dispMap[:,i] = dispMap[:,i+1]
        #dispMap[:,-i] = dispMap[:,-i-1]
    #showImg(make3Color(r=dispMap[..., 0], g=dispMap[..., 1], b=goodMap), title="Rough displacement map")
    
    
    ## Determine range of displacements to search, exclude border pixels
    ## TODO: this should exclude regions of the image which obviously do not match, rather than just chopping out the borders.
    dmCrop = dispMap[border:-border, border:-border]
    search = [
        [scale*(dmCrop[...,0].min()-1), scale*(dmCrop[...,0].max()+1)], 
        [scale*(dmCrop[...,1].min()-1), scale*(dmCrop[...,1].max()+1)]
    ]
    print "Finished initial search; displacement range is", search
    
    
    ## Generate full-size displacement map
    (dispMap2, goodMap2) = makeDispMap(im1, im2, searchRange=search, normBlur=2*scale, matchSize=5.*scale, showProgress=showProgress)
    if showProgress:
        imws.append(showImg(make3Color(r=dispMap2[..., 0], g=dispMap2[..., 1], b=goodMap2), title="Full displacement map"))
    
    
    ## blur the map to make continuous
    dm2Blur = blur(dispMap2.astype(float32), (mapBlur, mapBlur, 0))
    if showProgress:
        imws.append(showImg(dm2Blur, title="blurred full disp map"))
    
    
    ## Generate matched images
    print "Distorting image to match.."
    im2d = geometric_transform(im2, lambda x: (x[0]+(dm2Blur[x[0], x[1], 0]), x[1]+(dm2Blur[x[0], x[1], 1])))
    
    if showProgress:
        for w in imws:
            w.hide()
            
    return im2d


def measureBaseline(data, threshold=2.0, iterations=3):
    """Find the baseline value of a signal by iteratively measuring the median value, then excluding outliers."""
    data = data.view(ndarray)
    med = median(data)
    if iterations > 1:
        std = data.std()
        thresh = std * threshold
        arr = numpy.ma.masked_outside(data, med - thresh, med + thresh)
        return measureBaseline(arr[~arr.mask], threshold, iterations-1)
    else:
        return med

def measureNoise(data):
    ## Determine the base level of noise
    ## chop data up into small pieces, measure the std dev of each piece and take the median of those
    data2 = data.view(ndarray)[:10*(len(data)/10)]
    data2.shape = (10, len(data2)/10)
    return median(data2.std(axis=0))
    

def findEvents(data, minLength=3, noiseThreshold=2.0):
    """Locate events of any shape in a signal. Makes the following assumptions about the signal:
      - noise is gaussian
      - baseline is centered at 0 (high-pass filtering may be required to achieve this).
      - no 0 crossings within an event due to noise (low-pass filtering may be required to achieve this)
      - Events last more than minLength samples
      Return an array of events where each row is (start, length, sum)
    """
    ## just make sure this is an ndarray and not a MetaArray before operating..
    data1 = data.view(ndarray)
    
    
    ## find all 0 crossings
    mask = data1 > 0
    diff = mask[1:] - mask[:-1]  ## mask is True every time the trace crosses 0 between i and i+1
    times = argwhere(diff)[:, 0]  ## index of each point immediately before crossing.
    
    ## max number of events found, may cull some of these later..
    nEvents = len(times) - 1
    if nEvents < 1:
        return None
        
    ## Measure sum of values within each region between crossings, combine into single array
    ## At this stage, ignore al events with length < minLength
    events = empty(nEvents, dtype=[('start',int),('len', int),('sum', float)])  ### rows are [start, length, sum]
    n = 0
    for i in range(nEvents):
        t1 = times[i]+1
        t2 = times[i+1]+1
        if t2-t1 >= minLength:
            events[n][0] = t1
            events[n][1] = t2-t1
            events[n][2] = data1[t1:t2].sum()
            n += 1
    events = events[:n]
    
    ## Fit gaussian to peak in size histogram, use fit sigma as criteria for noise rejection
    stdev = measureNoise(data1)
    hist = histogram(events['sum'], bins=100)
    histx = 0.5*(hist[1][1:] + hist[1][:-1])
    fit = fitGaussian(histx, hist[0], [hist[0].max(), 0, stdev*3, 0])
    sigma = fit[0][2]
    minSize = sigma * noiseThreshold
    
    ## Generate new set of events, ignoring those with sum < minSize
    mask = abs(events['sum'] / events['len']) >= minSize
    events2 = events[mask]
    
    return events2
    
    
def removeBaseline(data, cutoff=5, threshold=1.5, dt=None):
    """Return the signal with baseline removed. Discards outliers from baseline measurement."""
    if dt is None:
        tv = data.xvals('Time')
        dt = tv[1] - tv[0]
    d1 = lowPass(data - measureBaseline(data), cutoff)
    d2 = data - d1
    stdev = std(d2)
    mask = abs(d2) > stdev*threshold
    d3 = where(mask, d1, data.view(ndarray))
    d4 = lowPass(d3, cutoff, dt=dt)
    return data - d4
    
def clusterSignals(data, num=5):
    pass
    
def denoise(data, radius=2, threshold=4):
    r2 = radius * 2
    d1 = data.view(ndarray)
    d2 = data[radius:-radius] - data[:-r2]
    d3 = data[r2:] - data[:-r2]
    d4 = d2 - d3
    stdev = d4.std()
    mask = abs(d4) < stdev*threshold
    d5 = where(mask, d1[radius:-radius], d1[:-r2])
    d6 = empty(d1.shape, dtype=d1.dtype)
    d6[:radius] = d1[:radius]
    d6[-radius:] = d1[-radius:]
    d6[radius:-radius] = d5
    
    if isinstance(data, MetaArray):
        return MetaArray(d6, info=data.infoCopy())
    return d6




