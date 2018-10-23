from __future__ import print_function
import scipy.optimize as opt
import scipy.weave
import numpy as np
import os, sys, user, time
from six.moves import range

path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'util'))
sys.path.append(path)

import acq4.pyqtgraph as pg
import acq4.util.functions as fn
from acq4.util import Qt

## TODO:
#  fit using rise and decay/rise as parameters so that the ratio can be constrained 
#  fit should be done without normalized amplitude for efficiency
#  multidimensional array of samples to match: 100 reps, 20 amps, 20 rise, 5 rise/decay

def main():
    global fits, err, psp, data, xVals
    
    ## generate table of PSP shapes
    nReps = 20
    amps = fn.logSpace(2e-12, 300e-12, 20)
    psp = np.empty((len(amps), nReps, 4))  ## last axis is [amp, xoff, rise, fall]
    psp[:,:,0] = amps[:,np.newaxis]
    psp[...,1] = 1e-3
    psp[...,2] = 0.1e-3
    psp[...,3] = 0.6e-3
    
    ## generate table of traces
    data, xVals = mkDataSet(psp, downsample=40)
    
    ## fit all traces
    guess = np.array([50e-10, 0.1e-3, 0.5e-3, 3e-3])
    bounds = np.array([(0, 5e-9), (0, 2e-3), (50e-6, 5e-3), (200e-6, 20e-3)])

    testFit("opt.leastsq", psp, data, xVals, fitPsp, guess=guess, bounds=bounds)
    #testFit("opt.leastsq_bounded", psp, data, xVals, fitPspBounded, guess=guess, bounds=bounds)
    
    ## very slow
    #testFit("opt.fmin_tnc", psp, data, xVals, fitPspFminTnc, guess=guess, bounds=bounds)
    
    ## bad fits, slow.. could possibly be improved
    #testFit("opt.fmin_l_bfgs_b", psp, data, xVals, fitPspLBFGSB, guess=guess, bounds=bounds)
    
    ## locks up
    #testFit("opt.fmin_cobyla", psp, data, xVals, fitPspCobyla, guess=guess, bounds=bounds)
    
    ## good fits, causes segfaults
    #testFit("opt.fmin_slsqp", psp, data, xVals, fitPspSlsqp, guess=guess, bounds=bounds)
    
    #testFit("opt.anneal", psp, data, xVals, fitAnneal, guess=guess)


def testMany(nReps=1000):
    psp = np.empty((1, nReps, 4))  ## last axis is [amp, xoff, rise, fall]
    psp[:,:,0] = 100e-12
    psp[...,1] = 1e-3
    psp[...,2] = 0.1e-3
    psp[...,3] = 0.6e-3
    
    ## generate table of traces
    data, xVals = mkDataSet(psp, downsample=40)
    
    ## fit all traces
    guess = np.array([50e-10, 0.1e-3, 0.5e-3, 3e-3])
    bounds = np.array([(0, 5e-9), (0, 2e-3), (50e-6, 5e-3), (200e-6, 20e-3)])

    #testFit("opt.leastsq", psp, data, xVals, fitPsp, guess=guess)
    #testFit("opt.leastsq_bounded", psp, data, xVals, fitPspBounded, guess=guess, bounds=bounds)

    global fits2, times2
    fits2, times2 = fitDataSet(xVals, data, fitPsp, guess=guess, bounds=bounds)
    print("Mean fit computation time: %0.2fms" % (times.mean() * 1000))
    
    p = pg.plot()
    p.setLabel('left', 'amplitude', units='A')
    p.setLabel('bottom', 'decay tau', units='s')
    p.plot(x=fits2[0, :, 3], y=fits2[0, :, 0], pen=None, symbol='o', symbolPen=None, symbolBrush=(255,255,255,100))
    p.plot(x=[psp[0, 0, 3]], y=[psp[0, 0, 0]], pen=None, symbol='+', symbolSize=15, symbolPen={'color': 'b', 'width': 3})
    
    p = pg.plot()
    p.setLabel('left', 'rise tau', units='s')
    p.setLabel('bottom', 'decay tau', units='s')
    p.plot(x=fits2[0, :, 3], y=fits2[0, :, 2], pen=None, symbol='o', symbolPen=None, symbolBrush=(255,255,255,100))
    p.plot(x=[psp[0, 0, 3]], y=[psp[0, 0, 2]], pen=None, symbol='+', symbolSize=15, symbolPen={'color': 'b', 'width': 3})
    
    
    



