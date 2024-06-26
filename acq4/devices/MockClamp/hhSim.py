# -*- coding: utf-8 -*-
from __future__ import print_function

"""
Simple Hodgkin-Huxley simulator for Python. VERY slow.
Includes Ih from Destexhe 1993 [disabled]
Also simulates voltage clamp and current clamp with access resistance.

Luke Campagnola 2013
"""

import numpy as np
import scipy.integrate
from acq4.util import Qt
#import scipy.weave

um = 1e-6
cm = 1e-2
uF = 1e-6

Raccess = 1e5
Cpip = 3e-12

Radius = 20 * um
Area = (4 * 3.1415926 * Radius**2)
C = Area * uF / cm**2
gNa = 40e-3 * Area/cm**2
gK =  12e-3 * Area/cm**2
gKShift = 0
gL =  0.1e-3 * Area/cm**2
gH = 30. * Area/cm**2  ## 10mS * cm^2

EK = -77e-3
ENa = 50e-3
EL = -55e-3
EH = -43e-3
Ik2 = 24.3

Alpha_t0 = 500.  # msec
Alpha_tau = 2.0
gAlpha = 1e-3 * Area/cm**2
EAlpha = -7e-3  # V

def IK(n, Vm):
    return gK * n**4 * (Vm - EK)
    
def INa(m, h, Vm):
    return gNa * m**3 * h * (Vm - ENa)

def IL(Vm):
    return gL * (Vm - EL)

def IH(Vm, f, s):
    return gH * f * s * (Vm - EH)

def IAlpha(Vm, t):
    if t < Alpha_t0:
        return 0.
    else:
        # g = gmax * (t - onset)/tau * exp(-(t - onset - tau)/tau)
        tn = t - Alpha_t0
        if tn > 10.0 * Alpha_tau:
            return 0.
        else:
            return gAlpha * (Vm - EAlpha)*(tn/Alpha_tau) * np.exp(-(tn-Alpha_tau)/Alpha_tau)


def hh(y, t, mode, cmd, dt):
    ## y is a vector [Ve, Vm, m, h, n, f, s], function returns derivatives of each variable
    ## with respect to time.
    ## t is current time expressed in ms.
    ## mode is 'ic' or 'vc'
    ## cmd is an array of ic or vc command values
    ## dt gives the time step of the command data.
    mode = mode.lower()
    (Ve, Vm, m, h, n, f, s) = y
    
    ## Select between vc and ic
    if cmd is None:
        cmd = 0
        mode = 'ic'
    else:
        # interpolate command -- sharp steps confuse the integrator.
        fInd = t/dt
        ind = min(len(cmd)-1, np.floor(fInd))
        ind2 = min(len(cmd)-1, ind+1)
        s = fInd - ind
        cmd = cmd[int(ind)] * (1-s) + cmd[int(ind2)] * s
        
    # determine current generated by voltage clamp 
    if mode == 'vc':
        G = 50e-6 # arbitrary vc gain
        cmd = (cmd-Ve) * G
        
    # Compute current through tip of pipette
    Iaccess = (Ve-Vm) / Raccess
    
    # Compute change in electrode potential
    dve = 1e-3 * (cmd - Iaccess) / Cpip    # 1e-3 is because t is expressed in ms
    
    # Compute change in membrane potential
    Im = (Iaccess - INa(m, h, Vm) - IK(n, Vm) - IL(Vm) - IH(Vm, f, s) - IAlpha(Vm, t))
    dv = 1e-3 * Im / C    # 1e-3 is because t is expressed in ms
    
    ## Compute changes in gating parameters
    Vm = Vm + 65e-3   ## gating parameter eqns assume resting is 0mV
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
    
    # Ih is disabled--very slow.
    #Hinf = 1.0 / (1.0 + np.exp((Vm + 68.9) / 6.5))
    #tauF = np.exp((Vm + 158.6)/11.2) / (1.0 + np.exp((Vm + 75.)/5.5))
    #tauS = np.exp((Vm + 183.6) / 15.24)
    #df = (Hinf - f) / tauF
    #ds = (Hinf - s) / tauS
    df = 0
    ds = 0
    
    return [dve, dv, dm, dh, dn, df, ds]


    

#import pyqtgraph as pg
#win = pg.GraphicsWindow()
#plt1 = win.addPlot(labels={'left': ('Vm', 'V'), 'bottom': ('Time', 's')})
#win.nextRow()
#plt2 = win.addPlot(labels={'left': ('Im', 'A'), 'bottom': ('Time', 's')})

def runSim(initState, mode='ic', cmd=None, dt=0.1, dur=100, **args):
    npts = int(dur/dt)
    t = np.linspace(0, dur, npts)
    result = np.empty((npts, 9))
    
    # Run the simulation
    (result[:,2:], info) = scipy.integrate.odeint(hh, initState, t, (mode, cmd, dt),
                                          rtol=1e-6, atol=1e-6, hmax=5e-2,full_output=1, **args)
    result[:,0] = t
   # print info
    # Compute electrode current sans pipette capacitance current
    t, Im, Ve, Vm, m, h, n, f, s = [result[:,i] for i in range(result.shape[1])]
    result[:,1] = (Ve-Vm) / Raccess
    
    return result  ## result is array with dims: [npts, (time, Ie, Ve, Vm, Im, m, h, n, f, s)]


initState = [-65e-3, -65e-3, 0.05, 0.6, 0.3, 0.0, 0.0]


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

    dt = cmd['dt'] * 1e3  ## convert s -> ms
    data = cmd['data']
    mode = cmd['mode'].lower()
    
    result = runSim(initState, cmd=data, mode=mode, dt=dt, dur=dt*len(data))
    
    initState = result[-1, 2:]
    if mode in ['ic', 'i=0']:
        out = result[:,2] + np.random.normal(size=len(data), scale=0.3e-3)
    elif mode == 'vc':
        out = result[:,1] + np.random.normal(size=len(data), scale=3.e-12)
    else:
        raise ValueError(f"Unknown clamp mode {mode!r}")
    
    return out


# provide a visible test to make sure code is working and failures are not ours.
# call this from the command line to observe the clamp plot results
#
if __name__ == '__main__':
    import pyqtgraph as pg
    from acq4.util import Qt
    app = Qt.QApplication([])
    win = pg.GraphicsWindow()
    win.resize(1000,600)
    win.setWindowTitle('Testing hhSim.py')
    p = win.addPlot(title='vc')
    npts = 10000.
    x1 = 2000.
    x2 = 7000.
    x = np.arange(-100, 41, 50)
    cmd = np.ones((len(x), npts))*-65.0*1e-3
    data = np.zeros((len(x), npts))
    dt = 1e-4
    tb = np.arange(0, npts*dt, dt)
    for i, v in enumerate(x):
        print('V: ', v)
        cmd[i, x1:x2] = v*1e-3
        opts = {
            'mode': 'vc',
            'dt': dt,
            'data': cmd[i,:]
        }
        data[i,:] = run(opts)
        p.plot(tb, data[i])

    Qt.QApplication.instance().exec_()
