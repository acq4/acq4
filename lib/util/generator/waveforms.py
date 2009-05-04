# -*- coding: utf-8 -*-
import numpy

## Functions to allow in eval for the waveform generator. 
## The first parameter is always a dict which will at least contain 'rate' and 'nPts'.
##   this parameter is automatically supplied, and will not be entered by the end user.
## These should be very robust with good error reporting since end users will be using them.


def pulse(params, times, widths, values, base=0.0):
    nPts = params['nPts']
    rate = params['rate']
    if type(times) in [float, int]:
        times = [times]
    if type(times) not in [list, tuple]:
        raise Exception('times argument must be a list')
    if type(widths) not in [list, tuple]:
        widths = [widths] * len(times)
    if type(values) not in [list, tuple]:
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
    if type(times) not in [list, tuple]:
        raise Exception('times argument must be a list')
    if type(values) not in [list, tuple]:
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
    
    