def testFit(title, psp, data, xVals, fitFn, *args, **kargs):
    global fits, times
    print("Running fit test", title)
    fits, times = fitDataSet(xVals, data, fitFn, *args, **kargs)
    print("Mean fit computation time: %0.2fms" % (times.mean() * 1000))
    
    ## compute fractional error
    psp2 = psp.copy()
    psp2[1] = psp2[2]  ## compare xoff against rise when determining fractional error
    err = (fits-psp2) / psp2
    errAvg = err.mean(axis=1)
    
    ## plot log(error) in each fit parameter vs amplitude
    ## (errors get larger as amplitude approaches the noise floor)
    p1 = pg.plot(title=title)
    p1.plot(x=psp[:,0,0], y=np.log(abs(errAvg[:,0])), pen='g')
    p1.plot(x=psp[:,0,0], y=np.log(abs(errAvg[:,1])), pen='y')
    p1.plot(x=psp[:,0,0], y=np.log(abs(errAvg[:,2])), pen='r')
    p1.plot(x=psp[:,0,0], y=np.log(abs(errAvg[:,3])), pen='b')



def pspInnerFunc(x, rise, decay, power):
    out = np.zeros(x.shape, x.dtype)
    mask = x >= 0
    xvals = x[mask]
    out[mask] =  (1.0 - np.exp(-xvals / rise))**power * np.exp(-xvals / decay)
    return out
    
def pspFunc(v, x, risePower=1.0):
    """Function approximating a PSP shape. 
    v = [amplitude, x offset, rise tau, decay tau]
    Uses absolute value of both taus, so fits may indicate negative tau.
    """
    
    if len(v) > 4:
        v = processExtraVars(v)
    
    ## determine scaling factor needed to achieve correct amplitude
    v[2] = abs(v[2])
    v[3] = abs(v[3])
    maxX = v[2] * np.log(1 + (v[3]*risePower / v[2]))
    maxVal = (1.0 - np.exp(-maxX / v[2]))**risePower * np.exp(-maxX / v[3])
    #maxVal = pspInnerFunc(np.array([maxX]), v[2], v[3], risePower)[0]
    
    try:
        out = v[0] / maxVal * pspInnerFunc(x-v[1], v[2], v[3], risePower)
    except:
        print(v[2], v[3], maxVal, x.shape, x.dtype)
        raise
    return out

def normalize(fn):
    def wrapper(x, y, guess, bounds=None, risePower=1.0):
        ## Find peak x,y 
        #peakX = np.argmax(y)
        peakVal = abs(y.mean()) #y[peakX]
        if peakVal == 0:
            peakVal = 1.0
            
        peakTime = abs(x.mean()) #x[peakX]
        if peakTime == 0:
            peakTime = 1.0
        
        ## normalize data, guess, and bounds
        y = y / peakVal
        x = x / peakTime
        origGuess = guess
        guess = np.array(guess)
        guess[0] /= peakVal
        guess[1:] /= peakTime
        bounds = np.array(bounds)
        bounds[0] = bounds[0] / peakVal
        bounds[1:] = bounds[1:] / peakTime
        
        
        ## interpolate
        #x2 = (x[:peakVal] + x[1:peakVal+1]) /2.
        #y2 = (y[:peakVal] + y[1:peakVal+1]) /2.
        #x = np.concatenate([x, x2])
        #y = np.concatenate([y, y2])
        
        if any(np.isinf(guess)) or any(np.isnan(guess)):
            print("NAN guess:", guess)
        
        ## run the fit on normalized data
        fit = fn(x, y, guess, bounds, risePower)


        
        ## reverse normalization before returning fit parameters
        ## also, make sure amplitude is properly scaled such that fit[0] is the maximum value of the function
        maxX = fit[2] * np.log(1 + (fit[3]*risePower / fit[2]))
        maxVal = (1.0 - np.exp(-maxX / fit[2]))**risePower * np.exp(-maxX / fit[3])
        fit[0] *= maxVal * peakVal
        fit[1:] *= peakTime
        
        if any(np.isnan(fit)) or any(np.isinf(fit)):
            fit = origGuess
        return fit
    return wrapper

    
