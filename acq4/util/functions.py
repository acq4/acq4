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
import os, re, math, time, threading, decimal
from acq4.util.metaarray import *
#from scipy import *
#from scipy.optimize import leastsq
#from scipy.ndimage import gaussian_filter, generic_filter, median_filter
from scipy import stats
import scipy.signal, scipy.ndimage, scipy.optimize
import numpy.ma
from acq4.util.debug import *
import numpy as np

try:
    import scipy.weave as weave
    from scipy.weave import converters
except:
    pass    


def dirDialog(startDir='', title="Select Directory"):
  return str(QtGui.QFileDialog.getExistingDirectory(None, title, startDir))

def fileDialog():
  return str(QtGui.QFileDialog.getOpenFileName())




## the built in logspace function is pretty much useless.
def logSpace(start, stop, num):
    num = int(num)
    d = (stop / start) ** (1./(num-1))
    return start * (d ** np.arange(0, num))

def linSpace(start, stop, num):
    return np.linspace(start, stop, num)


def sigmoid(v, x):
    """Sigmoid function value at x. the parameter v is [slope, x-offset, amplitude, y-offset]"""
    return v[2] / (1.0 + np.exp(-v[0] * (x-v[1]))) + v[3]
    
def gaussian(v, x):
    """Gaussian function value at x. The parameter v is [amplitude, x-offset, sigma, y-offset]"""
    return v[0] * np.exp(-((x-v[1])**2) / (2 * v[2]**2)) + v[3]

def expDecay(v, x):
    """Exponential decay function valued at x. Parameter vector is [amplitude, tau]"""
    return v[0] * np.exp(-x / v[1]) #+ v[2]

def expDecayWithOffset(v, x):
    """Exponential decay function with a y-offset. Suitable for measuring a 
    bridge-balance offset in a voltage response to a current pulse. Assumes a fixed t0 at x=0.
    Parameter v is [amp, tau, y-offset]."""
    return v[0] * (1- np.exp(-x/v[1])) + v[2]

def expPulse(v, x):
    """Exponential pulse function (rising exponential with variable-length plateau followed by falling exponential)
    Parameter v is [t0, y-offset, tau1, tau2, amp, width]"""
    t0, yOffset, tau1, tau2, amp, width = v
    y = np.empty(x.shape)
    y[x<t0] = yOffset
    m1 = (x>=t0)&(x<(t0+width))
    m2 = (x>=(t0+width))
    x1 = x[m1]
    x2 = x[m2]
    y[m1] = amp*(1-np.exp(-(x1-t0)/tau1))+yOffset
    amp2 = amp*(1-np.exp(-width/tau1)) ## y-value at start of decay
    y[m2] = ((amp2)*np.exp(-(x2-(width+t0))/tau2))+yOffset
    return y


def fit(function, xVals, yVals, guess, errFn=None, measureError=False, generateResult=False, resultXVals=None, **kargs):
    """fit xVals, yVals to the specified function. 
    If generateResult is True, then the fit is used to generate an array of points from function
    with the xVals supplied (useful for plotting the fit results with the original data). 
    The result x values can be explicitly set with resultXVals."""
    if errFn is None:
        errFn = lambda v, x, y: function(v, x)-y
    if len(xVals) < len(guess):
        raise Exception("Too few data points to fit this function. (%d variables, %d points)" % (len(guess), len(xVals)))
    fitResult = scipy.optimize.leastsq(errFn, guess, args=(xVals, yVals), **kargs)
    error = None
    #if measureError:
        #error = errFn(fit[0], xVals, yVals)
    result = None
    if generateResult or measureError:
        if resultXVals is not None:
            xVals = resultXVals
        result = function(fitResult[0], xVals)
        #fn = lambda i: function(fit[0], xVals[i.astype(int)])
        #result = fromfunction(fn, xVals.shape)
        if measureError:
            error = abs(yVals - result).mean()
    return fitResult + (result, error)
        
def fitSigmoid(xVals, yVals, guess=[1.0, 0.0, 1.0, 0.0], **kargs):
    """Returns least-squares fit for sigmoid"""
    return fit(sigmoid, xVals, yVals, guess, **kargs)

def fitGaussian(xVals, yVals, guess=[1.0, 0.0, 1.0, 0.0], **kargs):
    """Returns least-squares fit parameters for function v[0] * exp(((x-v[1])**2) / (2 * v[2]**2)) + v[3]"""
    return fit(gaussian, xVals, yVals, guess, **kargs)

def fitExpDecay(xVals, yVals, guess=[1.0, 1.0, 0.0], **kargs):
    return fit(expDecay, xVals, yVals, guess, **kargs)

#def pspInnerFunc(v, x):
    #return v[0] * (1.0 - np.exp(-x / v[2])) * np.exp(-x / v[3])
    
#def pspFunc(v, x, risePower=1.0):
    #"""Function approximating a PSP shape. 
    #v = [amplitude, x offset, rise tau, fall tau]
    #Uses absolute value of both taus, so fits may indicate negative tau.
    #"""
    ### determine scaling factor needed to achieve correct amplitude
    #v = [v[0], v[1], abs(v[2]), abs(v[3])]
    #maxX = v[2] * np.log(1 + (v[3]/v[2]))
    #maxVal = pspInnerFunc([1.0, 0, v[2], v[3]], maxX)
    #out = np.empty(x.shape, x.dtype)
    #mask = x > v[1]
    #out[~mask] = 0
    #xvals = x[mask]-v[1]
    #try:
        #out[mask] = 1.0 / maxVal * pspInnerFunc(v, xvals)
    #except:
        #print v[2], v[3], maxVal, xvals.shape, xvals.dtype
        #raise
    #return out

#def fitPsp(xVals, yVals, guess=[1e-3, 0, 10e-3, 10e-3], bounds=None, **kargs):
    #vals, junk, comp, err =  fit(pspFunc, xVals, yVals, guess, **kargs)
    #amp, xoff, rise, fall = vals
    ### fit may return negative tau values (since pspFunc uses abs(tau)); return the absolute value.
    #return (amp, xoff, abs(rise), abs(fall))#, junk, comp, err


def pspInnerFunc(x, rise, decay, power):
    out = np.zeros(x.shape, x.dtype)
    mask = x >= 0
    xvals = x[mask]
    out[mask] =  (1.0 - np.exp(-xvals / rise))**power * np.exp(-xvals / decay)
    return out

def pspMaxTime(rise, decay, risePower=2.0):
    """Return the time from start to peak for a psp with given parameters."""
    return rise * np.log(1 + (decay * risePower / rise))

def pspFunc(v, x, risePower=2.0):
    """Function approximating a PSP shape. 
    v = [amplitude, x offset, rise tau, decay tau]
    Uses absolute value of both taus, so fits may indicate negative tau.
    """
    
    if len(v) > 4:
        v = processExtraVars(v)
    
    ## determine scaling factor needed to achieve correct amplitude
    v[2] = abs(v[2])
    v[3] = abs(v[3])
    maxX = pspMaxTime(v[2], v[3], risePower)
    maxVal = (1.0 - np.exp(-maxX / v[2]))**risePower * np.exp(-maxX / v[3])
    #maxVal = pspInnerFunc(np.array([maxX]), v[2], v[3], risePower)[0]
    
    try:
        out = v[0] / maxVal * pspInnerFunc(x-v[1], v[2], v[3], risePower)
    except:
        print v[2], v[3], maxVal, x.shape, x.dtype
        raise
    return out

def fitPsp(x, y, guess, bounds=None, risePower=2.0, multiFit=False):
    """
        guess: [amp, xoffset, rise, fall]
        bounds: [[ampMin, ampMax], ...]
        
        NOTE: This fit is more likely to converge correctly if the guess amplitude 
        is larger (about 2x) than the actual amplitude.
        
        if multiFit is True, then attempt to improve the fit by brute-force searching
        and re-fitting. (this is very slow)
    """
    if guess is None:
        guess = [
            (y.max()-y.min()) * 2,
            0, 
            x[-1]*0.25,
            x[-1]
        ]
    
    ## pick some reasonable default bounds
    if bounds is None:
        bounds = [[None,None]] * 4
        bounds[1][0] = -2e-3
        minTau = (x[1]-x[0]) * 0.5
        #bounds[2] = [minTau, None]
        #bounds[3] = [minTau, None]
        
    errCache = {}
    def errFn(v, x, y):
        key = tuple(v)
        if key not in errCache:
            for i in range(len(v)):
                if bounds[i][0] is not None:
                    v[i] = max(v[i], bounds[i][0])
                if bounds[i][1] is not None:
                    v[i] = min(v[i], bounds[i][1])
            err = y - v[0] * pspInnerFunc(x-v[1], abs(v[2]), abs(v[3]), risePower)
                    
            errCache[key] = (err, v.copy())
            return err
        err, v2 = errCache[key]
        v[:] = v2
        return err
        
    ## initial fit
    fit = scipy.optimize.leastsq(errFn, guess, args=(x, y), ftol=1e-2, factor=0.1)[0]
    
    
    ## try on a few more fits
    if multiFit:
        err = (errFn(fit, x, y)**2).sum()
        #print "fit:", err
        bestFit = fit
        for da in [0.5, 1.0, 2.0]:
            for dt in [0.5, 1.0, 2.0]:
                for dr in [0.5, 1.0, 2.0]:
                    for do in [0.002, .0, 0.002]:
                        if da == 1.0 and dt == 1.0 and dr == 1.0 and do == 0.0:
                            continue
                        guess = fit.copy()            
                        guess[0] *= da
                        guess[1] += do
                        guess[3] *= dt
                        guess[2] *= dr
                        fit2 = scipy.optimize.leastsq(errFn, guess, args=(x, y), ftol=1e-1, factor=0.1)[0]
                        err2 = (errFn(fit2, x, y)**2).sum()
                        if err2 < err:
                            bestFit = fit2
                            #print "   found better PSP fit: %s -> %s" % (err, err2), da, dt, dr, do
                            err = err2
        
        fit = bestFit
    
    
    
    fit[2:] = abs(fit[2:])
    maxX = fit[2] * np.log(1 + (fit[3]*risePower / fit[2]))
    maxVal = (1.0 - np.exp(-maxX / fit[2]))**risePower * np.exp(-maxX / fit[3])
    fit[0] *= maxVal
    return fit




