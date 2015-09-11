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
    
    us=1e-6
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
    d=amplitude+sawWave(risfall*us,amplitude,0,0,risfall*us, **kwds)
    #+pulse(params,risfall*us,(stop-risfall)*us,amplitude)
    #d=np.cos(amplitude+sawWave(params,risfall*us,amplitude,0,0,risfall*us)+pulse(risfall*us,(stop-risfall)*us,amplitude)-sawWave(params,risfall*us,amplitude,0,(stop-risfall)*us,stop*us))**2*sineWave(float(1/freq))
    return d
    # linramp=np.pi/2+sawWave(risfall*us,np.pi/2,0,0,risfall*us)+pulse(risfall*us,(stop-risfall)*us,np.pi/2)-sawWave(risfall*us,np.pi/2,0,(stop-risfall)*us,stop*us)
    # cos2gat=np.cos(linramp)**2
    # d=cos2gat*sineWave(1/freq)

    #np.cos(1.5707963+sawWave(0.0025,1.5707963,0,0,0.0025)+pulse(0.0025,0.0475,1.5707963)-sawWave(0.0025,1.5707963,0,0.0475,0.05))**2*sineWave(0.002)
    #np.cos(1.5707963+sawWave(0.2,1.5707963,0,0,0.2)+pulse(0.2,1.8,1.5707963)-sawWave(0.2,1.5707963,0,1.8,2))**2*sineWave(.002)

    # ## initialize array
        # d = np.empty(nPts)
        # d[:] = base
        
        # ## Define start and end points
        # if start is None:
        #     start = 0
        # else:
        #     start = int(start * rate)
        # if stop is None:
        #     stop = nPts-1
        # else:
        #     stop = int(stop * rate)
            
        # if stop > nPts-1:
        #     WARNING += "WARNING: Function is longer than generated waveform\n"    
        #     stop = nPts-1
            
        # cycleTime = int(period * rate)
        # if cycleTime < 10:
        #     WARNING += 'Warning: Period is less than 10 samples\n'
        
        # #d[start:stop] = np.fromfunction(lambda i: amplitude * np.sin(phase * 2.0 * np.pi + i * 2.0 * np.pi / (period * rate)), (stop-start,))
        # d[start:stop] = amplitude * np.sin(phase * 2.0 * np.pi + np.arange(stop-start) * 2.0 * np.pi / (period * rate))
        # return d
        
_allFuncs = dict([(k, v) for k, v in globals().items() if callable(v)])
