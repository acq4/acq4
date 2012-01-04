import scipy.optimize as opt
import scipy.weave
import numpy as np
import os, sys, user, time

path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'util'))
sys.path.append(path)

import pyqtgraph as pg
import functions as fn

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
    guess = np.array([50e-12, 0.1e-3, 0.5e-3, 3e-3])
    bounds = [(0, 5e-9), (0, 2e-3), (100e-6, 5e-3), (200e-6, 20e-3)]
    
    #testFit("opt.leastsq", psp, data, xVals, fitPsp, guess=guess)
    
    testFit("opt.leastsq_bounded", psp, data, xVals, fitPspBounded, guess=guess, bounds=bounds)
    
    #testFit("opt.fmin_tnc", psp, data, xVals, fitPspFminTnc, guess=guess, bounds=bounds)
    
    #testFit("opt.fmin_l_bfgs_b", psp, data, xVals, fitPspLBFGSB, guess=guess, bounds=bounds)

    #testFit("opt.fmin_cobyla", psp, data, xVals, fitPspCobyla, guess=guess, bounds=bounds)
    
    #testFit("opt.fmin_slsqp", psp, data, xVals, fitPspSlsqp, guess=guess, bounds=bounds)

def testFit(title, psp, data, xVals, fitFn, *args, **kargs):
    global fits, times
    fits, times = fitDataSet(xVals, data, fitFn, *args, **kargs)
    print "Mean fit computation time: %0.2fms" % (times.mean() * 1000)
    
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
    ## determine scaling factor needed to achieve correct amplitude
    v[2] = abs(v[2])
    v[3] = abs(v[3])
    maxX = v[2] * np.log(1 + (v[3]*risePower / v[2]))
    maxVal = (1.0 - np.exp(-maxX / v[2]))**risePower * np.exp(-maxX / v[3])
    #maxVal = pspInnerFunc(np.array([maxX]), v[2], v[3], risePower)[0]
    
    try:
        out = v[0] / maxVal * pspInnerFunc(x-v[1], v[2], v[3], risePower)
    except:
        print v[2], v[3], maxVal, x.shape, x.dtype
        raise
    return out



def normalize(fn):
    def wrapper(x, y, guess, bounds, risePower=1.0):
        ## Find peak x,y 
        peakX = np.argmax(y)
        peakVal = y[peakX]
        peakTime = x[peakX]
        
        ## normalize data, guess, and bounds
        y = y / peakVal
        x = x / peakTime
        guess = np.array(guess)
        guess[0] /= peakVal
        guess[1:] /= peakTime
        bounds = np.array(bounds)
        bounds[0] = bounds[0] / peakVal
        bounds[1:] = bounds[1:] / peakTime
        
        
        ## interpolate
        x2 = (x[:peakVal] + x[1:peakVal+1]) /2.
        y2 = (y[:peakVal] + y[1:peakVal+1]) /2.
        x = np.concatenate([x, x2])
        y = np.concatenate([y, y2])
        
        ## run the fit on normalized data
        fit = fn(x, y, guess, bounds, risePower)
        
        ## reverse normalization before returning fit parameters
        ## also, make sure amplitude is properly scaled such that fit[0] is the maximum value of the function
        maxX = fit[2] * np.log(1 + (fit[3]*risePower / fit[2]))
        maxVal = (1.0 - np.exp(-maxX / fit[2]))**risePower * np.exp(-maxX / fit[3])
        fit[0] *= maxVal * peakVal
        fit[1:] *= peakTime
        
        return fit
    return wrapper

    
def errFn(v, x, y, risePower):
    fit = v[0] * pspInnerFunc(x-v[1], v[2], v[3], risePower)
    err = abs(y - fit) * (fit + 3.0)
    err = (err**2).sum()
    return err

    
    
def fitPsp(x, y, guess, risePower=1.0):
    #def errFn(v, x, y):
        #err = y - v[0] * pspInnerFunc(x-v[1], abs(v[2]), abs(v[3]), risePower)
        ##print "ERR: ", v, (abs(err)**2).sum()
        #return err
        
    fit = opt.leastsq(errFn, guess, args=(x, y, risePower))[0]
    fit[2:] = abs(fit[2:])
    maxX = fit[2] * np.log(1 + (fit[3]*risePower / fit[2]))
    maxVal = (1.0 - np.exp(-maxX / fit[2]))**risePower * np.exp(-maxX / fit[3])
    fit[0] *= maxVal
    return fit

@normalize
def fitPspBounded(x, y, guess, bounds, risePower=1.0):
    boundCenter = (bounds[:,1] + bounds[:,0]) /2.
    boundWidth = bounds[:,1] - bounds[:,0]
    def errFn(v, x, y):
        err = y - v[0] * pspInnerFunc(x-v[1], v[2], v[3], risePower)
        
        ## compute error that grows as v leaves boundaries
        boundErr = np.clip(np.abs(v-boundCenter) - boundWidth, 0, np.inf) / boundWidth
        err += 10 * boundErr.sum()
        
        #print "ERR: ", v, (abs(err)**2).sum()
        return err
        
    fit = opt.leastsq(errFn, guess, args=(x, y), ftol=1e-3, xtol=1e-3)[0]
    return fit


def fitPspSlow(x, y, guess, risePower=1.0):
    def errFn(v, x, y):
        return y - pspFunc(v, x, risePower)
        
    return opt.leastsq(errFn, guess, args=(x, y))[0]

    
    
@normalize
def fitPspFminTnc(x, y, guess, bounds, risePower=1.0):
    
    fit = opt.fmin_tnc(errFn, guess, bounds=bounds, args=(x,y, risePower), approx_grad=True, messages=0)[0]
    return fit

@normalize
def fitPspLBFGSB(x, y, guess, bounds, risePower=1.0):
    fit = opt.fmin_l_bfgs_b(errFn, guess, bounds=bounds, args=(x,y,risePower), approx_grad=True)[0]
    return fit

@normalize
def fitPspCobyla(x, y, guess, bounds, risePower=1.0):
    def cons(v, *args):
        ret = 1 if all(v > bounds[:,0]) and all(v < bounds[:,1]) else 0
        #print "Constraint:", v, ret
        return ret
    
    fit = opt.fmin_cobyla(errFn, guess, [cons], args=(x,y,risePower), rhobeg=guess*0.5)
    return fit


@normalize
def fitPspSlsqp(x, y, guess, bounds, risePower=1.0):
    fit = opt.fmin_slsqp(errFn, guess, bounds=bounds, args=(x,y,risePower), disp=0, acc=1e-3)
    
    return fit

@normalize
def fitPspSlsqpExtraAxes(x, y, guess, bounds, risePower=1.0):
    guess = np.append(guess, [0,0]) ## add extra axes to help gradient search
    bounds = np.append(bounds, bounds[0:1]+bounds[1:2], axis=0)
    bounds = np.append(bounds, bounds[1:2]+bounds[2:3], axis=0)
    print guess
    print bounds
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
    firstInd = it.next()
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
            p.showScale('left', False)
            p.showScale('bottom', False)
            p.hideButtons()
        w.nextRow()


if __name__ == '__main__':
    #from PyQt4 import QtGui
    #app = QtGui.QApplication([])
    main()
    #app.exec_()