def doublePspFunc(v, x, risePower=2.0):
    """Function approximating a PSP shape with double exponential decay. 
    v = [amp1, amp2, x offset, rise tau, decay tau 1, decay tau 2]
    Uses absolute value of both taus, so fits may indicate negative tau.
    """
    amp1, amp2, xoff, rise, decay1, decay2 = v
    
    x = x-xoff
    
    ### determine scaling factor needed to achieve correct amplitude
    #v[2] = abs(v[2])
    #v[3] = abs(v[3])
    #maxX = pspMaxTime(v[2], v[3], risePower)
    #maxVal = (1.0 - np.exp(-maxX / v[2]))**risePower * np.exp(-maxX / v[3])
    ##maxVal = pspInnerFunc(np.array([maxX]), v[2], v[3], risePower)[0]
    try:
        out = np.zeros(x.shape, x.dtype)
        mask = x >= 0
        x = x[mask]
        
        riseExp = (1.0 - np.exp(-x / rise))**risePower
        decayExp1 = amp1 * np.exp(-x / decay1)
        decayExp2 = amp2 * np.exp(-x / decay2)
        out[mask] =  riseExp * (decayExp1 + decayExp2)
    except:
        print v, x.shape, x.dtype
        raise
    return out

def doublePspMax(v, risePower=2.0):
    """
    Return the time and value of the peak of a PSP with double-exponential decay.
    """
    ## create same params with negative amplitudes
    v2 = list(v)[:]
    if v2[0] > 0:
        v2[0] *= -1
    if v2[1] > 0:
        v2[1] *= -1
    xMax = scipy.optimize.fmin(lambda x: doublePspFunc(v2, x), [v[2]], disp=False)
    yMax = doublePspFunc(v, xMax)
    return xMax[0], yMax[0]
    
def fitDoublePsp(x, y, guess, bounds=None, risePower=2.0):
    """
    Fit a PSP shape with double exponential decay.
    guess: [amp1, amp2, xoffset, rise, fall1, fall2]
    bounds: [[amp1Min, amp1Max], ...]
    
    NOTE: This fit is more likely to converge correctly if the guess amplitude 
    is larger (about 2x) than the actual amplitude.
    """
    ## normalize scale to assist fit
    yScale = y.max() - y.min()
    y = y / yScale
    for i in [0, 1]:
        guess[i] /= yScale
        if bounds[i][0] is not None:
            bounds[i][0] /= yScale
        if bounds[i][1] is not None:
            bounds[i][1] /= yScale
    
    #if guess is None:
        #guess = [
            #(y.max()-y.min()) * 2,
            #0, 
            #x[-1]*0.25,
            #x[-1]
        #]
    
    ### pick some reasonable default bounds
    #if bounds is None:
        #bounds = [[None,None]] * 4
        #minTau = (x[1]-x[0]) * 0.5
        ##bounds[2] = [minTau, None]
        ##bounds[3] = [minTau, None]
    #trials = []
    errs = {}
    def errFn(v, x, y):
        key = tuple(v)
        if key not in errs:
            ## enforce max rise/fall ratio
            #v[2] = min(v[2], v[3] / 2.)
            f = doublePspFunc(v,x,risePower)
            err = y - f
            #trials.append(f)
            
            for i in range(len(v)):
                if bounds[i][0] is not None and v[i] < bounds[i][0]:
                    v[i] = bounds[i][0]
                if bounds[i][1] is not None and v[i] > bounds[i][1]:
                    v[i] = bounds[i][1]
               
            ## both amps must be either positive or negative
            if (v[0] > 0 and v[1] < 0) or (v[0] < 0 and v[1] > 0):
                if abs(v[0]) > abs(v[1]):
                    v[1] = 0
                else:
                    v[0] = 0
            errs[key] = (err, v.copy())
            return err
        err, v2 = errs[key]
        v[:] = v2
        return err
        
    #fit = scipy.optimize.leastsq(errFn, guess, args=(x, y), ftol=1e-3, factor=0.1, full_output=1)
    fit = scipy.optimize.leastsq(errFn, guess, args=(x, y), ftol=1e-2)
    #print fit[2:]
    fit = fit[0]
    
    err = (errFn(fit, x, y)**2).sum()
    #print "initial fit:", fit, err
    
    guess = fit.copy()
    bestFit = fit
    for ampx in (0.5, 2.0):
        for taux in (0.2, 0.5, 2.0):   ## The combination ampx=2, taux=0.2 seems to be particularly important.
            guess[:2] = fit[:2] * ampx
            guess[4:6] = fit[4:6] * taux
            fit2 = scipy.optimize.leastsq(errFn, guess, args=(x, y), ftol=1e-2, factor=0.1)[0]
            err2 = (errFn(fit2, x, y)**2).sum()
            if err2 < err:
                #print "Improved fit:", ampx, taux, err2
                bestFit = fit2
                err = err2
    fit = bestFit
    #print "final fit:", fit, err
    fit[0] *= yScale
    fit[1] *= yScale
    return tuple(fit[:4]) + (min(*fit[4:]), max(*fit[4:]))




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

def downsample(data, n, axis=0, xvals='subsample'):
    """Downsample by averaging points together across axis.
    If multiple axes are specified, runs once per axis.
    If a metaArray is given, then the axis values can be either subsampled
    or downsampled to match.
    """
    ma = None
    if (hasattr(data, 'implements') and data.implements('MetaArray')):
        ma = data
        data = data.view(ndarray)
        
    
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
    d2 = d1.mean(axis+1)
    
    if ma is None:
        return d2
    else:
        info = ma.infoCopy()
        if 'values' in info[axis]:
            if xvals == 'subsample':
                info[axis]['values'] = info[axis]['values'][::n][:nPts]
            elif xvals == 'downsample':
                info[axis]['values'] = downsample(info[axis]['values'], n)
        return MetaArray(d2, info=info)
    
        
def downsamplend(data, div):
    """Downsample multiple axes at once. Probably slower than just using downsample multiple times."""
    shape = [float(data.shape[i]) / div[i] for i in range(0, data.ndim)]
    res = np.empty(tuple(shape), dtype=float)
    
    for ind, i in np.ndenumerate(res):
        sl = [slice(ind[j]*div[j], (ind[j]+1)*div[j]) for j in range(0, data.ndim)]
        res[tuple(ind)] = data[tuple(sl)].mean()
    
    return res


def recursiveRegisterImages(i1, i2, hint=(0,0), maxDist=None, objSize=None):
    """Given images i1 and i2, recursively find the offset for i2 that best matches with i1"""
    time1 = time.clock()
    ## float images
    im1 = i1.astype(float)
    im2 = i2.astype(float)
    #im1 = i1.mean(axis=2).astype(float)
    #im2 = i2.mean(axis=2).astype(float)
    
    ## Decide how many iterations to perform, scale images
    if objSize is not None:
        nit = int(np.floor(np.log(objSize)/np.log(2)) + 1)
    else:
        nit = 5
    print "Doing %d iterations" % nit
    
    spow = 2.0
    scales = map(lambda x: 1.0 / spow**x, range(nit-1,-1,-1))
    imScale = [[None, None]] * nit
    imScale[-1] = [im1, im2]
    time2 = time.clock()
    for i in range(nit-2,-1,-1):
        imScale[i] = [scipy.ndimage.zoom(imScale[i+1][0], 1.0/spow, order=1), scipy.ndimage.zoom(imScale[i+1][1], 1.0/spow, order=1)]
    print scales

    time3 = time.clock()
    lastSf = None
    if maxDist != None:
        start = (np.array(hint) - np.ceil(maxDist / 2.)) * scales[0]
        end = (np.array(hint) + np.ceil(maxDist / 2.)) * scales[0]
    else:
        start = np.array([0,0])
        end = None
        
    print "Checking range %s - %s" % (str(start), str(end))
    for i in range(0, nit):
        sf = scales[i]
        im1s = imScale[i][0]
        im2s = imScale[i][1]
        
        if lastSf is not None:
            start = np.floor(np.floor(center-0.5) * sf / lastSf)
            end = np.ceil(np.ceil(center+0.5) * sf / lastSf)
        ## get prediction
        #print "Scale %f: start: %s  end: %s" % (sf, str(start), str(end))
        if end is None or any(start != end):
            print "register:", start, end
            center = registerImages(im1s, im2s, (start, end))
        #print "   center = %s" % str(center/sf)
        
        
        lastSf = sf
    time4 = time.clock()
    print "Scale time: %f   Corr time: %f    Total: %f" % (time3-time2, time4-time3, time4-time1)
    return center

def xcMax(xc):
    mi = np.where(xc == xc.max())
    mi = np.array([mi[0][0], mi[1][0]])
    return mi

