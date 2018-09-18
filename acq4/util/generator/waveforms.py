# -*- coding: utf-8 -*-
from __future__ import print_function
"""
waveforms.py -  Waveform functions used by StimGenerator
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

This file defines several waveform-generating functions meant to be
called from within a StimGenerator widget.
"""

import numpy

## Checking functions
def isNum(x):
    return hasattr(x, '__int__')
    
def isNumOrNone(x):
    return (x is None) or isNum(x)
    
def isList(x):
    return hasattr(x, '__len__')
    
def isNumList(x):
    return isList(x) and (len(x) > 0) and isNum(x[0])

## Functions to allow in eval for the waveform generator. 
## The first parameter is always a dict which will at least contain 'rate' and 'nPts'.
##   this parameter is automatically supplied, and will not be entered by the end user.
## These should be very robust with good error reporting since end users will be using them.


def pulse(params, times, widths, values, base=0.0):
    nPts = params['nPts']
    rate = params['rate']
    if not isList(times):
        times = [times]
    if not isList(widths):
        widths = [widths] * len(times)
    if not isList(values):
        values = [values] * len(times)
        
    d = numpy.empty(nPts)
    d[:] = base
    for i in range(len(times)):
        t1 = int(times[i] * rate)
        wid = int(widths[i] * rate)
        if wid == 0:
            params['message'] = "WARNING: Pulse width %f is too short for rate %f" % (widths[i], rate)
        if t1+wid >= nPts:
            params['message'] = "WARNING: Function is longer than generated waveform."
        d[t1:t1+wid] = values[i]
    return d

def steps(params, times, values, base=0.0):
    rate = params['rate']
    nPts = params['nPts']
    if not isList(times):
        raise Exception('times argument must be a list')
    if not isList(values):
        raise Exception('values argument must be a list')
    
    d = numpy.empty(nPts)
    d[:] = base
    for i in range(1, len(times)):
        t1 = int(times[i-1] * rate)
        t2 = int(times[i] * rate)
        
        if t1 == t2:
            params['message'] = "WARNING: Step width %f is too short for rate %f" % (times[i]-times[i-1], rate)
        if t2 >= nPts:
            params['message'] = "WARNING: Function is longer than generated waveform."
        d[t1:t2] = values[i-1]
    last = int(times[-1] * rate)
    d[last:] = values[-1]
    return d
    
def sineWave(params, period, amplitude=1.0, phase=0.0, start=0.0, stop=None, base=0.0):
    rate = params['rate']
    nPts = params['nPts']
    params['message'] = ""

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
    d = numpy.empty(nPts)
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
        params['message'] += "WARNING: Function is longer than generated waveform\n"    
        stop = nPts-1
        
    cycleTime = int(period * rate)
    if cycleTime < 10:
        params['message'] += 'Warning: Period is less than 10 samples\n'
    
    #d[start:stop] = numpy.fromfunction(lambda i: amplitude * numpy.sin(phase * 2.0 * numpy.pi + i * 2.0 * numpy.pi / (period * rate)), (stop-start,))
    d[start:stop] = amplitude * numpy.sin(phase * 2.0 * numpy.pi + numpy.arange(stop-start) * 2.0 * numpy.pi / (period * rate))
    return d
    
def squareWave(params, period, amplitude=1.0, phase=0.0, duty=0.5, start=0.0, stop=None, base=0.0):
    rate = params['rate']
    nPts = params['nPts']
    params['message'] = ""

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
    
    ## initialize array
    d = numpy.empty(nPts)
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
        params['message'] += "WARNING: Function is longer than generated waveform\n"    
        stop = nPts-1
    
    pulseWidth = int(duty * period * rate)
    phase = (phase % 1.0) - 1.0
    pulseShift = int(phase * period * rate)
    
    cycleTime = int(period * rate)
    if cycleTime < 10:
        params['message'] += 'Warning: Period is less than 10 samples\n'
    if cycleTime < 1:
        return numpy.zeros(nPts)
        
    nCycles = 2 + int((stop-start) / float(period*rate))
    for i in range(nCycles):
        ptr = start + int(i*period*rate)
        a = ptr + pulseShift
        if a > stop:
            break
        b = a + pulseWidth
        a = max(a, start)
        b = min(b, stop)
        if a >= b:
            continue
        d[a:b] = amplitude
    
    return d
    
def sawWave(params, period, amplitude=1.0, phase=0.0, start=0.0, stop=None, base=0.0):
    rate = params['rate']
    nPts = params['nPts']
    params['message'] = ""

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
    d = numpy.empty(nPts)
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
        params['message'] += "WARNING: Function is longer than generated waveform\n"    
        stop = nPts-1
    #if period * rate < 10:
        #params['message'] += "Warning: period is less than 10 samples\n"
        
    cycleTime = int(period * rate)
    if cycleTime < 10:
        params['message'] += 'Warning: Period is less than 10 samples\n'
    if cycleTime < 1:
        return numpy.zeros(nPts)
    
    #d[start:stop] = amplitude * numpy.fromfunction(lambda t: (phase + t/float(rate*period)) % 1.0, (stop-start,))
    d[start:stop] = amplitude * ((phase + numpy.arange(stop-start)/float(rate*period)) % 1.0)
    return d

    
def listWave(params, period, values=None, phase=0.0, start=0.0, stop=None, base=0.0):
    rate = params['rate']
    nPts = params['nPts']
    params['message'] = ""

    ## Check all arguments 
    if type(values) not in [list, tuple, numpy.ndarray]or len(values) < 1:
        raise Exception("Values argument must be a list or array")
    values = numpy.array(values)
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
    d = numpy.empty(nPts)
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
        params['message'] += "WARNING: Function is longer than generated waveform\n"    
        stop = nPts-1

    cycleTime = int(period * rate)
    if cycleTime < 10:
        params['message'] += 'Warning: Period is less than 10 samples\n'
    if cycleTime < 1:
        return numpy.zeros(nPts)

    #saw = numpy.fromfunction(lambda t: len(values) * ((phase + t/float(rate*period)) % 1.0), (stop-start,))
    saw = len(values) * ((phase + numpy.arange(stop-start)/float(rate*period)) % 1.0)
    d[start:stop] = values[saw.astype(int).clip(0, len(values)-1)]
    #d[start:stop] = saw
    return d

def noise(params, mean, sigma, start=0.0, stop=None):
    rate = params['rate']
    nPts = params['nPts']
    params['message'] = ""
    
    if not isNum(mean):
        raise Exception("Mean argument must be a number")
    if not isNum(sigma):
        raise Exception("Sigma argument must be a number")
    if not isNumOrNone(start):
        raise Exception("Start argument must be a number")
    if not isNumOrNone(stop):
        raise Exception("Stop argument must be a number")
    
    
    ## initialize array
    d = numpy.zeros(nPts)
    
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
        params['message'] += "WARNING: Function is longer than generated waveform\n"    
        stop = nPts-1

    d[start:stop] = numpy.random.normal(size=stop-start, loc=mean, scale=sigma)
    return d