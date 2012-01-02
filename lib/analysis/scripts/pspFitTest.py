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
    #amp = -20e-12
    #ampCV = 0.5
    #rise = 0.15e-3
    #riseCV = 0.001
    #fall = 0.6e-3
    #fallCV = 0.001
    #xoff = 1e-3
    #xoffCV = 0.1
    
    
    
    ## generate amplitude, rise, decay for each event
    #numEvents = 10
    #amps = np.random.normal(scale=abs(ampCV*amp), loc=amp, size=numEvents)
    #if amp < 0:
        #amps[amps>-1e-12] = -1e-12
    #else:
        #amps[amps<1e-12] = 1e-12
    #rises = np.random.normal(scale=riseCV*rise, loc=rise, size=numEvents)
    #rises[rises<0] = 0
    #falls = np.random.normal(scale=fallCV*fall, loc=fall, size=numEvents)
    #falls[falls<0] = 0
    #offsets = np.random.normal(scale=xoffCV*xoff, loc=xoff, size=numEvents)
    #offsets[offsets<0] = 0
    #amps = fn.logSpace(1e-12, 50e-12, numEvents)
    #rises = np.random.uniform(50e-6, 2e-3, numEvents)
    #falls = np.random.uniform(100e-6, 5e-3, numEvents)
    #offsets = np.random.uniform(0., 2e-3, numEvents)
    
    

    #psp = np.vstack([amps, offsets, rises, falls]).transpose()
    
    nReps = 10
    amps = fn.logSpace(0.2e-12, 150e-12, 20)
    
    psp = np.empty((len(amps), nReps, 4))  ## last axis is [amp, xoff, rise, fall]
    psp[:,:,0] = amps[:,np.newaxis]
    psp[...,1] = 1e-3
    psp[...,2] = 0.1e-3
    psp[...,3] = 0.6e-3
    
    
    data, xVals = mkDataSet(psp, downsample=40)
    
    guess = np.array([50e-12, 0, 0.5e-3, 3e-3])
    fits, times = fitDataSet(xVals, data, fitPsp, guess=guess)
    
    ## compute fractional error
    psp2 = psp.copy()
    psp2[1] = psp2[2]  ## compare xoff against rise when determining fractional error
    #err = np.empty(psp.shape, dtype=psp.dtype)
    #for n in err.dtype.names:
        #err[n] = (fits[n]-psp2[n]) / psp2[n]
    
    #minTime = 1e9
    #times = []
    #for i in range(numEvents):
        #x, y = data[i]
        #start = time.time()
        #fits.append(fitPsp(x, y, guess))
        #times.append(time.time()-start)
        
    #times = np.array(times)
    print "Mean fit computation time: %0.2fms" % (times.mean() * 1000)
    
    #fits = np.vstack(fits)
    
    #psp2 = psp.copy()
    #psp2[1] = psp2[2]  ## compare xoff against rise when determining fractional error
    
    err = (fits-psp2) / psp2
    
    #print err.max(axis=1)
    
    errAvg = err.mean(axis=1)
    
    p1 = pg.plot()
    
    p1.plot(x=psp[:,0,0], y=np.log(abs(errAvg[:,0])), pen='g')
    p1.plot(x=psp[:,0,0], y=np.log(abs(errAvg[:,1])), pen='y')
    p1.plot(x=psp[:,0,0], y=np.log(abs(errAvg[:,2])), pen='r')
    p1.plot(x=psp[:,0,0], y=np.log(abs(errAvg[:,3])), pen='b')
    
    #p1 = pg.PlotWindow(title="amp error vs amplitude")
    #p1.addDataItem(pg.ScatterPlotItem(x=psp[:,0], y=err[:,0]))
    #p2 = pg.PlotWindow(title="rise error vs rise")
    #p2.addDataItem(pg.ScatterPlotItem(x=psp[:,2], y=err[:,2]))
    #p3 = pg.PlotWindow(title="decay error vs decay")
    #p3.addDataItem(pg.ScatterPlotItem(x=psp[:,3], y=err[:,3]))
    #p.show()





def pspInnerFunc(x, rise, decay, power):
    out = np.empty(x.shape, x.dtype)
    mask = x >= 0
    out[~mask] = 0
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


def fitPsp(x, y, guess, risePower=1.0):
    def errFn(v, x, y):
        return y - v[0] * pspInnerFunc(x-v[1], abs(v[2]), abs(v[3]), risePower)
        
    fit = opt.leastsq(errFn, guess, args=(x, y))[0]
    fit[2:] = abs(fit[2:])
    maxX = fit[2] * np.log(1 + (fit[3]*risePower / fit[2]))
    maxVal = (1.0 - np.exp(-maxX / fit[2]))**risePower * np.exp(-maxX / fit[3])
    fit[0] *= maxVal
    return fit

#def fitPsp(x, y, guess, risePower=1.0):
    #def errFn(v, x, y):
        #return y - pspFunc(v, x, risePower)
        
    #return opt.leastsq(errFn, guess, args=(x, y))[0]



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
    space = data.shape[:-1]
    fits = np.empty(space + (4,))
    times = np.empty(space)
    for ind in np.ndindex(space):
        start = time.time()
        fits[ind] = fitFn(xVals, data[ind], *args, **kargs)
        times[ind] = time.time() - start
    return fits, times
    

def showFit(index):
    global xVals, data, psp, fits
    p = pg.plot(xVals, data[index])
    p.plot(xVals, pspFunc(psp[index], xVals), pen='b')
    p.plot(xVals, pspFunc(fits[index], xVals), pen='r')


if __name__ == '__main__':
    #from PyQt4 import QtGui
    #app = QtGui.QApplication([])
    main()
    #app.exec_()