def registerImages(im1, im2, searchRange):
    """
    searchRange is [[xmin, ymin], [xmax, ymax]]
    """
    #print "Registering images %s and %s, %s-%s" % (str(im1.shape), str(im2.shape), str(start), str(end))
    #(sx, sy) = searchRange
    #start=[sx[0], sy[0]]
    #end = [sx[1], sy[1]]
    start, end = searchRange
    print "start:",start,"end:",end
    
    if end is None:
        mode = 'full'
        im1c = im1
        im2c = im2
        #print "Searching full images."
    else:
        mode = 'valid'
        s1x = max(0, start[0])
        s1y = max(0, start[1])
        print im1.shape
        print im2.shape
        e1x = min(im1.shape[0], im2.shape[0]+end[0])
        e1y = min(im1.shape[1], im2.shape[1]+end[1])
        print "%d,%d - %d,%d" % (s1x, s1y, e1x, e1y)
        
        s2x = max(0, -start[0])
        s2y = max(0, -start[1])
        e2x = min(im2.shape[0], im1.shape[0]-end[0])
        e2y = min(im2.shape[1], im1.shape[1]-end[1])
        print "%d,%d - %d,%d" % (s2x, s2y, e2x, e2y)
        
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
        try:
            img.shape = im2c.shape
        except:
            print img.shape, im2c.shape
            raise
        return abs(im2c - img).sum()
    
    print im1c.shape, im2c.shape
    xc = scipy.ndimage.generic_filter(im1c, err, footprint=im2c) 
   # print xc.min(), xc.max()
    #xcb = ndimage.filters.gaussian_filter(xc, 20)
    #xc -= xcb
    
    xcm = np.argmin(xc)
    # argmin returns min index of flattened array
    xcm = np.unravel_index(xcm, xc.shape)


    #xcm = xcMax(xc)
    #xcc = concatenate((xc[...,newaxis], xc[...,newaxis], xc[...,newaxis]), axis=2)
    #xcc[xcm[0], xcm[1], 0:2] = xc.min()
    #showImage(xcc)
    #showImage(xcb)
    
    print "Best match at " + str(xcm)
    if mode == 'full':
        xcm -= np.array(im1c.shape)-1
    else:
        xcm += start
    print "  ..corrected to " + str(xcm)
    
    #showImage(regPair(im1, im2, xcm))
    raise Exception()
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
    r = np.empty((w, h))
    g = np.empty((w, h))
    b = np.empty((w, h))
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
    
    return scipy.concatenate((r[...,np.newaxis], g[...,np.newaxis], b[...,np.newaxis]), axis=2)


def vibratome(data, start, stop, axes=(0,1)):
    """Take a diagonal slice through an array. If the input is N-dimensional, the result is N-1 dimensional.
    start and stop are (x,y) tuples that indicate the beginning and end of the slice region.
    The spacing of points along the slice is equivalent to the original pixel spacing.
    (The data set returned is not guaranteed to hit the stopping point exactly)"""

    ## transpose data so x and y are the first 2 axes
    trAx = range(data.ndim)
    trAx.remove(axes[0])
    trAx.remove(axes[1])
    tr1 = tuple(axes) + tuple(trAx)
    data = data.transpose(tr1)

    ## determine proper length of output array and pointwise vectors
    length = np.sqrt((stop[0]-start[0])**2 + (stop[1]-start[1])**2)
    dx = (stop[0]-start[0]) / length
    dy = (stop[1]-start[1]) / length
    length = np.ceil(length)  ## Extend length to be integer (can't have fractional array dimensions)
    nPts = int(length)+1
    
    ## Actual position of each point along the slice
    x = np.linspace(start[0], start[0]+(length*dx), nPts)
    y = np.linspace(start[1], start[1]+(length*dy), nPts)
    
    ## Location of original values that will contribute to each point
    xi0 = np.floor(x).astype(np.uint)
    yi0 = np.floor(y).astype(np.uint)
    xi1 = xi0 + 1
    yi1 = yi0 + 1
    
    ## Find out-of-bound values
    ox0 = (xi0 < 0) + (xi0 >= data.shape[0])
    oy0 = (yi0 < 0) + (yi0 >= data.shape[1])
    ox1 = (xi1 < 0) + (xi1 >= data.shape[0])
    oy1 = (yi1 < 0) + (yi1 >= data.shape[1])
    
    ## Make sure these locations are in-bounds (just read from 0,0 and then overwrite the values later)
    xi0[ox0] = 0
    xi1[ox1] = 0
    yi0[oy0] = 0
    yi1[oy1] = 0
    
    ## slices needed to pull values from data set
    s00 = [xi0, yi0] + [slice(None)] * (data.ndim-2)
    s10 = [xi1, yi0] + [slice(None)] * (data.ndim-2)
    s01 = [xi0, yi1] + [slice(None)] * (data.ndim-2)
    s11 = [xi1, yi1] + [slice(None)] * (data.ndim-2)
    
    ## Actual values from data set
    v00 = data[s00]
    v10 = data[s10]
    v01 = data[s01]
    v11 = data[s11]

    ## Set 0 for all out-of-bound values
    v00[ox0+oy0] = 0
    v10[ox1+oy0] = 0
    v01[ox0+oy1] = 0
    v11[ox1+oy1] = 0

    ## Interpolation coefficients
    dx0 = x - xi0
    dy0 = y - yi0
    dx1 = 1 - dx0
    dy1 = 1 - dy0
    c00 = dx1 * dy1
    c10 = dx0 * dy1
    c01 = dx1 * dy0
    c11 = dx0 * dy0
    
    ## Add un-indexed dimensions into coefficient arrays
    c00.shape = c00.shape + (1,)*(data.ndim-2)
    c10.shape = c10.shape + (1,)*(data.ndim-2)
    c01.shape = c01.shape + (1,)*(data.ndim-2)
    c11.shape = c11.shape + (1,)*(data.ndim-2)
    
    ## Interpolate!
    interpolated = v00*c00 + v10*c10 + v01*c01 + v11*c11
    
    ## figure out the reverse transpose order
    tr1 = list(tr1)
    tr1.pop(1)
    tr2 = [None] * len(tr1)
    for i in range(len(tr1)):
        if tr1[i] > 1:
            tr1[i] -= 1
        tr2[tr1[i]] = i
    tr2 = tuple(tr2)
    
    ## Untranspose array before returning
    return interpolated.transpose(tr2)

