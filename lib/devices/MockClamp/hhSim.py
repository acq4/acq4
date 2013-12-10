# -*- coding: utf-8 -*-
"""
Simple Hodgkin-Huxley simulator for Python. VERY slow.
Includes Ih from Destexhe 1993
"""

import numpy as np
from scipy.integrate import odeint
#import pyqtgraph as pg
from PyQt4 import QtGui, QtCore
import scipy.weave

Area = 2e-6
C = 1e-6 * Area
gNa = 120e-3 * Area
gK =  36e-3 * Area
gKShift = 0
gL =  0.3e-3 * Area
gH = 0.0
EK = -77e-3
ENa = 50e-3
EL = -55e-3
EH = -43e-3


def IK(n, Vm):
    return gK * n**4 * (Vm - EK)
    
def INa(m, h, Vm):
    return gNa * m**3 * h * (Vm - ENa)

def IL(Vm):
    return gL * (Vm - EL)

def IH(Vm, f, s):
    return gH * f * s * (Vm - EH)

def hh(y, t, ccFn=None, vcFn=None):
    ## y is a vector [Vm, m, h, n, f, s], function returns derivatives of each variable
    (Vm, m, h, n, f, s) = y
    
    ## Select between VC and CC
    if vcFn is not None:
        Vcmd = vcFn(t)
        dv = Vcmd-Vm
    else:
        ## Determine command current
        if ccFn is None:
            ICmd = 0
        else:
            Icmd = ccFn(t)
        ## Compute change in membrane potential
        dv = (Icmd - INa(m, h, Vm) - IK(n, Vm) - IL(Vm) - IH(Vm, f, s)) / C
    
    ## Compute changes in gating parameters
    Vm += 65e-3   ## gating parameter eqns assume resting is 0mV
    Vm *= 1000.   ##  ..and that Vm is in mV
    
    am = (2.5-0.1*Vm) / (np.exp(2.5-0.1*Vm) - 1.0)
    bm = 4. * np.exp(-Vm / 18.)
    dm = am * (1.0 - m) - bm * m
    
    ah = 0.07 * np.exp(-Vm / 20.)
    bh = 1.0 / (np.exp(3.0 - 0.1 * Vm) + 1.0)
    dh = ah * (1.0 - h) - bh * h
    
    an = (0.1 - 0.01*(Vm-gKShift)) / (np.exp(1.0 - 0.1*(Vm-gKShift)) - 1.0)
    bn = 0.125 * np.exp(-Vm / 80.)
    dn = an * (1.0 - n) - bn * n
    
    Hinf = 1.0 / (1.0 + np.exp((Vm + 68.9) / 6.5))
    tauF = np.exp((Vm + 158.6)/11.2) / (1.0 + np.exp((Vm + 75.)/5.5))
    tauS = np.exp((Vm + 183.6) / 15.24)
    df = (Hinf - f) / tauF
    ds = (Hinf - s) / tauS
    
    return [dv, dm*1000, dh*1000, dn*1000, df*1000, ds*1000]  ## gating variables assume t is in ms; multiply by 1000.

def runSim(initState, ccFn=None, vcFn=None, dt=0.1e-3, dur=0.1, **args):
    npts = int(dur/dt)
    t = np.linspace(0, dur, npts)
    result = np.empty((npts, 7))
    result[:,1:] = odeint(hh, initState, t, (ccFn, vcFn), **args)
    result[:,0] = t
    return result  ## result is array with dims: [npts, (time, Vm, Im, m, h, n, f, s)]


initState = [-65e-3, 0.05, 0.6, 0.3, 0.0, 0.0]

def run(cmd):
    """
    Accept command like 
    
        {
            'dt': 1e-4,
            'mode': 'ic',
            'data': np.array([...]),
        }
        
    Return array of Vm or Im values.        
    """
    global initState
    print cmd, cmd['data'].min(), cmd['data'].max()
    dt = cmd['dt'] * 1e3  ## convert s -> ms
    data = cmd['data']
    mode = cmd['mode']
    def dataFn(t):
        ind = min(len(data)-1, int(t/dt))
        return data[ind]
    
    if mode == 'ic':
        result = runSim(initState, ccFn=dataFn, dt=dt, dur=dt*len(data))

    elif mode == 'vc':
        result = runSim(initState, vcFn=dataFn, dt=dt, dur=dt*len(data))
        
    else:
        sys.stderr.write("Unknown mode '%s'" % sys.argv[1])
        raise Exception("Unknown mode '%s'" % sys.argv[1])

    initState = result[-1, 1:]
    if mode == 'ic':
        out = result[:,1] + np.random.normal(size=len(data), scale=0.3e-3)
    elif mode == 'vc':
        I = C * np.diff(result[:,1]) / dt
        I = np.append(I, I[-1])
        out = I + np.random.normal(size=len(data), scale=3.e-12)
    
    return out



def pulse(t, delay=5e-3, duration=100e-3, amplitude=20e-12):
    if t > delay and t < duration+delay:
        return amplitude
    else:
        return 0.0
    
def runPulseSequence(amps, mode='cc', delay=5e-3, duration=100e-3, post=100e-3):
    total = delay+duration+post
    results = []
    for amp in amps:
        def fn(t):
            return pulse(t, amplitude=amp, delay=delay, duration=duration)
        if mode == 'cc':
            results.append(runSim(ccFn=fn, dur=total))
        else:
            results.append(runSim(vcFn=fn, dur=total))
    return results