def errFn(v, x, y, risePower):
    if len(v) > 4:
        v = processExtraVars(v)
    fit = v[0] * pspInnerFunc(x-v[1], v[2], v[3], risePower)
    err = abs(y - fit) * (fit + 3.0)
    err = (err**2).sum()
    return err


def processExtraVars(v):
    ##  allows using some extra variables to help fitters converge
    ##  v = [amp, xoff, rise, fall, xshift, decayshift]
    ##    xshift is a variable that shifts the onset of the PSP without affecting the decay curve
    ##    decayshift (in)decreases the decay before 1/e and (de)increases the decay after 1/e
    
    if len(v) == 4:
        return v
    
    v2 = v[:4]
    
    ## xshift
    v2[1] += v[4]
    v2[0] *= np.exp(-v[4]/v[3])
    
    return v2


def makeGuess(x, y):
    #tau = x[int(len(x)/10.)]
    #xoff = x[np.argmax(y)]-tau
    #if xoff < 0:
        #xoff = 0.
    #guess = [
        #y.max() - y.min(),
        #xoff,
        #tau,
        #x[int(len(x)/3.)],
        ##0.
    #]
    
    guess = [
        (y.max()-y.min()) * 2,
        0, 
        x[-1]*0.25,
        x[-1]
    ]
    
    
    return guess
    

    
def fitPsp(x, y, guess, bounds=None, risePower=1.0):
    guess = makeGuess(x, y)
    
    def errFn(v, x, y):
        #for i in range(len(v)):
            #v[i] = np.clip(v[i], bounds[i,0], bounds[i,1])  
            
        err = y - v[0] * pspInnerFunc(x-v[1], abs(v[2]), abs(v[3]), risePower)
        #print "ERR: ", v, (abs(err)**2).sum()
        return err
        
    fit = opt.leastsq(errFn, guess, args=(x, y), ftol=1e-3, factor=0.1)[0]
    fit[2:] = abs(fit[2:])
    maxX = fit[2] * np.log(1 + (fit[3]*risePower / fit[2]))
    maxVal = (1.0 - np.exp(-maxX / fit[2]))**risePower * np.exp(-maxX / fit[3])
    fit[0] *= maxVal
    return fit

@normalize
def fitPspBounded(x, y, guess, bounds, risePower=1.0):
    
    guess = makeGuess(x, y)
    #print "==================================="
    #print "Fit guess:", guess
    
    boundCenter = (bounds[:,1] + bounds[:,0]) /2.
    boundWidth = bounds[:,1] - bounds[:,0]
    #history = []
    def errFn(v, x, y):
        #print "    =======", v
        v = processExtraVars(v)
        for i in range(len(v)):
            ## clip v to bounds so that the boundary error value will not compete
            ## with the function error value.
            v[i] = np.clip(v[i], bounds[i,0], bounds[i,1])  
        #print "        ==>", v
        err = y - v[0] * pspInnerFunc(x-v[1], v[2], v[3], risePower)
        
        ## compute error that grows as v leaves boundaries
        boundErr = (np.clip(np.abs(v-boundCenter) - boundWidth/2., 0, np.inf) / boundWidth) ** 2 
        #print "       bound error:", boundErr
        #print "        func error:", (err**2).sum()
        err += 1.0 * boundErr.sum()
        #history.append((np.sum(err**2), list(v)))
        #print "       total error:", (err**2).sum()
        #print "ERR: ", v, (abs(err)**2).sum()
        return err
        
    fit = opt.leastsq(errFn, guess, args=(x, y), ftol=1e-3)[0]
    #minErr = None
    #minV = None
    #for err, v in history:
        #if minErr is None or err < minErr:
            #minErr = err
            #minV = v
    #if np.any(fit != minV):
        #print fit, minV
        #fit = minV
    
    
    
    fit = processExtraVars(fit)
    #print fit
    return fit