def affineSlice(data, shape, origin, vectors, axes, **kargs):
    """Take an arbitrary slice through an array.
    Parameters:
        data: the original dataset
        shape: the shape of the slice to take (Note the return value may have more dimensions than len(shape))
        origin: the location in the original dataset that will become the origin in the sliced data.
        vectors: list of unit vectors which point in the direction of the slice axes
                 each vector must be the same length as axes
                 If the vectors are not unit length, the result will be scaled.
                 If the vectors are not orthogonal, the result will be sheared.
        axes: the axes in the original dataset which correspond to the slice vectors
        interpolate: chice between linear interpolation and nearest-neighbor
        
        Example: start with a 4D data set, take a diagonal-planar slice out of the last 3 axes
            - data = array with dims (time, x, y, z) = (100, 40, 40, 40)
            - The plane to pull out is perpendicular to the vector (x,y,z) = (1,1,1) 
            - The origin of the slice will be at (x,y,z) = (40, 0, 0)
            - The we will slice a 20x20 plane from each timepoint, giving a final shape (100, 20, 20)
            affineSlice(data, shape=(20,20), origin=(40,0,0), vectors=((-1, 1, 0), (-1, 0, 1)), axes=(1,2,3))
            
            Note the following: 
                len(shape) == len(vectors) 
                len(origin) == len(axes) == len(vectors[0])
    """
    
    # sanity check
    if len(shape) != len(vectors):
        raise Exception("shape and vectors must have same length.")
    if len(origin) != len(axes):
        raise Exception("origin and axes must have same length.")
    for v in vectors:
        if len(v) != len(axes):
            raise Exception("each vector must be same length as axes.")
    shape = (np.ceil(shape[0]), np.ceil(shape[1]))
    

    ## transpose data so slice axes come first
    trAx = range(data.ndim)
    for x in axes:
        trAx.remove(x)
    tr1 = tuple(axes) + tuple(trAx)
    data = data.transpose(tr1)
    #print "tr1:", tr1
    ## dims are now [(slice axes), (other axes)]
    

    ### determine proper length of output array and pointwise vectors
    #length = np.sqrt((stop[0]-start[0])**2 + (stop[1]-start[1])**2)
    #dx = (stop[0]-start[0]) / length
    #dy = (stop[1]-start[1]) / length
    #length = np.ceil(length)  ## Extend length to be integer (can't have fractional array dimensions)
    #nPts = int(length)+1
    
    ## Actual position of each point along the slice
    #x = np.linspace(start[0], start[0]+(length*dx), nPts)
    #y = np.linspace(start[1], start[1]+(length*dy), nPts)
    
    ## make sure vectors are arrays
    vectors = np.array(vectors)
    origin = np.array(origin)
    origin.shape = (len(axes),) + (1,)*len(shape)
    
    ## Build array of sample locations. 
    grid = np.mgrid[tuple([slice(0,x) for x in shape])]  ## mesh grid of indexes
    x = (grid[np.newaxis,...] * vectors.transpose()[(Ellipsis,) + (np.newaxis,)*len(shape)]).sum(axis=1)  ## magic
    #print x.shape, origin.shape
    x += origin
    #print "X values:"
    #print x
    ## iterate manually over unused axes since map_coordinates won't do it for us
    extraShape = data.shape[len(axes):]
    output = np.empty(tuple(shape) + extraShape, dtype=data.dtype)
    for inds in np.ndindex(*extraShape):
        ind = (Ellipsis,) + inds
        output[ind] = scipy.ndimage.map_coordinates(data[ind], x, **kargs)
    
    
    tr = range(output.ndim)
    trb = []
    for i in range(min(axes)):
        ind = tr1.index(i) + (len(shape)-len(axes))
        tr.remove(ind)
        trb.append(ind)
    tr2 = tuple(trb+tr)
    #print "tr2", tr2

    ## Untranspose array before returning
    return output.transpose(tr2)
    
    
    ## old manual method. Might resurrect if performance is an issue..
    
    ### x[:, 1,2,3] is the vector indicating the position in data coords for the point [1,2,3] in slice coords
    ### Note this is the floating-point position, and should not be used for indexing (that's what xi is for)
    ### so axes are [pos, (slice axes)]
    
    
    
    ### Location of original values that will contribute to each point
    ### If there is no interpolation, then we use nearest neighbor.
    ### If there is interpolation, then each output voxel will be a combination of the nearest 2**ndim voxels
    ##xi0 = np.floor(x).astype(uint)
    ##yi0 = np.floor(y).astype(uint)
    ##xi1 = xi0 + 1
    ##yi1 = yi0 + 1
    #if interpolate:
        #xi = np.empty((2,) + x.shape, dtype=np.intp)
        #xi[0] = np.floor(x)
        #xi[1] = xi[0] + 1
    #else:
        #xi = np.round(x).astype(np.intp)[np.newaxis,...]
    ###Now we have added a new axis to the beginning of the array for separating the values on either side of the sample location
    ### so axes are [+/-, pos, (slice axes)]
    
    ### Find out-of-bound values
    ##ox0 = (xi0 < 0) + (xi0 >= data.shape[0])
    ##oy0 = (yi0 < 0) + (yi0 >= data.shape[1])
    ##ox1 = (xi1 < 0) + (xi1 >= data.shape[0])
    ##oy1 = (yi1 < 0) + (yi1 >= data.shape[1])
    #sh = list(xi.shape)
    
    #sh[1] = 1  ## instead of a vector for each point, we just want a boolean marking bad spots 
               ### (but leave the axis in anyway for broadcasting compatibility)
    #ox = np.zeros(tuple(sh), dtype=bool)
    #for i in range(len(xi.shape[1])):
        #ox += xi[:,i] < 0
        #ox += xi[:,i] > data.shape[i]
    ### axes are [+/-, 1, (slice axes)]
    
    ### Make sure these locations are in-bounds so the indexing slice will not barf later
    ### (just read from 0,0 and then overwrite the values later)
    ##xi0[ox0] = 0
    ##xi1[ox1] = 0
    ##yi0[oy0] = 0
    ##yi1[oy1] = 0
    #xi[ox] = 0
    
    ### slices needed to pull values from data set
    ##s00 = [xi0, yi0] + [slice(None)] * (data.ndim-2)
    ##s10 = [xi1, yi0] + [slice(None)] * (data.ndim-2)
    ##s01 = [xi0, yi1] + [slice(None)] * (data.ndim-2)
    ##s11 = [xi1, yi1] + [slice(None)] * (data.ndim-2)
    
    ### Actual values from data set
    ##v00 = data[s00]
    ##v10 = data[s10]
    ##v01 = data[s01]
    ##v11 = data[s11]
    #if interpolate:
        ###Should look like this:
        ##slices[0,1,1] = (xi[0,0], xi[1,1], xi[1,2])
        ##slices = fromfunction(lambda *inds: tuple([xi[inds[i], i] for i in range(len(inds))]), (2,)*len(shape), dtype=object)
        
        ### for each point in the slice, we grab 2**ndim neighboring values from which to interpolate
        ### v[0,1,1] = data[slices[0,1,1]]
        
        #intShape = (2,)*len(axes)  ## shape of interpolation space around each voxel
        
        #v = np.empty(intShape + data.shape, dtype=data.dtype)
        ### axes are [(interp. space), (slice axes), (other axes)]
        
        ##c = empty(v.shape, dtype=float)
        
        #for inds in np.ndindex(*intShape):  ## iterate over interpolation space
            #sl = tuple([xi[inds[i], i] for i in range(len(inds))])  ## generate the correct combination of slice values from xi
            #v[inds] = data[sl]
            #v[inds][ox] = 0  ## set out-of-bounds values to 0
            
            ### create interpolation coefficients 
            ##dx = x - xi
            #c = np.ones()
            #for i in range(len(shape)):
                #c *= x - xi
                
            ### apply interpolation coeff.
            #v[inds] *= c
            
        ### interpolate!
        #for i in range(len(shape)):
            #v = v.sum(axis=0)
    #else:
        #sl = tuple([xi[0][i] for i in range(len(shape))])
        #v = data[sl]
        #v[ox] = 0
        

    ### Set 0 for all out-of-bound values
    ##v00[ox0+oy0] = 0
    ##v10[ox1+oy0] = 0
    ##v01[ox0+oy1] = 0
    ##v11[ox1+oy1] = 0

    ### Interpolation coefficients
    #dx0 = x - xi0
    #dy0 = y - yi0
    #dx1 = 1 - dx0
    #dy1 = 1 - dy0
    #c00 = dx1 * dy1
    #c10 = dx0 * dy1
    #c01 = dx1 * dy0
    #c11 = dx0 * dy0
    
    ### Add un-indexed dimensions into coefficient arrays
    #c00.shape = c00.shape + (1,)*(data.ndim-2)
    #c10.shape = c10.shape + (1,)*(data.ndim-2)
    #c01.shape = c01.shape + (1,)*(data.ndim-2)
    #c11.shape = c11.shape + (1,)*(data.ndim-2)
    
    ### Interpolate!
    #interpolated = v00*c00 + v10*c10 + v01*c01 + v11*c11
    
    ### figure out the reverse transpose order
    ##tr1 = list(tr1)
    ##tr1.pop(1)
    ##tr2 = [None] * len(tr1)
    ##for i in range(len(tr1)):
        ##if tr1[i] > 1:
            ##tr1[i] -= 1
        ##tr2[tr1[i]] = i
    ##tr2 = tuple(tr2)

    #tr2 = np.array(tr1)
    #for i in range(0, len(tr2)):
        #tr2[tr1[i]] = i
    #tr2 = tuple(tr2)


    ### Untranspose array before returning
    #return interpolated.transpose(tr2)


def volumeSum(data, alpha, axis=0, dtype=None):
    """Volumetric summing over one axis."""
    #if data.ndim != alpha.ndim:
        #raise Exception('data and alpha must have same ndim.')
    if dtype is None:
        dtype = data.dtype
    sh = list(data.shape)
    sh.pop(axis)
    output = np.zeros(sh, dtype=dtype)
    #mask = np.zeros(sh, dtype=dtype)
    sl = [slice(None)] * data.ndim
    for i in reversed(range(data.shape[axis])):
        sl[axis] = i
        #p = (1.0 - mask) * alpha[sl]
        #output += p*data[sl]
        #mask += p
        a = alpha[sl]
        #print a.min(), a.max()
        output *= (1.0-a)
        output += a * data[sl] 
    
    return output


def slidingOp(template, data, op):
    data = data.view(ndarray)
    template = template.view(ndarray)
    tlen = template.shape[0]
    length = data.shape[0] - tlen
    result = np.empty((length), dtype=float)
    for i in range(0, length):
        result[i] = op(template, data[i:i+tlen])
    return result

def ratio(a, b):
    r1 = a/b
    r2 = b/a
    return np.where(r1>1.0, r1, r2)

def rmsMatch(template, data, thresh=0.75, scaleInvariant=False, noise=0.0):
    ## better to use scipy.ndimage.generic_filter ?
    if scaleInvariant:
        devs = slidingOp(template, data, lambda t,d: (t/d).std())
    else:
        devs = slidingOp(template, data, lambda t,d: (t-d).std())
    
    tstd = template.std()
    blocks = np.argwhere(devs < thresh * tstd)[:, 0]
    if len(blocks) == 0:
        return []
    inds = list(np.argwhere(blocks[1:] - blocks[:-1] > 1)[:,0] + 1) #remove adjacent points
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
            ix = np.ceil(scale/lastScale)
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




def highPass(data, cutoff, order=1, dt=None):
    """return data passed through high-pass bessel filter"""
    return besselFilter(data, cutoff, order, dt, 'high')


def applyFilter(data, b, a, padding=100, bidir=True):
    """Apply a linear filter with coefficients a, b. Optionally pad the data before filtering
    and/or run the filter in both directions."""
    d1 = data.view(ndarray)
    
    if padding > 0:
        d1 = numpy.hstack([d1[:padding], d1, d1[-padding:]])
    
    if bidir:
        d1 = scipy.signal.lfilter(b, a, scipy.signal.lfilter(b, a, d1)[::-1])[::-1]
    else:
        d1 = scipy.signal.lfilter(b, a, d1)
    
    if padding > 0:
        d1 = d1[padding:-padding]
        
    if (hasattr(data, 'implements') and data.implements('MetaArray')):
        return MetaArray(d1, info=data.infoCopy())
    else:
        return d1
    
def besselFilter(data, cutoff, order=1, dt=None, btype='low', bidir=True):
    """return data passed through bessel filter"""
    if dt is None:
        try:
            tvals = data.xvals('Time')
            dt = (tvals[-1]-tvals[0]) / (len(tvals)-1)
        except:
            raise Exception('Must specify dt for this data.')
    
    b,a = scipy.signal.bessel(order, cutoff * dt, btype=btype) 
    
    return applyFilter(data, b, a, bidir=bidir)
    #base = data.mean()
    #d1 = scipy.signal.lfilter(b, a, data.view(ndarray)-base) + base
    #if (hasattr(data, 'implements') and data.implements('MetaArray')):
        #return MetaArray(d1, info=data.infoCopy())
    #return d1

def butterworthFilter(data, wPass, wStop=None, gPass=2.0, gStop=20.0, order=1, dt=None, btype='low', bidir=True):
    """return data passed through bessel filter"""
    if dt is None:
        try:
            tvals = data.xvals('Time')
            dt = (tvals[-1]-tvals[0]) / (len(tvals)-1)
        except:
            raise Exception('Must specify dt for this data.')
    
    if wStop is None:
        wStop = wPass * 2.0
    ord, Wn = scipy.signal.buttord(wPass*dt*2., wStop*dt*2., gPass, gStop)
    #print "butterworth ord %f   Wn %f   c %f   sc %f" % (ord, Wn, cutoff, stopCutoff)
    b,a = scipy.signal.butter(ord, Wn, btype=btype) 
    
    return applyFilter(data, b, a, bidir=bidir)



