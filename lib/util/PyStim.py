#!/usr/bin/env python
"""
PyStim is the module for computing stimulus waveforms for electrophysiolgical
experiments.

March 2, 2009
Paul B. Manis, Ph.D.
UNC Chapel Hill.

"""

from numpy import *
from Utility import *
from pylab import * # matplot lib for testing plots


# a PyStim object is a single waveform, along with the controlling parameters
class PyStim():
    
    def __init__(self):
        self.type = 'pulse'
        self.rate = 0.1 # in msec
        self.Stim_Duration = 100.0 # in msec, of the waveform
        self.Pulse_level = 100.0
        self.Pulse_delay = 5.0 # delay to first pulse
        self.Pulse_ipi = 10.0 # in msec, interpulse interval
        self.Pulse_np = 2 # number of pulses
        self.Pulse_dur =  10.0 # pulse duration in msec

        self.Step_Durations = [10, 100.0, 200.0, 50.0]
        self.Step_Levels = [0, -100.0, 100.0, 0.0]
        self.dac = 0
        self.sequence = '-100;100/100 & 5;10/2'
        self.seqtype = 'ld'
        self.seqstep = [0] # 0 is ALL pulses in train, otherwise it is selected ones
        self.Stim = []
        self.time = []
#
#pseudocode for make pulses:
# prodalldim = prod(shape(seq)) # this is how many entries are in the table
#prodotherdims = prodalldim/len(seq[0]) # current other dimensions.
#us = seq[0].repeat(product of other dimensions) # makes array of length needed, with repeats
#for all dimensions  kexcept the first:
#    prodotherdims = prodalldim/len(seq[k]
#    us = seq[k].repeat(prodotherdims)
#    ns = us[k].reshape(len(seq[k]), prodotherdims
#    na = ns.T.reshape(prod(shape(ns[k])))
#    us = column_stack((us, na))
#

    def makeAllPulses(self):
        seq = seqparse(self.sequence) # get the sequence(s)
        nent = 1
        for n in range(0, len(seq)):
            nent = nent * len(seq[n]) #compute the number of elements needed
        nother = nent/len(seq[0])
        pa = seq[0].repeat(nother) # fill the array with repeats
        for k in range(1, len(seq)): # now handle all the other dimensions
            nseq = len(seq[k])
            nother = nent/nseq
            ns = seq[k].repeat(nother) # repeats against the other dimensions
            ns = ns.reshape(nseq, nother)
            ns = ns.T.reshape(prod(shape(ns)))
            pa = column_stack((pa, ns)) # creates an k*n arrray, where k is the number of stimuli and n is the number of varing parameters
        ps = shape(pa)
        for k in range(0, ps[0]):
            dur = self.Pulse_dur
            ipi = self.Pulse_ipi
            lev = self.Pulse_level # initial values
            # in this loop, should check that len seqtype is <= len(seq)
            for n in range(0, len(self.seqtype)): # iterate over the values in the sequence
                if len(ps) is 1:
                    v = pa[k]
                else:
                    v = pa[k,n]
                if self.seqtype[n] is 'l': # assign variable values
                    lev = v
                if self.seqtype[n] is 'd':
                    dur = v
                if self.seqtype[n] is 'i':
                    ipi = v
#                print "lev: %6.1f dur: %6.1f ipi: %6.1f, self.seqtype: %s" % (lev, dur, ipi, self.seqtype[n])
                self.Stim.append(self.makePulse(lev, dur, ipi))
        
# make one pulse waveform with the specfied paramaters
    def makePulse(self, level, duration, ipi):
        w = self._zeroStim() # first generate a zero pulse array
        pdur = floor(duration/self.rate)
        pdelay = floor(self.Pulse_delay/self.rate)
        pipi = floor(ipi/self.rate)
        pstart = pdelay + cumsum(self.Pulse_np*[pipi]) - pipi
        for p in pstart:
            w[int(p):int(p+pdur)] = [level]*pdur
        return(w)
        
    def makeStimTime(self):
        self.time = arange(0, self.Stim_Duration, self.rate)
        
    def _zeroStim(self):
        self.points = floor(self.Stim_Duration/self.rate)
        w = array([0]*self.points)
        return(w)
        
    def getStim(self):
        return(self.wave)

# routine for debugging - plot the data
    def showStim(self):
        figure(1)
        clf()
        sh = shape(self.Stim)
        if len(self.time) is 0:
            self.makeStimTime()
        for i in range(0, sh[0]):
            plot(self.time, self.Stim[i])
        show()

def testcase():
    ns = PyStim()
    ns.makeAllPulses()
    ns.showStim()
    

if __name__ == "__main__":
    testcase()