@normalize
def fitAnneal(x, y, guess, bounds=None, risePower=1.0):
    def errFn(v, x, y):
        err = y - v[0] * pspInnerFunc(x-v[1], v[2], v[3], risePower)
        return (err**2).sum()
        
    fit = opt.anneal(errFn, guess, args=(x, y))[0]
    return fit
    

def fitPspSlow(x, y, guess, risePower=1.0):
    def errFn(v, x, y):
        return y - pspFunc(v, x, risePower)
        
    return opt.leastsq(errFn, guess, args=(x, y))[0]

    
    
@normalize
def fitPspFminTnc(x, y, guess, bounds, risePower=1.0):
    
    fit = opt.fmin_tnc(errFn, guess, bounds=bounds, args=(x,y, risePower), approx_grad=True, disp=0, accuracy=1e-3)[0]
    return fit

@normalize
def fitPspLBFGSB(x, y, guess, bounds, risePower=1.0):
    fit = opt.fmin_l_bfgs_b(errFn, guess, bounds=bounds, args=(x,y,risePower), approx_grad=True, factr=1e12)[0]
    return fit

@normalize
def fitPspCobyla(x, y, guess, bounds, risePower=1.0):
    def cons(v, *args):
        ret = 1 if all(v > bounds[:,0]) and all(v < bounds[:,1]) else 0
        #print "Constraint:", v, ret
        return ret
    
    fit = opt.fmin_cobyla(errFn, guess, [cons], args=(x,y,risePower), disp=0)
    return fit


@normalize
def fitPspSlsqp(x, y, guess, bounds, risePower=1.0):
    fit = opt.fmin_slsqp(errFn, guess, bounds=bounds, args=(x,y,risePower), acc=1e-2, disp=0)
    
    return fit

@normalize
def fitPspSlsqpExtraAxes(x, y, guess, bounds, risePower=1.0):
    guess = np.append(guess, [0,0]) ## add extra axes to help gradient search
    bounds = np.append(bounds, bounds[0:1]+bounds[1:2], axis=0)
    bounds = np.append(bounds, bounds[1:2]+bounds[2:3], axis=0)
    print(guess)
    print(bounds)
    def errFn(v, x, y, risePower):
        fit = (v[0]+v[4]) * pspInnerFunc(x-(v[1]+v[4]+v[5]), v[2]+v[5], v[3], risePower)
        err = abs(y - fit) * (fit + 1.0)
        err = (err**2).sum()
        return err
    fit = opt.fmin_slsqp(errFn, guess, bounds=bounds, args=(x,y,risePower))
    fit[0] += fit[4]
    fit[1] += fit[4]+fit[5]
    fit[2] += fit[5]
    
    return fit[:4]









def mkData(v, power=1, noise=5e-12, length=5e-3, rate=400e3, downsample=40):
    ## Make a single event in noise
    ## Note: noise is the desired stdev of noise _after_ downsampling
    (amp, xoff, rise, fall) = v
    
    numPts = length * rate
    data = np.random.normal(scale=noise * downsample**0.5, loc=0, size=numPts)
    
    x = np.linspace(0,length,numPts)
    signal = pspFunc([amp, xoff, rise, fall], x, power)
    data += signal
    
    ## downsample
    data = fn.downsample(data, downsample)
    
    return x[::downsample], data
    
def mkDataSet(psp, **kargs):
    ## Make an array of data sets from an array of PSP parameters
    it = np.ndindex(psp.shape[:-1])
    firstInd = next(it)
    first = psp[firstInd]
    x, sample = mkData(first, **kargs)
    data = np.empty(psp.shape[:-1] + sample.shape)
    data[firstInd] = sample
    for ind in it:
        x, y = mkData(psp[ind], **kargs)
        data[ind] = y
    return data, x

def fitDataSet(xVals, data, fitFn, *args, **kargs):
    ## Fit an array of traces using fitFn(xVals, data[index], *args, **kargs)
    global psp
    space = data.shape[:-1]
    fits = np.empty(space + (4,))
    times = np.empty(space)
    for ind in np.ndindex(space):
        #print "Guess", kargs['guess']
        start = time.time()
        fits[ind] = fitFn(xVals, data[ind], *args, **kargs)
        #print "Real:", psp[ind]
        #print "Fit: ", fits[ind]
        #print ""
        times[ind] = time.time() - start
    return fits, times
    