def lowPass(data, cutoff, order=4, bidir=True, filter='butterworth', stopCutoff=None, gpass=2., gstop=20., samplerate=None, dt=None):
    """Bi-directional bessel/butterworth lowpass filter"""
    if dt is None:
        try:
            tvals = data.xvals('Time')
            dt = (tvals[-1]-tvals[0]) / (len(tvals)-1)
        except:
            raise Exception('Must specify dt for this data.')
        
    if dt is not None:
        samplerate = 1.0 / dt
    if samplerate is not None:
        cutoff /= 0.5*samplerate
        if stopCutoff is not None:
            stopCutoff /= 0.5*samplerate
    
    if filter == 'bessel':
        ## How do we compute Wn?
        ### function determining magnitude transfer of 4th-order bessel filter
        #from scipy.optimize import fsolve

        #def m(w):  
            #return 105. / (w**8 + 10*w**6 + 135*w**4 + 1575*w**2 + 11025.)**0.5
        #v = fsolve(lambda x: m(x)-limit, 1.0)
        #Wn = cutoff / (sampr*v)
        b,a = scipy.signal.bessel(order, cutoff, btype='low') 
    elif filter == 'butterworth':
        if stopCutoff is None:
            stopCutoff = cutoff * 2.0
        ord, Wn = scipy.signal.buttord(cutoff, stopCutoff, gpass, gstop)
        #print "butterworth ord %f   Wn %f   c %f   sc %f" % (ord, Wn, cutoff, stopCutoff)
        b,a = scipy.signal.butter(ord, Wn, btype='low') 
    else:
        raise Exception('Unknown filter type "%s"' % filter)
        
    return applyFilter(data, b, a, bidir=bidir)



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
    return data.astype(np.float32) / scipy.ndimage.gaussian_filter(data, sigma=sigma)
    
def meanDivide(data, axis, inplace=False):
    if not inplace:
        d = np.empty(data.shape, dtype=np.float32)
    ind = [slice(None)] * data.ndim
    for i in range(0, data.shape[axis]):
        ind[axis] = i
        if inplace:
            data[tuple(ind)] /= data[tuple(ind)].mean()
        else:
            d[tuple(ind)] = data[tuple(ind)].astype(np.float32) / data[tuple(ind)].mean()
    if not inplace:
        return d

def medianDivide(data, axis, inplace=False):
    if not inplace:
        d = np.empty(data.shape, dtype=np.float32)
    ind = [slice(None)] * data.ndim
    for i in range(0, data.shape[axis]):
        ind[axis] = i
        if inplace:
            data[tuple(ind)] /= data[tuple(ind)].median()
        else:
            d[tuple(ind)] = data[tuple(ind)].astype(np.float32) / data[tuple(ind)].mean()
    if not inplace:
        return d

def blur(data, sigma):
    return scipy.ndimage.gaussian_filter(data, sigma=sigma)


def findTriggers(data, spacing=None, highpass=True, devs=1.5):
    if highpass:
        d1 = data - scipy.ndimage.median_filter(data, size=spacing)
    else:
        d1 = data
    stdev = d1.std() * devs
    ptrigs = (d1[1:] > stdev*devs) * (d1[:-1] <= stdev)
    ntrigs = (d1[1:] < -stdev*devs) * (d1[:-1] >= -stdev)
    return (np.argwhere(ptrigs)[:, 0], np.argwhere(ntrigs)[:, 0])

def triggerStack(data, triggers, axis=0, window=None):
    """Stacks windows from a waveform from trigger locations.
    Useful for making spike-triggered measurements"""
    
    if window is None:
        dt = (triggers[1:] - triggers[:-1]).mean()
        window = [int(-0.5 * dt), int(0.5 * dt)]
    shape = list(data.shape)
    shape[axis] = window[1] - window[0]
    total = np.zeros((len(triggers),) + tuple(shape), dtype=data.dtype)
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
    d = np.empty((w, w), dtype=np.float32)
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
        
    img = np.zeros(i.shape + (3,), dtype=i.dtype)
    if r is not None:
        img[..., 2] = r
    if g is not None:
        img[..., 1] = g
    if b is not None:
        img[..., 0] = b
    return img


def imgDeconvolve(data, div):
    ## pad data past the end with the minimum value for each pixel
    data1 = np.empty((data.shape[0]+len(div),) + data.shape[1:])
    data1[:data.shape[0]] = data
    dmin = data.min(axis=0)
    dmin.shape = (1,) + dmin.shape
    data1[data.shape[0]:] = dmin
    
    ## determine shape of deconvolved image
    dec = deconvolve(data1[:, 0, 0], div)
    shape1 = (dec[0].shape[0], data.shape[1], data.shape[2])
    shape2 = (dec[1].shape[0], data.shape[1], data.shape[2])
    dec1 = np.empty(shape1)
    dec2 = np.empty(shape2)
    
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
    res = np.empty(tuple(shape), dtype=float)
    for ind, i in np.ndenumerate(res):
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
    im1 = im1.astype(np.float32)
    im2 = im2.astype(np.float32)
    
    if searchRange is None:
        searchRange = [[-maxDist, maxDist+1], [-maxDist, maxDist+1]]
    
    bestMatch = np.empty(im2.shape, dtype=float)
    bmSet = False
    matchOffset = np.zeros(im2.shape + (2,), dtype=int)
    
    if showProgress:
        imw1 = showImg(np.zeros(im2.shape), title="errMap")
        imw2 = showImg(np.zeros(im2.shape), title="matchOffset")
        imw3 = showImg(np.zeros(im2.shape), title="goodness")
    
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
            bestMatch[s2[0]:s2[1], s2[2]:s2[3]] = np.where(stdCmp, errMap, bmRgn)
            
            # set matchOffset to i,j wherever std is lower than previously seen
            stdCmpInds = np.argwhere(stdCmp) + np.array([[s2[0],s2[2]]])
            
            matchOffset[stdCmpInds[:,0], stdCmpInds[:,1]] = np.array([i,j])
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
    dm2Blur = blur(dispMap2.astype(np.float32), (mapBlur, mapBlur, 0))
    if showProgress:
        imws.append(showImg(dm2Blur, title="blurred full disp map"))
    
    
    ## Generate matched images
    print "Distorting image to match.."
    im2d = geometric_transform(im2, lambda x: (x[0]+(dm2Blur[x[0], x[1], 0]), x[1]+(dm2Blur[x[0], x[1], 1])))
    
    if showProgress:
        for w in imws:
            w.hide()
            
    return im2d


def threshold(data, threshold, direction=1):
    """Return all indices where data crosses threshold."""
    mask = data >= threshold
    mask = mask[1:].astype(np.byte) - mask[:-1].astype(np.byte)
    return np.argwhere(mask == direction)[:, 0]
    


def measureBaseline(data, threshold=2.0, iterations=2):
    """Find the baseline value of a signal by iteratively measuring the median value, then excluding outliers."""
    data = data.view(ndarray)
    med = np.median(data)
    if iterations > 1:
        std = data.std()
        thresh = std * threshold
        arr = numpy.ma.masked_outside(data, med - thresh, med + thresh)
        if len(arr) == 0:
            raise Exception("Masked out all data. min: %f, max: %f, std: %f" % (med - thresh, med + thresh, std))
        return measureBaseline(arr[~arr.mask], threshold, iterations-1)
    else:
        return med

def measureNoise(data, threshold=2.0, iterations=2):
    ## Determine the base level of noise
    data = data.view(ndarray)
    if iterations > 1:
        med = median(data)
        std = data.std()
        thresh = std * threshold
        arr = numpy.ma.masked_outside(data, med - thresh, med + thresh)
        return measureNoise(arr[~arr.mask], threshold, iterations-1)
    else:
        return data.std()
    #data2 = data.view(ndarray)[:10*(len(data)/10)]
    #data2.shape = (10, len(data2)/10)
    #return median(data2.std(axis=0))
    

def stdevThresholdEvents(data, threshold=3.0):
    """Finds regions in data greater than threshold*stdev.
    Returns a record array with columns: index, length, sum, peak.
    This function is only useful for data with its baseline removed."""
    stdev = data.std()
    mask = (abs(data) > stdev * threshold).astype(np.byte)
    starts = np.argwhere((mask[1:] - mask[:-1]) == 1)[:,0]
    ends = np.argwhere((mask[1:] - mask[:-1]) == -1)[:,0]
    if len(ends) > 0 and len(starts) > 0:
        if ends[0] < starts[0]:
            ends = ends[1:]
        if starts[-1] > ends[-1]:
            starts = starts[:-1]
        
        
    lengths = ends-starts
    events = np.empty(starts.shape, dtype=[('start',int), ('len',int), ('sum',float), ('peak',float)])
    events['start'] = starts
    events['len'] = lengths
    
    if len(starts) == 0 or len(ends) == 0:
        return events
    
    for i in range(len(starts)):
        d = data[starts[i]:ends[i]]
        events['sum'][i] = d.sum()
        if events['sum'][i] > 0:
            peak = d.max()
        else:
            peak = d.min()
        events['peak'][i] = peak
    return events

def findEvents(*args, **kargs):
    return zeroCrossingEvents(*args, **kargs)

