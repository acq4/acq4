# -*- coding: utf-8 -*-
"""
waveforms.py -  Waveform functions used by StimGenerator
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

This file defines several waveform-generating functions meant to be
called from within a StimGenerator widget.
"""
import numpy as np


def allFunctions():
    """Return all registered waveform generation functions.
    """
    return _allFuncs

def registerFunction(name, func):
    _allFuncs[name] = func

## Checking functions
def isNum(x):
    return np.isscalar(x)
    
def isNumOrNone(x):
    return (x is None) or isNum(x)
    
def isList(x):
    return hasattr(x, '__len__')
    
def isNumList(x):
    return isList(x) and (len(x) > 0) and isNum(x[0])

## Functions to allow in eval for the waveform generator. 
## These should be very robust with good error reporting since end users will be using them.
## rate and nPts are provided in the global namespace where these functions are called.

def pulse(times, widths, values, base=0.0, **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']
    
    if not isList(times):
        times = [times]
    if not isList(widths):
        widths = [widths] * len(times)
    if not isList(values):
        values = [values] * len(times)
        
    d = np.empty(nPts)
    d[:] = base
    for i in range(len(times)):
        t1 = int(times[i] * rate)
        wid = int(widths[i] * rate)
        if wid == 0:
            warnings.append("WARNING: Pulse width %f is too short for sample rate %f" % (widths[i], rate))
        if t1+wid >= nPts:
            warnings.append("WARNING: Function is longer than generated waveform.")
        d[t1:t1+wid] = values[i]
    return d

def steps(times, values, base=0.0, **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']
    
    if not isList(times):
        raise Exception('times argument must be a list')
    if not isList(values):
        raise Exception('values argument must be a list')
    
    d = np.empty(nPts)
    d[:] = base
    for i in range(1, len(times)):
        t1 = int(times[i-1] * rate)
        t2 = int(times[i] * rate)
        
        if t1 == t2:
            warnings.append("WARNING: Step width %f is too short for sample rate %f" % (times[i]-times[i-1], rate))
        if t2 >= nPts:
            warnings.append("WARNING: Function is longer than generated waveform.")
        d[t1:t2] = values[i-1]
    last = int(times[-1] * rate)
    d[last:] = values[-1]
    return d
    
def sineWave(period, amplitude=1.0, phase=0.0, start=0.0, stop=None, base=0.0, **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']
    
    ## Check all arguments 
    if not isNum(amplitude):
        raise Exception("Amplitude argument must be a number")
    if not isNum(period):
        raise Exception("Period argument must be a number")
    if not isNum(phase):
        raise Exception("Phase argument must be a number")
    if not isNumOrNone(start):
        raise Exception("Start argument must be a number")
    if not isNumOrNone(stop):
        raise Exception("Stop argument must be a number")
    
    ## initialize array
    d = np.empty(nPts)
    d[:] = base
    
    ## Define start and end points
    if start is None:
        start = 0
    else:
        start = int(start * rate)
    if stop is None:
        stop = nPts-1
    else:
        stop = int(stop * rate)
        
    if stop > nPts-1:
        warnings.append("WARNING: Function is longer than generated waveform\n")
        stop = nPts-1
        
    cycleTime = int(period * rate)
    if cycleTime < 10:
        warnings.append('Warning: Period is less than 10 samples\n')
    
    #d[start:stop] = np.fromfunction(lambda i: amplitude * np.sin(phase * 2.0 * np.pi + i * 2.0 * np.pi / (period * rate)), (stop-start,))
    d[start:stop] = amplitude * np.sin(phase * 2.0 * np.pi + np.arange(stop-start) * 2.0 * np.pi / (period * rate))
    return d
    
def squareWave(period, amplitude=1.0, phase=0.0, duty=0.5, start=0.0, stop=None, base=0.0, **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']
    
    ## Check all arguments 
    if not isNum(amplitude):
        raise Exception("Amplitude argument must be a number")
    if not isNum(period) or period <= 0:
        raise Exception("Period argument must be a number > 0")
    if not isNum(phase):
        raise Exception("Phase argument must be a number")
    if not isNum(duty) or duty < 0.0 or duty > 1.0:
        raise Exception("Duty argument must be a number between 0.0 and 1.0")
    if not isNumOrNone(start):
        raise Exception("Start argument must be a number")
    if not isNumOrNone(stop):
        raise Exception("Stop argument must be a number")
    
    ## Define start and end points
    if start is None:
        start = 0
    else:
        start = int(start * rate)
    if stop is None:
        stop = nPts-1
    else:
        stop = int(stop * rate)
        
    if stop > nPts-1:
        warnings.append("WARNING: Function is longer than generated waveform\n")
        stop = nPts-1
    
    cycleLen = int(period * rate)
    pulseLen = int(duty * period * rate)
    phase = (phase % 1.0) - 1.0
    pulseShift = int(phase * period * rate)
    
    if cycleLen <= 1:
        raise Exception('Period (%d) is less than 2 samples.' % cycleLen)
    if pulseLen < 1:
        raise Exception('Duty cycle (%d) is less than 1 sample.' % pulseLen)
    if cycleLen < 10:
        warnings.append('Warning: Period (%d) is less than 10 samples\n' % cycleLen)
    elif pulseLen < 10:
        warnings.append('Warning: Duty cycle (%d) is less than 10 samples\n' % pulseLen)

    ## initialize array
    d = np.empty(nPts)
    d[:] = base
    
    mask = ((np.arange(nPts) - pulseShift) % cycleLen) < pulseLen
    d[mask] = amplitude
    return d
    
    # nCycles = 2 + int((stop-start) / float(period*rate))
    # for i in range(nCycles):
    #     ptr = start + int(i*period*rate)
    #     a = ptr + pulseShift
    #     if a > stop:
    #         break
    #     b = a + pulseWidth
    #     a = max(a, start)
    #     b = min(b, stop)
    #     if a >= b:
    #         continue
    #     d[a:b] = amplitude

    
    
def sawWave(period, amplitude=1.0, phase=0.0, start=0.0, stop=None, base=0.0, **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']
    
    ## Check all arguments 
    if not isNum(amplitude):
        raise Exception("Amplitude argument must be a number")
    if not isNum(period) or period <= 0:
        raise Exception("Period argument must be a number > 0")
    if not isNum(phase):
        raise Exception("Phase argument must be a number")
    if not isNumOrNone(start):
        raise Exception("Start argument must be a number")
    if not isNumOrNone(stop):
        raise Exception("Stop argument must be a number")
    
    
    ## initialize array
    d = np.empty(nPts)
    d[:] = base
    
    ## Define start and end points
    if start is None:
        start = 0
    else:
        start = int(start * rate)
    if stop is None:
        stop = nPts-1
    else:
        stop = int(stop * rate)
        
    if stop > nPts-1:
        warnings.append("WARNING: Function is longer than generated waveform\n")
        stop = nPts-1
    #if period * rate < 10:
        #warnings.append("Warning: period is less than 10 samples\n")
        
    cycleTime = int(period * rate)
    if cycleTime < 10:
        warnings.append('Warning: Period is less than 10 samples\n')
    if cycleTime < 1:
        raise Exception('Period (%d) is less than 1 sample.' % cycleTime)
    
    #d[start:stop] = amplitude * np.fromfunction(lambda t: (phase + t/float(rate*period)) % 1.0, (stop-start,))
    d[start:stop] = amplitude * ((phase + np.arange(stop-start)/float(rate*period)) % 1.0)
    return d

    
def listWave(period, values=None, phase=0.0, start=0.0, stop=None, base=0.0, **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']
    
    ## Check all arguments 
    if type(values) not in [list, tuple, np.ndarray]or len(values) < 1:
        raise Exception("Values argument must be a list or array")
    values = np.array(values)
    if values.ndim != 1:
        raise Exception("Values argument must be 1-dimensional array")
        
    if not isNum(period) or period <= 0:
        raise Exception("Period argument must be a number > 0")
    if not isNum(phase):
        raise Exception("Phase argument must be a number")
    if not isNumOrNone(start):
        raise Exception("Start argument must be a number")
    if not isNumOrNone(stop):
        raise Exception("Stop argument must be a number")
    
    ## initialize array
    d = np.empty(nPts)
    d[:] = base
    
    ## Define start and end points
    if start is None:
        start = 0
    else:
        start = int(start * rate)
    if stop is None:
        stop = nPts-1
    else:
        stop = int(stop * rate)
        
    if stop > nPts-1:
        warnings.append("WARNING: Function is longer than generated waveform\n")
        stop = nPts-1

    cycleTime = int(period * rate)
    if cycleTime < 10:
        warnings.append('Warning: Period is less than 10 samples\n')
    if cycleTime < 1:
        return np.zeros(nPts)

    #saw = np.fromfunction(lambda t: len(values) * ((phase + t/float(rate*period)) % 1.0), (stop-start,))
    saw = len(values) * ((phase + np.arange(stop-start)/float(rate*period)) % 1.0)
    d[start:stop] = values[saw.astype(int).clip(0, len(values)-1)]
    #d[start:stop] = saw
    return d

def noise(mean, sigma, start=0.0, stop=None, **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']
    
    if not isNum(mean):
        raise Exception("Mean argument must be a number")
    if not isNum(sigma):
        raise Exception("Sigma argument must be a number")
    if not isNumOrNone(start):
        raise Exception("Start argument must be a number")
    if not isNumOrNone(stop):
        raise Exception("Stop argument must be a number")
    
    
    ## initialize array
    d = np.zeros(nPts)
    
    ## Define start and end points
    if start is None:
        start = 0
    else:
        start = int(start * rate)
    if stop is None:
        stop = nPts-1
    else:
        stop = int(stop * rate)
        
    if stop > nPts-1:
        warnings.append("WARNING: Function is longer than generated waveform\n")
        stop = nPts-1

    d[start:stop] = np.random.normal(size=stop-start, loc=mean, scale=sigma)
    return d

def tonePip(freq= 1000.0, risfall=10.0, start=0.0, stop=500.0, base=0.0, **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']
    
    ms=1e-3
    ## Check all arguments
    if not isNum(freq) or freq <= 0:
        raise Exception("Frequency argument must be a number > 0") 
    if not isNum(risfall):
        raise Exception("RisFall argument must be a number")
    if not isNumOrNone(start):
        raise Exception("Start argument must be a number")
    if not isNumOrNone(stop):
        raise Exception("Stop argument must be a number")
    amplitude=np.pi/2
    linramp=amplitude+sawWave(risfall*ms,amplitude,0,start*ms,(start+risfall)*ms, 0, **kwds)+pulse((start+risfall)*ms,(stop-risfall)*ms,amplitude, **kwds)-sawWave(risfall*ms,amplitude,0,(stop-risfall)*ms,stop*ms, **kwds)
    cos2gat=(np.cos(linramp))**2
    d=cos2gat
    per=float(1/freq)
    d=cos2gat*sineWave(per,1,0,start*ms,stop*ms,0, **kwds)
    return d
#def sawWave(period, amplitude=1.0, phase=0.0, start=0.0, stop=None, base=0.0, **kwds):    
#np.cos(1.570796+sawWave(2.5e-3,1.570796,0,.250,.250+2.5e-3,0)+pulse(.250+2.5e-3,497.5e-3,1.570796)-sawWave(2.5e-3,1.570796,0,497.5e-3,500e-3))**2*sineWave(1/4000.0,1,0,.250,.500,0)

# def soundstim(startfreq= 1000.0, npip= 11, tdur= 50, tipi= 200, direction= 'up', **kwds):  #tfr 09/28/2015
def soundstim(startfreq= 1000.0, npip= 11, tdur= 50, tipi= 400, octspace = 0.5, reps=1, direction= 'up', **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']

## Check all arguments
    if not isNum(startfreq) or startfreq <= 0:
        raise Exception("Frequency argument must be a number > 0") 
    if not isNum(npip):
        raise Exception("npip argument must be a number")
    if not isNumOrNone(tdur):
        raise Exception("tdur argument must be a number")
    if not isNumOrNone(tipi):
        raise Exception("tipi argument must be a number")
    if not isNumOrNone(tipi):
        raise Exception("octspace argument must be a number between 0 and 1")
    posDirection=['up', 'down']
    if direction not in posDirection:
        raise Exception("direction must be up or down")

    if direction == posDirection[0]:
        dirconst = octspace
    else:
        dirconst = -1 * octspace
    d=0
    totalrep=npip*(tdur+tipi)
    for repcount in np.arange(reps):
        freqs = startfreq * 2**(dirconst * np.arange(npip))
        

        for icount in np.arange(npip):
            #d = d+tonePip(freqs[icount],2.5,(icount)*250,250*icount+50,0, **kwds) #tropp 09/28/2015
            print 'start', (icount)*(tdur+tipi)+repcount*totalrep
            print 'stop',(tdur+tipi)*icount+tdur+repcount*totalrep
            d = d+tonePip(freqs[icount],2.5,(icount)*(tdur+tipi)+repcount*totalrep,(tdur+tipi)*icount+tdur+repcount*totalrep,0, **kwds)
    return d
_allFuncs = dict([(k, v) for k, v in globals().items() if callable(v)])
