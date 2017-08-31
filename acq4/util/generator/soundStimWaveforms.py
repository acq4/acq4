# -*- coding: utf-8 -*-
"""
soundStimWaveforms.py -  Waveform functions used by StimGenerator
Copyright 2016  Luke Campagnola 
Distributed under MIT/X11 license. See license.txt for more infomation.

This file defines several waveform-generating functions meant to be
called from within a StimGenerator widget. This functions are specific to
auditory stimulation so have been separated out from the more generic functions
in waveforms.py.
"""
import numpy as np
from scipy import signal
from acq4.util.generator import waveforms

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

def cos2gat(risfall=10.0, start=0.0, stop=500.0, **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']
    
    #ms=1e-3
    ## Check all arguments
    if not isNum(risfall):
        raise Exception("RisFall argument must be a number")
    if not isNumOrNone(start):
        raise Exception("Start argument must be a number")
    if not isNumOrNone(stop):
        raise Exception("Stop argument must be a number")

    amplitude=np.pi/2
    linramp= (amplitude + waveforms.sawWave(risfall,amplitude,0,start,(start+risfall), 0, **kwds)
                    + waveforms.pulse((start+risfall),(stop-risfall),amplitude, **kwds)
                    - waveforms.sawWave(risfall,amplitude,0,(stop-risfall),stop, **kwds))
    cos2gat=(np.cos(linramp))**2
    d=cos2gat

    return d

def tonePip(freq= 1000.0, risfall=10e-3, start=0.0, stop=500.0e-3, base=0.0, **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']
    
    #ms=1e-3
    ## Check all arguments
    if not isNum(freq) or freq <= 0:
        raise Exception("Frequency argument must be a number > 0") 
    if not isNum(risfall):
        raise Exception("RisFall argument must be a number")
    if not isNumOrNone(start):
        raise Exception("Start argument must be a number")
    if not isNumOrNone(stop):
        raise Exception("Stop argument must be a number")
    # amplitude=np.pi/2
    # linramp=amplitude+sawWave(risfall*ms,amplitude,0,start*ms,(start+risfall)*ms, 0, **kwds)+pulse((start+risfall)*ms,(stop-risfall)*ms,amplitude, **kwds)-sawWave(risfall*ms,amplitude,0,(stop-risfall)*ms,stop*ms, **kwds)
    # cos2gat=(np.cos(linramp))**2
    # d=cos2gat
    per = float(1./freq)
    d = cos2gat(risfall, start, stop, **kwds) * waveforms.sineWave(per, 1, 0, start, stop, 0, **kwds)
    return d
#def sawWave(period, amplitude=1.0, phase=0.0, start=0.0, stop=None, base=0.0, **kwds):    
#np.cos(1.570796+sawWave(2.5e-3,1.570796,0,.250,.250+2.5e-3,0)+pulse(.250+2.5e-3,497.5e-3,1.570796)-sawWave(2.5e-3,1.570796,0,497.5e-3,500e-3))**2*sineWave(1/4000.0,1,0,.250,.500,0)

# def soundstim(startfreq= 1000.0, npip= 11, tdur= 50, tipi= 200, direction= 'up', **kwds):  #tfr 09/28/2015
def soundstim(startfreq= 1000.0, npip= 11, tdur= 50, tipi= 400, octspace = 0.5, reps=1, direction= 'up', delay = 0, **kwds):
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
    d = 0
    totalrep = npip*(tdur+tipi)
    for repcount in np.arange(reps):
        freqs = startfreq * 2**(dirconst * np.arange(npip))
        

        for icount in np.arange(npip):
            #d = d+tonePip(freqs[icount],2.5,(icount)*250,250*icount+50,0, **kwds) #tropp 09/28/2015
            print 'icount', icount
            print 'repcount', repcount
            print 'start', (icount)*(tdur+tipi)+repcount*totalrep+delay
            print 'stop',(tdur+tipi)*icount+tdur+repcount*totalrep+delay
            print 'freqs', freqs
            d = d + tonePip(float(freqs[icount]), 2.5e-3, icount*(tdur+tipi) + repcount*totalrep+delay,(
                    tdur+tipi)*icount + tdur + repcount*totalrep + delay, 0, **kwds)
    return d

def noisestim(risfall=10.0, npip=11, tdur= 50, tipi = 50, reps = 1, delay = 0, **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']

## Check all arguments
    if not isNum(npip):
        raise Exception("npip argument must be a number")
    if not isNumOrNone(tdur):
        raise Exception("tdur argument must be a number")
    if not isNumOrNone(risfall):
        raise Exception("risfall argument must be a number")
    if not isNumOrNone(tipi):
        raise Exception("octspace argument must be a number between 0 and 1")
    
    d = 0
    totalrep = npip*(tdur+tipi)
    # for icount in np.arange(npip):
    #     d = d+noise(0,1,(icount)*(tdur+tipi),(tdur+tipi)*icount+tdur,**kwds)
    # return d
    for repcount in np.arange(reps):
        for icount in np.arange(npip):
            start = icount*(tdur+tipi) + repcount*totalrep + delay
            stop = icount*(tdur+tipi) + tdur+repcount*totalrep + delay
            d = d + cos2gat(risfall, start, stop, **kwds) * waveforms.noise(0, 1, start, stop, **kwds)
    return d
#     amplitude = np.random_sample([nPts])
#     d = tonePip(1000.0, 10.0, 0.0, 500.0, 0.0)
#     dd = amplitude*d
#     return dd

def sineAM(fC=16000.0, fM=10.0, risfall=2e-3, tdur=200e-3, tipi=150e-3, nstim=20, delay = 0, **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']

## Check all arguments
    if not isNum(nstim):
        raise Exception("npip must be a number")
    if not isNumOrNone(tdur):
        raise Exception("tdur  must be a number")
    if not isNumOrNone(risfall):
        raise Exception("risfall must be a number")
    if not isNumOrNone(tipi):
        raise Exception("tipi must be a number between 0 and 1")
    
    # def sineWave(period, amplitude=1.0, phase=0.0, start=0.0, stop=None, base=0.0, **kwds): 
    # def cos2gat(risfall=10.0, start=0.0, stop=500.0, **kwds):   
    d = 0
    for icount in np.arange(nstim):
        perM = float(1./fM)  # modulation period
        perC = float(1./fC)  # carrier period
        start = icount*(tdur+tipi)+delay
        stop = (tdur+tipi)*icount+tdur+delay
        sineC = waveforms.sineWave(perC, 1, 0, start, stop, 0, **kwds)
        sineM = 1 + 0.7*waveforms.sineWave(perM, 1, 0, start, stop, 0, **kwds)
        d = d + cos2gat(risfall, start, stop, **kwds)*sineC*sineM
    return d

# def soundstimAM(fM=10, startfreq= 1000.0, npip= 11, tdur= 50, tipi= 400, octspace = 0.5, reps=1, direction= 'up', **kwds):
#     rate = kwds['rate']
#     nPts = kwds['nPts']
#     warnings = kwds['warnings']

# ## Check all arguments
#     if not isNum(startfreq) or startfreq <= 0:
#         raise Exception("Frequency argument must be a number > 0") 
#     if not isNum(npip):
#         raise Exception("npip argument must be a number")
#     if not isNumOrNone(tdur):
#         raise Exception("tdur argument must be a number")
#     if not isNumOrNone(tipi):
#         raise Exception("tipi argument must be a number")
#     if not isNumOrNone(tipi):
#         raise Exception("octspace argument must be a number between 0 and 1")
#     posDirection=['up', 'down']
#     if direction not in posDirection:
#         raise Exception("direction must be up or down")

#     if direction == posDirection[0]:
#         dirconst = octspace
#     else:
#         dirconst = -1 * octspace
#     d=0
#     totalrep=npip*(tdur+tipi)
#     for repcount in np.arange(reps):
#         freqs = startfreq * 2**(dirconst * np.arange(npip))
        

#         for icount in np.arange(npip):
#             #d = d+tonePip(freqs[icount],2.5,(icount)*250,250*icount+50,0, **kwds) #tropp 09/28/2015
#             print 'icount', icount
#             print 'repcount', repcount
#             print 'start', (icount)*(tdur+tipi)+repcount*totalrep
#             print 'stop',(tdur+tipi)*icount+tdur+repcount*totalrep
#             print 'freqs', freqs
#             d = d+sineAM(freqs[icount],fM, 2.5e-3,tdur,tipi,1, **kwds)
#             # def sineAM(fC=16000.0, fM=10.0, risfall=2e-3, tdur=200e-3, tipi=150e-3, nstim=20, **kwds
#     return d

def narrowbandNoise(fC, bandwidth, start=0.0, stop=None, **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']
    #print 'sample rate', rate
    w = 0
    nyq = float(rate/2.0)
    low = (fC-(bandwidth/2.0))/nyq
    high = (fC+(bandwidth/2.0))/nyq
    BW = [low,high]
    b, a = signal.butter(4, BW, 'band', False, output='ba')
    BBN = waveforms.noise(0, 1, start, stop, **kwds)
    #print 'filter creation complete'
    if BBN.ndim == 1:
        sm = np.mean(BBN)
        w = signal.lfilter(b,a,BBN-sm)
        #print 'filtering complete'
        w = w + sm
    b, a = signal.ellip(4, 0.1, 120, BW, 'bandpass', False, output='ba')
    sm = np.mean(w)
    w = signal.lfilter(b, a, w-sm)
    w = w + sm
    return w

def NBNStim(fC=16000.0, bandwidth=4000.0, risfall=2.5e-3, tdur=200e-3, tipi=150e-3, nstim=20, delay=0,**kwds): 
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']

## Check all arguments
    if not isNum(nstim):
        raise Exception("npip argument must be a number")
    if not isNumOrNone(tdur):
        raise Exception("tdur argument must be a number")
    if not isNumOrNone(risfall):
        raise Exception("risfall argument must be a number")
    if not isNumOrNone(tipi):
        raise Exception("octspace argument must be a number between 0 and 1")
    
    # def sineWave(period, amplitude=1.0, phase=0.0, start=0.0, stop=None, base=0.0, **kwds): 
    # def cos2gat(risfall=10.0, start=0.0, stop=500.0, **kwds):   
    d = 0
    for icount in np.arange(nstim):
        start = icount*(tdur+tipi)+delay
        stop = icount*(tdur+tipi) + tdur + delay
        NBN = narrowbandNoise(fC, bandwidth, start, stop, **kwds)
        d = d + cos2gat(risfall, start, stop, **kwds)*NBN
    return d   

# #Building FM sweeps
# def FMfreqLinear(f0=5, f1=11, tcur=0, TotT=12, **kwds):
#     rate = kwds['rate']
#     nPts = kwds['nPts']
#     warnings = kwds['warnings']

#     ## Check all arguments
#     if not isNum(f0):
#         raise Exception("f0 argument must be a number")
#     if not isNumOrNone(f1):
#         raise Exception("f1 argument must be a number")
#     if not isNumOrNone(tcur):
#         raise Exception("tcur argument must be a number")
#     if not isNumOrNone(TotT):
#         raise Exception("TotT argument must be a number")

#     fcur = f0(1-tcur/TotT)+f1*tcur/TotT

#     return fcur

# def FMfreqLog(f0=5, f1=11, tcur=0, TotT=12, **kwds):
#     rate = kwds['rate']
#     nPts = kwds['nPts']
#     warnings = kwds['warnings']

#     ## Check all arguments
#     if not isNum(f0):
#         raise Exception("f0 argument must be a number")
#     if not isNumOrNone(f1):
#         raise Exception("f1 argument must be a number")
#     if not isNumOrNone(tcur):
#         raise Exception("tcur argument must be a number")
#     if not isNumOrNone(TotT):
#         raise Exception("TotT argument must be a number")

#     fcur = f0**(1-tcur/TotT)*tcur**f1/TotT

#     return fcur

# def FMmag(tcur=0, TotT=12, sigma=2.8, **kwds):
#     rate = kwds['rate']
#     nPts = kwds['nPts']
#     warnings = kwds['warnings']

#     ## Check all arguments
#     if not isNum(sigma):
#         raise Exception("sigma argument must be a number")
#     if not isNumOrNone(tcur):
#         raise Exception("tcur argument must be a number")
#     if not isNumOrNone(TotT):
#         raise Exception("TotT argument must be a number")

#     Acur=np.exp(-1*(tcur-TotT)/(2*sigma**2))

#     return Acur

# def FMsweep(f0=5, f1=11, start=0, stop=12, risfall=10.0, **kwds):
#     rate = kwds['rate']
#     nPts = kwds['nPts']
#     warnings = kwds['warnings']

#     ## Check all arguments
#     if not isNum(f0):
#         raise Exception("f0 argument must be a number")
#     if not isNumOrNone(f1):
#         raise Exception("f1 argument must be a number")
#     if not isNumOrNone(start):
#         raise Exception("start argument must be a number")
#     if not isNumOrNone(stop):
#         raise Exception("stop argument must be a number")

#     ## initialize array
#     d = np.empty(nPts)
#     d[:] = 0.0
  
#     ## Define start and end points
#     if start is None:
#         start = 0
#     else:
#         start = int(start * rate)
#     if stop is None:
#         stop = nPts-1
#     else:
#         stop = int(stop * rate)
        
#     if stop > nPts:
#         warnings.append("WARNING: Function is longer than generated waveform\n")
#         stop = nPts-1
#     calcrng=3
#     for nn in np.arange(calcrng):
        
#         FMamp = FMmag(5.0,12.0,2.8, **kwds)     
#         freq = FMfreqLog(f0,f1,spoint,12,**kwds)
#         period = 1/freq
#         cycleTime = int(period * rate)
#         if cycleTime < 10:
#             warnings.append('Warning: Period is less than 10 samples\n')
#         d[nn] = amplitude * np.sin(phase * 2.0 * np.pi + runvalue * 2.0 * np.pi / (period * rate))
#     d = cos2gat(risfall, start, stop,**kwds)*d
#     return d

def FMsweepLinear(f0, f1, start, stop, base=0.0, **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']
    
    ## Check all arguments 

    
    ## initialize array
    
    d = np.empty(nPts)
    d[:] = base
    
    ## Define start and end points
    if start is None:
        starttime = 0
    else:
        starttime = int(start * rate)
    if stop is None:
        stoptime = nPts-1
    else:
        stoptime = int(stop * rate)
    #d[start:stop] = amplitude * np.sin(phase * 2.0 * np.pi + np.arange(stop-start) * 2.0 * np.pi / (period * rate))
 
    delt = np.arange((stoptime-starttime))/rate
  #  samp = np.zeros(len(delt))
    samp = signal.chirp(delt, f0, np.max(delt), f1, method='linear', phi=0)
    # print 'length of samp:',len(samp)
    d[starttime:stoptime] = samp
    return d 

def FMsweepLogarithmic(f0, f1, start, stop, base=0.0, **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']
    
    ## Check all arguments 

    
    ## initialize array
    
    d = np.empty(nPts)
    d[:] = base
    
    ## Define start and end points
    if start is None:
        starttime = 0
    else:
        starttime = int(start * rate)
    if stop is None:
        stoptime = nPts-1
    else:
        stoptime = int(stop * rate)
    #d[start:stop] = amplitude * np.sin(phase * 2.0 * np.pi + np.arange(stop-start) * 2.0 * np.pi / (period * rate))

    delt = np.arange((stoptime-starttime))
    
    samp = np.zeros(len(delt))
    samp = signal.chirp(delt/rate, f0, stop, f1, method='logarithmic', phi=0)
   
    d[starttime:stoptime] = samp
    return d 

def FMSweepReversal(method='linear',sweeprate=12., upfirst=True, f0=5000., f1= 11000., delay=0.5, duration=2.0, risfall=0.1, **kwds):
    rate = kwds['rate']
    nPts = kwds['nPts']
    warnings = kwds['warnings']
    d = 0
    SWP = 0
    dir1 = 0
    dir2 = 0
    ## Check all arguments 
    #sweeprate is in number of sweeps per second
    #timeswitch = float(duration/2.0)
    #numsweeps=sweeprate
    numsweeps = int(sweeprate*duration/2.0)
    sweeplen = 0.5/sweeprate
    # print 'sweeplen',sweeplen
    # print 'numsweeps', numsweeps
    sweepstart = delay
    if not upfirst:
        t = f0
        f0 = f1
        f1 = t
    for counter in range(numsweeps):
        # print 'counter',counter
        if method == 'linear':
            upstart = sweepstart
            upstop = upstart + sweeplen # start + (counter+1)*sweeplen + delay
            dir1 = FMsweepLinear(f0, f1, upstart, upstop, base=0.0, **kwds)
            
            dwnstart = upstop
            dwnstop = dwnstart+sweeplen
            sweepstart = dwnstop
            dir2 = FMsweepLinear(f1, f0, dwnstart, dwnstop, base=0.0, **kwds)
            if counter == 0:
                SWP = dir1 + dir2
            else:
                SWP = SWP + dir1 + dir2
    
    d = cos2gat(risfall, delay, duration, **kwds) * SWP

    return d

_allFuncs = dict([(k, v) for k, v in globals().items() if callable(v)])