def zeroCrossingEvents(data, minLength=3, minPeak=0.0, minSum=0.0, noiseThreshold=None):
    """Locate events of any shape in a signal. Works by finding regions of the signal
    that deviate from noise, using the area beneath the deviation as the detection criteria.
    
    Makes the following assumptions about the signal:
      - noise is gaussian
      - baseline is centered at 0 (high-pass filtering may be required to achieve this).
      - no 0 crossings within an event due to noise (low-pass filtering may be required to achieve this)
      - Events last more than minLength samples
      Return an array of events where each row is (start, length, sum, peak)
    """
    ## just make sure this is an ndarray and not a MetaArray before operating..
    #p = Profiler('findEvents')
    data1 = data.view(ndarray)
    #p.mark('view')
    xvals = None
    if (hasattr(data, 'implements') and data.implements('MetaArray')):
        try:
            xvals = data.xvals(0)
        except:
            pass
    
    
    ## find all 0 crossings
    mask = data1 > 0
    diff = mask[1:] - mask[:-1]  ## mask is True every time the trace crosses 0 between i and i+1
    times1 = np.argwhere(diff)[:, 0]  ## index of each point immediately before crossing.
    
    times = np.empty(len(times1)+2, dtype=times1.dtype)  ## add first/last indexes to list of crossing times
    times[0] = 0                                         ## this is a bit suspicious, but we'd rather know
    times[-1] = len(data1)                               ## about large events at the beginning/end
    times[1:-1] = times1                                 ## rather than ignore them.
    #p.mark('find crossings')
    
    ## select only events longer than minLength.
    ## We do this check early for performance--it eliminates the vast majority of events
    longEvents = np.argwhere(times[1:] - times[:-1] > minLength)
    if len(longEvents) < 1:
        nEvents = 0
    else:
        longEvents = longEvents[:, 0]
        nEvents = len(longEvents)
    
    ## Measure sum of values within each region between crossings, combine into single array
    if xvals is None:
        events = np.empty(nEvents, dtype=[('index',int),('len', int),('sum', float),('peak', float)])  ### rows are [start, length, sum]
    else:
        events = np.empty(nEvents, dtype=[('index',int),('time',float),('len', int),('sum', float),('peak', float)])  ### rows are [start, length, sum]
    #p.mark('empty %d -> %d'% (len(times), nEvents))
    #n = 0
    for i in range(nEvents):
        t1 = times[longEvents[i]]+1
        t2 = times[longEvents[i]+1]+1
        events[i]['index'] = t1
        events[i]['len'] = t2-t1
        evData = data1[t1:t2]
        events[i]['sum'] = evData.sum()
        if events[i]['sum'] > 0:
            peak = evData.max()
        else:
            peak = evData.min()
        events[i]['peak'] = peak
    #p.mark('generate event array')
    
    if xvals is not None:
        events['time'] = xvals[events['index']]
    
    if noiseThreshold  > 0:
        ## Fit gaussian to peak in size histogram, use fit sigma as criteria for noise rejection
        stdev = measureNoise(data1)
        #p.mark('measureNoise')
        hist = histogram(events['sum'], bins=100)
        #p.mark('histogram')
        histx = 0.5*(hist[1][1:] + hist[1][:-1]) ## get x values from middle of histogram bins
        #p.mark('histx')
        fit = fitGaussian(histx, hist[0], [hist[0].max(), 0, stdev*3, 0])
        #p.mark('fit')
        sigma = fit[0][2]
        minSize = sigma * noiseThreshold
        
        ## Generate new set of events, ignoring those with sum < minSize
        #mask = abs(events['sum'] / events['len']) >= minSize
        mask = abs(events['sum']) >= minSize
        #p.mark('mask')
        events = events[mask]
        #p.mark('select')

    if minPeak > 0:
        events = events[abs(events['peak']) > minPeak]
    
    if minSum > 0:
        events = events[abs(events['sum']) > minSum]
    
        
    return events


def thresholdEvents(data, threshold, adjustTimes=True, baseline=0.0):
    """Finds regions in a trace that cross a threshold value (as measured by distance from baseline). Returns the index, time, length, peak, and sum of each event.
    Optionally adjusts times to an extrapolated baseline-crossing."""
    threshold = abs(threshold)
    data1 = data.view(ndarray)
    data1 = data1-baseline
    #if (hasattr(data, 'implements') and data.implements('MetaArray')):
    try:
        xvals = data.xvals(0)
        dt = xvals[1]-xvals[0]
    except:
        dt = 1
        xvals = None
    
    ## find all threshold crossings
    masks = [(data1 > threshold).astype(np.byte), (data1 < -threshold).astype(np.byte)]
    hits = []
    for mask in masks:
        diff = mask[1:] - mask[:-1]
        onTimes = np.argwhere(diff==1)[:,0]+1
        offTimes = np.argwhere(diff==-1)[:,0]+1
        #print mask
        #print diff
        #print onTimes, offTimes
        if len(onTimes) == 0 or len(offTimes) == 0:
            continue
        if offTimes[0] < onTimes[0]:
            offTimes = offTimes[1:]
            if len(offTimes) == 0:
                continue
        if offTimes[-1] < onTimes[-1]:
            onTimes = onTimes[:-1]
        for i in xrange(len(onTimes)):
            hits.append((onTimes[i], offTimes[i]))
    
    ## sort hits  ## NOTE: this can be sped up since we already know how to interleave the events..
    hits.sort(lambda a,b: cmp(a[0], b[0]))
    
    nEvents = len(hits)
    if xvals is None:
        events = np.empty(nEvents, dtype=[('index',int),('len', int),('sum', float),('peak', float),('peakIndex', int)])  ### rows are [start, length, sum]
    else:
        events = np.empty(nEvents, dtype=[('index',int),('time',float),('len', int),('sum', float),('peak', float),('peakIndex', int)])  ### rows are     

    mask = np.ones(nEvents, dtype=bool)
    
    ## Lots of work ahead:
    ## 1) compute length, peak, sum for each event
    ## 2) adjust event times if requested, then recompute parameters
    for i in range(nEvents):
        t1, t2 = hits[i]
        ln = t2-t1
        evData = data1[t1:t2]
        sum = evData.sum()
        if sum > 0:
            #peak = evData.max()
            #ind = argwhere(evData==peak)[0][0]+t1
            peakInd = np.argmax(evData)
        else:
            #peak = evData.min()
            #ind = argwhere(evData==peak)[0][0]+t1
            peakInd = np.argmin(evData)
        peak = evData[peakInd]
        peakInd += t1
            
        #print "event %f: %d" % (xvals[t1], t1) 
        if adjustTimes:  ## Move start and end times outward, estimating the zero-crossing point for the event
        
            ## adjust t1 first
            mind = np.argmax(evData)
            pdiff = abs(peak - evData[0])
            if pdiff == 0:
                adj1 = 0
            else:
                adj1 = int(threshold * mind / pdiff)
                adj1 = min(ln, adj1)
            t1 -= adj1
            #print "   adjust t1", adj1
            
            ## check for collisions with previous events
            if i > 0:
                #lt2 = events[i-1]['index'] + events[i-1]['len']
                lt2 = hits[i-1][1]
                if t1 < lt2:
                    diff = lt2-t1   ## if events have collided, force them to compromise
                    tot = adj1 + lastAdj
                    if tot != 0:
                        d1 = diff * float(lastAdj) / tot
                        d2 = diff * float(adj1) / tot
                        #events[i-1]['len'] -= (d1+1)
                        hits[i-1] = (hits[i-1][0], hits[i-1][1]-(d1+1))
                        t1 += d2
                        #recompute[i-1] = True
                        #print "  correct t1", d2, "  correct prev.", d1+1
            #try:
                #print "   correct t1", d2, "  correct prev.", d1+1
            #except:
                #pass
            
            ## adjust t2
            mind = ln - mind
            pdiff = abs(peak - evData[-1])
            if pdiff == 0:
                adj2 = 0
            else:
                adj2 = int(threshold * mind / pdiff)
                adj2 = min(ln, adj2)
            t2 += adj2
            lastAdj = adj2
            #print "  adjust t2", adj2
            
            #recompute[i] = True
            
        #starts.append(t1)
        #stops.append(t2)
        hits[i] = (t1, t2)
        events[i]['peak'] = peak
        #if index == 'peak':
            #events[i]['index']=ind
        #else:
        events[i]['index'] = t1
        events[i]['peakIndex'] = peakInd
        events[i]['len'] = ln
        events[i]['sum'] = sum
        
    if adjustTimes:  ## go back and re-compute event parameters.
        for i in range(nEvents):
            t1, t2 = hits[i]
            
            ln = t2-t1
            evData = data1[t1:t2]
            sum = evData.sum()
            if len(evData) == 0:
                mask[i] = False
                continue
            if sum > 0:
                #peak = evData.max()
                #ind = argwhere(evData==peak)[0][0]+t1
                peakInd = np.argmax(evData)
            else:
                #peak = evData.min()
                #ind = argwhere(evData==peak)[0][0]+t1
                peakInd = np.argmin(evData)
            peak = evData[peakInd]
            peakInd += t1
                
            events[i]['peak'] = peak
            #if index == 'peak':
                #events[i]['index']=ind
            #else:
            events[i]['index'] = t1
            events[i]['peakIndex'] = peakInd
            events[i]['len'] = ln
            events[i]['sum'] = sum
    
    ## remove masked events
    events = events[mask]
    
    if xvals is not None:
        events['time'] = xvals[events['index']]
        
    #for i in xrange(len(events)):
        #print events[i]['time'], events[i]['peak']

    return events

    
def adaptiveDetrend(data, x=None, threshold=3.0):
    """Return the signal with baseline removed. Discards outliers from baseline measurement."""
    if x is None:
        x = data.xvals(0)
    
    d = data.view(ndarray)
    
    d2 = scipy.signal.detrend(d)
    
    stdev = d2.std()
    mask = abs(d2) < stdev*threshold
    #d3 = where(mask, 0, d2)
    #d4 = d2 - lowPass(d3, cutoffs[1], dt=dt)
    
    lr = stats.linregress(x[mask], d[mask])
    base = lr[1] + lr[0]*x
    d4 = d - base
    
    if (hasattr(data, 'implements') and data.implements('MetaArray')):
        return MetaArray(d4, info=data.infoCopy())
    return d4
    