def showFit(index):
    global xVals, data, psp, fits
    p = pg.plot(xVals, data[index])
    p.plot(xVals, pspFunc(psp[index], xVals), pen='b')
    p.plot(xVals, pspFunc(fits[index], xVals), pen='r')
    
def showAll():
    global xVals, data, psp, fits
    w = pg.GraphicsWindow()
    for i in range(psp.shape[0]):
        for j in range(psp.shape[1]):
            p = w.addPlot()
            fit = pspFunc(fits[i,j], xVals)
            err = (abs(data[i,j]-fit)**2).sum() / (data[i,j]**2).sum()
            
            green = np.clip((np.log(err)+3)*60, 0, 255)
            p.plot(xVals, data[i,j], pen=(80,60,60))
            p.plot(xVals, fit, pen=(50, green, 255-green, 200))
            #p.plot(xVals, pspFunc(psp[i,j], xVals), pen='b')
            p.hideAxis('left')
            p.hideAxis('bottom')
            p.hideButtons()
        w.nextRow()


def showTemplates(v):
    p = pg.plot()
    x = np.linspace(0, 10e-3, 1000)
    for i in range(v.shape[0]):
        vi = v[i]
        if len(vi) > 4:
            vi = processExtraVars(vi)
            print("Convert v:", v[i], " => ", vi)
        p.plot(x=x, y=pspFunc(vi, x), pen=(i, v.shape[0]*1.5))
        

def errorSurface(axes=[3, 0], v1=None, v2=None, bounds=None, noise=0.0, n=5000):
    ## compute sum of squares error between two templates over a range of differences in v
    ## the two templates are generated from the parameters in v1 and v2
    ## the error surface is computed by varying v2[axis[n]] from bounds[axis[n]][0] to bounds[axis[n]][1] on 
    ## each axis of the surface.
    
    ## displays and returns the error surface, 
    ## also returns an array of all the v2 parameters used for each point in the surface.
    
    x = np.linspace(0, 0.5, 5000)
    v = [1.0, 0.05, 0.05, 0.1]  ## defaults used if v1 / v2 are not given
    if v1 is None:
        v1 = v[:]
    if v2 is None:
        v2 = v1[:]
    
    if bounds is None:
        bounds = [(0.0, 2.0), (0.0, 0.1), (0.01, 0.1), (0.01, 0.5)]
        
    template1 = pspFunc(v1, x) + np.random.normal(size=len(x), scale=noise)
    
    ## number of iterations per axis
    n = int(n**(1.0/len(axes)))
    
    axv = []
    for ax in axes:
        axv.append(np.linspace(bounds[ax][0], bounds[ax][1], n))
        
    err = np.empty((n,)*len(axes))
    vals = np.empty(err.shape, dtype=object)
    
    inds = np.indices(err.shape).reshape((len(axes), err.size))
    
    for i in range(inds.shape[1]):
        ind = tuple(inds[:,i])
        v2a = v2[:]
        for j in range(len(axes)):
            v2a[axes[j]] = axv[j][ind[j]]
        template2 = pspFunc(v2a, x)
        err[ind] = np.sum((template2-template1)**2)
        vals[ind] = v2a
            
    if len(axes) == 2:
        p = pg.plot()
        img = pg.ImageItem(err)
        p.addItem(img)
        b1 = bounds[axes[0]]
        b2 = bounds[axes[1]]
        img.setRect(Qt.QRectF(b1[0], b2[0], b1[1]-b1[0], b2[1]-b2[0]))
    elif len(axes) == 3:
        pg.image(err)
        
    return err, vals
            
        
def watchFit(data, guess, bounds):
    ## plot each iteration of a fitting procedure by color
    
    
    pass
    

if __name__ == '__main__':
    #np.seterr(all='raise')
    #from acq4.util import Qt
    #app = Qt.QApplication([])
    main()
    #showAll()
    #app.exec_()