def mode(data, bins=None):
    """Returns location max value from histogram."""
    if bins is None:
        bins = int(len(data)/10.)
        if bins < 2:
            bins = 2
    y, x = np.histogram(data, bins=bins)
    ind = np.argmax(y)
    mode = 0.5 * (x[ind] + x[ind+1])
    return mode
    
def modeFilter(data, window=500, step=None, bins=None):
    """Filter based on histogram-based mode function"""
    d1 = data.view(np.ndarray)
    vals = []
    l2 = int(window/2.)
    if step is None:
        step = l2
    i = 0
    while True:
        if i > len(data)-step:
            break
        vals.append(mode(d1[i:i+window], bins))
        i += step
            
    chunks = [np.linspace(vals[0], vals[0], l2)]
    for i in range(len(vals)-1):
        chunks.append(np.linspace(vals[i], vals[i+1], step))
    remain = len(data) - step*(len(vals)-1) - l2
    chunks.append(np.linspace(vals[-1], vals[-1], remain))
    d2 = np.hstack(chunks)
    
    if (hasattr(data, 'implements') and data.implements('MetaArray')):
        return MetaArray(d2, info=data.infoCopy())
    return d2
    


def histogramDetrend(data, window=500, bins=50, threshold=3.0):
    """Linear detrend. Works by finding the most common value at the beginning and end of a trace, excluding outliers."""
    
    d1 = data.view(np.ndarray)
    d2 = [d1[:window], d1[-window:]]
    v = [0, 0]
    for i in [0, 1]:
        d3 = d2[i]
        stdev = d3.std()
        mask = abs(d3-np.median(d3)) < stdev*threshold
        d4 = d3[mask]
        y, x = np.histogram(d4, bins=bins)
        ind = np.argmax(y)
        v[i] = 0.5 * (x[ind] + x[ind+1])
        
    base = np.linspace(v[0], v[1], len(data))
    d3 = data.view(np.ndarray) - base
    
    if (hasattr(data, 'implements') and data.implements('MetaArray')):
        return MetaArray(d3, info=data.infoCopy())
    return d3
    
    

def subtractMedian(data, time=None, width=100, dt=None):
    """Subtract rolling median from signal. 
    Arguments:
      width:  the width of the filter window in samples
      time: the width of the filter window in x value 
            if specified, then width is ignored.
      dt:   the conversion factor for time -> width
    """
        
    if time is not None:
        if dt is None:
            x = data.xvals(0)
            dt = x[1] - x[0]
        width = time / dt
    
    d1 = data.view(ndarray)
    width = int(width)
    med = scipy.ndimage.median_filter(d1, size=width)
    d2 = d1 - med
    
    if (hasattr(data, 'implements') and data.implements('MetaArray')):
        return MetaArray(d2, info=data.infoCopy())
    return d2
    
    
    
#def removeBaseline(data, windows=[500, 100], threshold=4.0):
    ## very slow method using median_filter:
    #d1 = data.view(ndarray)
    #d2 = d1 - median_filter(d1, windows[0])
    
    #stdev = d2.std()
    #d3 = where(abs(d2) > stdev*threshold, 0, d2)
    #d4 = d2 - median_filter(d3, windows[1])
    
    #if (hasattr(data, 'implements') and data.implements('MetaArray')):
        #return MetaArray(d4, info=data.infoCopy())
    #return d4
    
    
def clusterSignals(data, num=5):
    pass
    
def denoise(data, radius=2, threshold=4):
    """Very simple noise removal function. Compares a point to surrounding points,
    replaces with nearby values if the difference is too large."""
    
    
    r2 = radius * 2
    d1 = data.view(ndarray)
    d2 = data[radius:] - data[:-radius] #a derivative
    #d3 = data[r2:] - data[:-r2]
    #d4 = d2 - d3
    stdev = d2.std()
    #print "denoise: stdev of derivative:", stdev
    mask1 = d2 > stdev*threshold #where derivative is large and positive
    mask2 = d2 < -stdev*threshold #where derivative is large and negative
    maskpos = mask1[:-radius] * mask2[radius:] #both need to be true
    maskneg = mask1[radius:] * mask2[:-radius]
    mask = maskpos + maskneg
    d5 = np.where(mask, d1[:-r2], d1[radius:-radius]) #where both are true replace the value with the value from 2 points before
    d6 = np.empty(d1.shape, dtype=d1.dtype) #add points back to the ends
    d6[radius:-radius] = d5
    d6[:radius] = d1[:radius]
    d6[-radius:] = d1[-radius:]
    
    if (hasattr(data, 'implements') and data.implements('MetaArray')):
        return MetaArray(d6, info=data.infoCopy())
    return d6


def rollingSum(data, n):
    d1 = data.copy()
    d1[1:] += d1[:-1]  # integrate
    d2 = np.empty(len(d1) - n + 1, dtype=data.dtype)
    d2[0] = d1[n-1]  # copy first point
    d2[1:] = d1[n:] - d1[:-n]  # subtract
    return d2
    

def clementsBekkers(data, template):
    """Implements Clements-bekkers algorithm: slides template across data,
    returns array of points indicating goodness of fit.
    Biophysical Journal, 73: 220-229, 1997.
    """
    
    ## Strip out meta-data for faster computation
    D = data.view(ndarray)
    T = template.view(ndarray)
    
    ## Prepare a bunch of arrays we'll need later
    N = len(T)
    sumT = T.sum()
    sumT2 = (T**2).sum()
    sumD = rollingSum(D, N)
    sumD2 = rollingSum(D**2, N)
    sumTD = correlate(D, T, mode='valid')
    
    ## compute scale factor, offset at each location:
    scale = (sumTD - sumT * sumD /N) / (sumT2 - sumT**2 /N)
    offset = (sumD - scale * sumT) /N
    
    ## compute SSE at every location
    SSE = sumD2 + scale**2 * sumT2 + N * offset**2 - 2 * (scale*sumTD + offset*sumD - scale*offset*sumT)
    
    ## finally, compute error and detection criterion
    error = sqrt(SSE / (N-1))
    DC = scale / error
    return DC, scale, offset
    
def cbTemplateMatch(data, template, threshold=3.0):
    dc, scale, offset = clementsBekkers(data, template)
    mask = dc > threshold
    diff = mask[1:] - mask[:-1]
    times = np.argwhere(diff==1)[:, 0]  ## every time we start OR stop a spike
    
    ## in the unlikely event that the very first or last point is matched, remove it
    if abs(dc[0]) > threshold:
        times = times[1:]
    if abs(dc[-1]) > threshold:
        times = times[:-1]
    
    nEvents = len(times) / 2
    
    result = np.empty(nEvents, dtype=[('peak', int), ('dc', float), ('scale', float), ('offset', float)])
    for i in range(nEvents):
        i1 = times[i*2]
        i2 = times[(i*2)+1]
        d = dc[i1:i2]
        p = argmax(d)
        result[0] = p+i1
        result[1] = d[p]
        result[2] = scale[p+i1]
        result[3] = offset[p+i1]
    return result


def expTemplate(dt, rise, decay, delay=None, length=None, risePow=2.0):
    """Create PSP template with sample period dt.
    rise and decay are the exponential time constants
    delay is the amount of time before the PSP starts (defaults to rise+decay)
    length is the amount of time after the PSP starts (defaults to 5 * (rise+decay))
    """
    if delay is None:
        delay = rise+decay
    if length is None:
        length = (rise+decay) * 5
        
    nPts = int(length / dt)
    start = int(delay / dt)
    temp = np.empty(nPts)
    times = np.arange(0.0, dt*(nPts-start), dt)
    temp[:start] = 0.0
    temp[start:] = (1.0 - np.exp(-times/rise))**risePow  *  np.exp(-times/decay)
    temp /= temp.max()
    return temp


def tauiness(data, win, step=10):
    ivals = range(0, len(data)-win-1, int(win/step))
    xvals = data.xvals(0)
    result = np.empty((len(ivals), 4), dtype=float)
    for i in range(len(ivals)):
        j = ivals[i]
        v = fitExpDecay(np.arange(win), data.asarray()[j:j+win], measureError=True)
        result[i] = np.array(list(v[0]) + [v[3]])
        #result[i][0] = xvals[j]
        #result[i][1] = j
    result = MetaArray(result, info=[
        {'name': 'Time', 'values': xvals[ivals]}, 
        {'name': 'Parameter', 'cols': [{'name': 'Amplitude'}, {'name': 'Tau'}, {'name': 'Offset'}, {'name': 'Error'}]}
    ])
    return result
        
        

def expDeconvolve(data, tau):
    dt = 1
    if (hasattr(data, 'implements') and data.implements('MetaArray')):
        dt = data.xvals(0)[1] - data.xvals(0)[0]
    arr = data.view(np.ndarray)
    d = arr[:-1] + (tau / dt) * (arr[1:] - arr[:-1])
    if (hasattr(data, 'implements') and data.implements('MetaArray')):
        info = data.infoCopy()
        if 'values' in info[0]:
            info[0]['values'] = info[0]['values'][:-1]
        info[-1]['expDeconvolveTau'] = tau
        return MetaArray(d, info=info)
    else:
        return d

    
def expReconvolve(data, tau=None, dt=None):
    if (hasattr(data, 'implements') and data.implements('MetaArray')):
        if dt is None:
            dt = data.xvals(0)[1] - data.xvals(0)[0]
        if tau is None:
            tau = data._info[-1].get('expDeconvolveTau', None)
    if dt is None: 
        dt = 1
    if tau is None:
        raise Exception("Must specify tau.")
    # x(k+1) = x(k) + dt * (f(k) - x(k)) / tau
    # OR: x[k+1] = (1-dt/tau) * x[k] + dt/tau * x[k]
    #print tau, dt
    d = np.zeros(data.shape, data.dtype)
    dtt = dt / tau
    dtti = 1. - dtt
    for i in range(1, len(d)):
        d[i] = dtti * d[i-1] + dtt * data[i-1]
    
    if (hasattr(data, 'implements') and data.implements('MetaArray')):
        info = data.infoCopy()
        #if 'values' in info[0]:
            #info[0]['values'] = info[0]['values'][:-1]
        #info[-1]['expDeconvolveTau'] = tau
        return MetaArray(d, info=info)
    else:
        return d

    

def concatenateColumns(data):
    """Returns a single record array with columns taken from the elements in data. 
    data should be a list of elements, which can be either record arrays or tuples (name, type, data)
    """
    
    ## first determine dtype
    dtype = []
    names = set()
    maxLen = 0
    for element in data:
        if isinstance(element, np.ndarray):
            ## use existing columns
            for i in range(len(element.dtype)):
                name = element.dtype.names[i]
                dtype.append((name, element.dtype[i]))
            maxLen = max(maxLen, len(element))
        else:
            name, type, d = element
            if type is None:
                type = suggestDType(d)
            dtype.append((name, type))
            if isinstance(d, list) or isinstance(d, np.ndarray):
                maxLen = max(maxLen, len(d))
        if name in names:
            raise Exception('Name "%s" repeated' % name)
        names.add(name)
            
            
    
    ## create empty array
    out = np.empty(maxLen, dtype)
    
    ## fill columns
    for element in data:
        if isinstance(element, np.ndarray):
            for i in range(len(element.dtype)):
                name = element.dtype.names[i]
                try:
                    out[name] = element[name]
                except:
                    print "Column:", name
                    print "Input shape:", element.shape, element.dtype
                    print "Output shape:", out.shape, out.dtype
                    raise
        else:
            name, type, d = element
            out[name] = d
            
    return out
    
def suggestDType(x, singleValue=False):
    """Return a suitable dtype for x
    If singleValue is True, then a sequence will be interpreted as dtype=object
    rather than looking inside the sequence to determine its type.
    """
    if not singleValue and isinstance(x, list) or isinstance(x, tuple):
        if len(x) == 0:
            raise Exception('can not determine dtype for empty list')
        x = x[0]
        
    if hasattr(x, 'dtype'):
        return x.dtype
    elif isinstance(x, float):
        return float
    elif isinstance(x, int) or isinstance(x, long):
        return int
    #elif isinstance(x, basestring):  ## don't try to guess correct string length; use object instead.
        #return '<U%d' % len(x)
    else:
        return object
    
def suggestRecordDType(x, singleRecord=False):
    """Given a dict of values, suggest a record array dtype to use
    If singleRecord is True, then x is interpreted as a single record 
    rather than a dict-of-lists structure. This can resolve some ambiguities
    when a single cell contains a sequence as its value.
    """
    dt = []
    for k, v in x.iteritems():
        dt.append((k, suggestDType(v, singleValue=singleRecord)))
    return dt
    
    
def isFloat(x):
    return isinstance(x, float) or isinstance(x, np.floating)

def isInt(x):
    for typ in [int, long, np.integer]:
        if isinstance(x, typ):
            return True
    return False
    #return isinstance(x, int) or isinstance(x, np.integer)



def find(data, val, op='==', arrayOp='all', axis=0, useWeave=True):
    operands = {'==': 'eq', '!=': 'ne', '<': 'lt', '>': 'gt', '<=': 'le', '>=': 'ge'}
    if op not in operands:
        raise Exception("Operand '%s' is not supported. Options are: %s" % (str(op), str(operands.keys())))
    ## fallback for when weave is not available
    if not useWeave:
        axes = range(data.ndim)
        axes.remove(axis)
        axes = [axis] + axes
        d2 = data.transpose(axes)
        op = '__'+operands[op]+'__'
        for i in range(d2.shape[0]):
            d3 = d2[i]
            test = getattr(d3, op)
            if getattr(test, arrayOp)():
                return i
        return None
    
    ## simple scalar test
    if data.ndim == 1:
        template = """
            if (op == "%s") {
                for (int i=0; i<data_array->dimensions[0]; i++) {
                    if (data[i] %s val) {
                        return_val = i;
                        break;
                    }
                }
            }
        """
        
        code = "return_val = -1;\n"
        for op1 in operands:
            code += template % (op1, op1)
        
        #ret = weave.inline(code, ['data', 'val', 'op'], type_converters=converters.blitz, compiler = 'gcc')
        ret = weave.inline(code, ['data', 'val', 'op'], compiler = 'gcc')
        if ret == -1:
            ret = None
        return ret
        
    ## broadcasting test
    else:
        template = """
            if (op == "%s") {
                for (int i=0; i<data_array->dimensions[0]; i++) {
                    PyArrayObject* d2 = // PyArray_TakeFrom(data_array, PyInt_FromLong(i), 0, NULL, NPY_CLIP);
                    PyObject *itr;
                    itr = PyArray_MultiIterNew(2, d2, val);
                    int fail = 0;
                    while(PyArray_MultiIter_NOTDONE(itr)) {
                        if (PyArray_MultiIter_DATA(itr, 0) %s PyArray_MultiIter_DATA(itr, 1)) {
                            fail = 1;
                            break;
                        }
                        PyArray_MultiIter_NEXT(itr);
                    }
                    
                    if (fail == 0) {
                        return_val = i;
                        break;
                    }
                }
            }
        """
        
        code = "return_val = -1;\n"
        for op1 in operands:
            code += template % (op1, op1)
        
        ret = weave.inline(code, ['data', 'val', 'op'], compiler = 'gcc')
        if ret == -1:
            ret = None
        return ret
    
    
    ## broadcasting test
    #else:
        #template = """
            #if (op == "%s") {
                #for (int i=0; i<data_array->dimensions[0]; i++) {
                    #PyArrayObject* d2 = data(i);
                    #PyObject *itr;
                    #itr = PyArray_MultiIterNew(2, a_array, b_array);
                    #while(PyArray_MultiIter_NOTDONE(itr)) {
                        #p1 = (%s *) PyArray_MultiIter_DATA(itr, 0);
                        #p2 = (%s *) PyArray_MultiIter_DATA(itr, 1);
                        #*p1 = (*p1) * (*p2);
                        #PyArray_MultiIter_NEXT(itr);
                    #}
                #}
            #}
        #"""
        #pass

def measureResistance(data, mode):
    """Return a tuple of the (inputResistance, seriesResistance) for the given data.
    Arguments:
        data      A metaarray with a Time axis and 'primary' and 'command' channels, with a square step in the command channel.
        mode      Either 'IC' for current clamp or 'VC' for voltage clamp. If mode is 'IC' seriesResistance will be None."""
    cmd = data['command']

    pulseStart = cmd.axisValues('Time')[np.argwhere(cmd != cmd[0])[0][0]]
    pulseStop = cmd.axisValues('Time')[np.argwhere(cmd != cmd[0])[-1][0]]
    
    ## Extract specific time segments
    nudge = 0.1e-3
    base = data['Time': :(pulseStart-nudge)]
    pulse = data['Time': (pulseStart+nudge):(pulseStop-nudge)]
    pulseEnd = data['Time': pulseStart+((pulseStop-pulseStart)*2./3.):pulseStop-nudge]
    end = data['Time': (pulseStop+nudge): ]
    
    pulseAmp = pulse['command'].mean() - base['command'].mean()

    if mode == 'IC':
        inputResistance = (pulseEnd['primary'].mean() - base['primary'].mean())/pulseAmp
        seriesResistance = None

    elif mode == 'VC':
        if pulseAmp < 0:
            RsPeak = data['primary'].min()
        else:
            RsPeak = data['primary'].max()
        seriesResistance = (RsPeak-base['primary'].mean())/pulseAmp
        inputResistance = (pulseEnd['primary'].mean() - base['primary'].mean())/pulseAmp

    else:
        raise Exception("Not sure how to interpret mode: %s. Please use either 'VC' or 'IC'. " %str(mode))

    return (inputResistance, seriesResistance)

def measureResistanceWithExponentialFit(data, debug=False):
    """Return a dict with 'inputResistance', 'bridgeBalance' and 'tau' keys for the given current clamp
    data. Fits the data to an exponential decay with a y-offset to measure the 
    voltage drop across the bridge balance. Does not account for any bridge balance 
    compensation done during recording.
    Arguments:
        data      A metaarray with a Time axis and 'primary' and 'command' channels, with a square step in the command channel.
        debug     Default: False. If True, include extra intermediary calculated values in the dictionary that is returned. 

    """


    cmd = data['command']

    pulseStart = cmd.axisValues('Time')[np.argwhere(cmd != cmd[0])[0][0]]
    pulseStop = cmd.axisValues('Time')[np.argwhere(cmd != cmd[0])[-1][0]]

    baseline = data['Time':0:pulseStart]['primary']
    baseline = measureBaseline(baseline)

    pulse = data["Time":pulseStart:pulseStop]['primary']
    xvals = pulse.axisValues('Time') - pulseStart

    fitResult = fit(expDecayWithOffset, xvals, pulse, (-0.01, 0.01, 0.00), generateResult=True)

    amp = fitResult[0][0]
    tau = fitResult[0][1]
    yOffset = fitResult[0][2]

    commandAmp = cmd['Time':pulseStart][0] - cmd[0]

    inputResistance = abs((amp)/commandAmp)
    bridgeBalance = (yOffset - baseline)/commandAmp

    results = {'inputResistance':inputResistance,
            'bridgeBalance':bridgeBalance,
            'tau':tau}
    if debug:
        results['fitResult'] = fitResult
        results['xvals'] = xvals
        results['pulse'] = pulse
        results['baseline'] = baseline
        results['commandAmp'] = commandAmp

    return results








#------------------------------------------
#       Useless function graveyard:
#------------------------------------------


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
    d = np.empty((len(data)), dtype=data.dtype)
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
    posCurr = np.argwhere(ivc['current'] > 0.)[:, 0]
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










if __name__ == '__main__':
    import user
    
    
    