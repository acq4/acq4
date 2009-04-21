#!/usr/bin/env python
"""
PyStim is the module for computing stimulus waveforms for electrophysiolgical
experiments.

The classes include:
PyWave, which makes a single waveform
Stimulator, which manages a list of PyStim objects to generate the
   appropriate DAC commands, and interfaces with the gui.
PyStim, which provides an interface and calls the Stimulator.
This module generates the waveforms and combines them for the different
output channels, but it does not interface to the hardware.

March 2, 2009
Paul B. Manis, Ph.D.
UNC Chapel Hill.

"""
from numpy import *
from Utility import *
from pylab import * # matplot lib for testing plots
from PyQt4 import Qt, QtCore, QtGui
import PyQt4.Qwt5 as Qwt
from PyQt4.Qwt5.anynumpy import *
from PyStim_gui import Ui_Stimulator
import MPlot
import Utility

Utils = Utility.Utility()

NChannels = 8
class PyStim(QtGui.QMainWindow):
    """ PyStim creates an object with multiple stimulus channels
    and handles the GUI interface. 
    """
    def __init__(self):        
        """ PyStim.__init__ defines standard variables, and initialzes the GUI interface
        """
        QtGui.QDialog.__init__(self)
        self.ui = Ui_Stimulator() 
        self.ui.setupUi(self)
        
        self.Stim = Stimulator(NChannels) # build stimulator structure
        self.StimPlots = MPlot.MPlot() # engate our own "stimplots"
        self.current = 0 # start with waveform # set to 0
        self.ui.PyStim_WaveNo.setMaximum(NChannels-1) # limit wave
        self.pasteParameters(self.current, initialize=True) # display the current item
        self.connect(self.ui.PyStim_WaveNo, QtCore.SIGNAL("valueChanged(int)"),
                    self.pasteParameters) # capture change in wave selection
        self.connect(self.ui.PyStim_Compute, QtCore.SIGNAL("clicked()"),
                    self.computeAll) # compute and display waveforms
        self.computeAll() # build the first set of waveforms
        
    def pasteParameters(self, wavesel, initialize=False):
        """PasteParameters posts the data to the GUI fields."""
        if initialize is False:
            self.getParameters() # first read the parameters from the screen
            self.current = int(self.ui.PyStim_WaveNo.value())
        else:
            self.current = wavesel
        type = self.Stim.stim[self.current].type
        self.ui.PyStim_Seq.setText(self.Stim.stim[self.current].sequence)
        self.ui.PyStim_DAC.setValue(self.Stim.stim[self.current].dac)
        self.ui.PyStim_On.setChecked(self.Stim.stim[self.current].on)
        # map stim type
        if type == "Step":
            self.ui.PyStim_StimTab.setCurrentIndex(0)
            self.ui.PyStim_Durs.setText(self.Stim.stim[self.current].Step_Durations)
            self.ui.PyStim_Levels.setText(self.Stim.stim[self.current].Step_Levels)
        if type == "Pulse":
            self.ui.PyStim_StimTab.setCurrentIndex(1)
            self.ui.PyStim_Duration.setText(self.Stim.stim[self.current].Pulse_Duration)
            self.ui.PyStim_Level.setText(self.Stim.stim[self.current].Pulse_Level)
            self.ui.PyStim_NP.setValue(self.Stim.stim[self.current].Pulse_NP)
            self.ui.PyStim_IPI.setText(self.Stim.stim[self.current].Pulse_IPI)
            self.ui.PyStim_Delay.setText(self.Stim.stim[self.current].Pulse_Delay)
            self.ui.PyStim_RecoveryDelay.setText(self.Stim.stim[self.current].Pulse_RecoveryDelay)
#
# Grab parameters from the GUI
#
    def getParameters(self):
        """ getParameters reads the GUI fields and stores the values in the PyStim parameters."""
#        self.current = self.ui.PyStim_WaveNo.value()
        tab = self.ui.PyStim_StimTab.currentIndex()
        self.Stim.stim[self.current].type = str(self.ui.PyStim_StimTab.tabText(tab))
        type = str(self.Stim.stim[self.current].type)
        self.Stim.stim[self.current].sequence = self.ui.PyStim_Seq.text()
        self.Stim.stim[self.current].dac = int(self.ui.PyStim_DAC.value())
        self.Stim.stim[self.current].on = self.ui.PyStim_On.isChecked()
        # map stim type
        if type == "Step":
            self.ui.PyStim_StimTab.setCurrentIndex(0)
            self.Stim.stim[self.current].Step_Durations = self.ui.PyStim_Durs.text()
            self.Stim.stim[self.current].Step_Levels = self.ui.PyStim_Levels.text()
        if type == "Pulse":
            self.ui.PyStim_StimTab.setCurrentIndex(1)
            self.Stim.stim[self.current].Pulse_NP = self.ui.PyStim_NP.value()
            self.Stim.stim[self.current].Pulse_IPI = self.ui.PyStim_IPI.text()
            self.Stim.stim[self.current].Pulse_Delay = self.ui.PyStim_Delay.text()
            self.Stim.stim[self.current].Pulse_RecoveryDelay = self.ui.PyStim_RecoveryDelay.text()
            self.Stim.stim[self.current].Pulse_Duration = self.ui.PyStim_Duration.text()
            self.Stim.stim[self.current].Pulse_Level = self.ui.PyStim_Level.text()
            
    def computeAll(self):
        """ Read the parameters from the gui and compute all waveforms."""
        self.getParameters() # read the the most recent values in the display
#        self.report()
        self.Stim.compute() # compute the waveforms
        self.display()
    
    def report(self):
        for current in range(0, len(self.Stim.stim)):
            type = self.Stim.stim[current].type
            print "Wave: %d Type: %s DAC: %d  status: %d" % (current, type,
                                                            self.Stim.stim[current].dac,
                                                            self.Stim.stim[current].on)
            if self.Stim.stim[current].on:
                if type == 'Step':
                    print "    StepDur: %s\n    StepLevs: %s" % (self.Stim.stim[current].Step_Durations,
                                             self.Stim.stim[current].Step_Levels)
                if type == 'Pulse':
                    print "    PulseNP: %d  Pulse IPI: %s  Pulse Delay: %s" % (self.Stim.stim[current].Pulse_NP,
                                                                     self.Stim.stim[current].Pulse_IPI,
                                                                     self.Stim.stim[current].Pulse_Delay)
                    print "    Pulse Dur: %s    Pulse Level: %s" % (
                        self.Stim.stim[current].Pulse_Duration, self.Stim.stim[current].Pulse_Level)
        print "-------------"
        
    def display(self):
        """Display all the stimulus waveforms for the user."""
        (d, t) = self.Stim.getWaves()
        ndac = len(d.keys())
        dk = d.keys()
        tk = t.keys()
        # build the plot display first
        self.StimPlots.Erase(self.ui.PlotWindow) # clear out previous plots in widget
        pl = [[]]*(ndac)
        i = 0
        for dac in d.keys():
            pl[i] = self.StimPlots.subPlot(self.ui.PlotWindow, ndac, 1, i)
            if i == ndac-1:
                xAxisF = True
            else:
                xAxisF = False
            self.StimPlots.PlotReset(pl[i], xlabel='Time', unitsX= 'ms',
                        ylabel='units', unitsY= 'ms', textName='Waves',
                        linemode = 'steps', xAxisOn = xAxisF, bkcolor = 'k')
            print shape(d[dac])
            for j in range(0, shape(d[dac])[0]):
                self.StimPlots.PlotLine(pl[i], t[dac], d[dac][j],
                        color = 'w', symbol=None, symbolsize = 0, dataID='Stim')
            i = i + 1
        self.StimPlots.sameScale(pl, ysame = False)
        pl[-1].enableAxis(Qwt.QwtPlot.xBottom, True)
        
class Stimulator():
    """The Stimulator class creates an bank of stimulus waveforms, with
    each stimulus waveform based on the PyWave class."""
    def __init__(self, n): # n is the number of waveforms/max channels in the stimulator
        stim = []
        for i in range(0, n):
            stim.append(PyWave())
            if i > 1:
                stim[i].on = False
            else:
                stim[i].on = True
            if i == 1:
                stim[i].type = 'Pulse'
                stim[i].sequence = 'l1:100;500/50'
                stim[i].dac = 1
        self.stim = stim
        self.index = 0
    
    def getWaves(self):
        """ getWaves"""
        # first find out how many stim are on  and how many DACs are selected in the list
        daclist = [] # list of dacs specified
        dacwave = {} # dacwave is a dictionary of waveforms.
        timewave = {}
        ndac = 0
        for s in self.stim:
            if s.on is True:
                if s.dac not in daclist:
                    daclist.append(s.dac)
                    dacwave[s.dac] = s.getStim()
                    s.makeStimTime()
                    timewave[s.dac] = s.time
                else:
                    print "Multiple Waves cannot go to one DAC: only the first one will be used"
                #    dacwave[s.dac] = self.__addWaves(dacwave[s.dac], s.getStim())
        return (dacwave, timewave)
    
    def compute(self):
        for s in self.stim:
            if s.on is True:
                s.makeAllPulses()
                
    def __addWaves(self, w1, w2):
        s1 = shape(w1)
        s2 = shape(w2)
        for i in range(0, s2[0]):
            for j in range(0, s1[0]):
                lw1 = s1[1]
                lw2 = s2[1]
                maxl = max(lw1, lw2)
                if maxl > lw1:
                    w1[j] = append(w1[j], array([w1[j][-1]]*(maxl-lw1))) # extend the last point out
                if maxl > lw2:
                    w2[i] = append(w2[i], array([w2[i][-1]]*(maxl-lw2)))
        print shape(w1)
        print shape(w2)
        return(w1 + w2)

class PyWave():
    """A Wave object defines a single waveform, along with the controlling parameters
    normally, you will create multiple PyWave objects according to the waveforms
    you need
    """    
    def __init__(self):
        self.type = 'Step'
        self.name = 'IV'
        self.rate = 0.1 # clocking rate, in msec
        self.Stim_Duration = 100.0 # in msec, of the waveform
        self.sequence = 'l2:-100;0/10' 
        # pulse parameters
        self.Pulse_Level = '10'
        self.Pulse_Delay = '10' # delay to first pulse
        self.Pulse_RecoveryDelay = '0' # delay to recovery - 0 indicates no recovery test
        self.Pulse_IPI = '20' # in msec, interpulse interval
        self.Pulse_NP = 2 # number of pulses
        self.Pulse_Duration =  '0.1' # pulse duration in msec
        # step parameters
        self.Step_Durations = '10, 100, 50, 20'
        self.Step_Levels = '0, 0, 0, 0'
        self.dac = 0 # target output DAC channel
        self.on = Qt.Qt.Checked # to turn the Stim on or off for the channel
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
        """ makeAllPulses takes the wave parameters, and generates the sequence of
        waves as defined by the sequence. The waves are returned as a variable of
        the PyStim object.
        """
        self.Stim = [] # always generate a clean sequence
        (seq, seqpar) = seqparse(self.sequence) # get the sequence(s) and the targets
        if seq is [] or len(seq) == 0:
            print "Sequence did not parse - check syntax"
            return
        nent = 1
        for n in range(0, len(seq)):
            nent = nent * len(seq[n]) #compute the number of elements needed
        nother = nent/len(seq[0])
        seql = seq[0].repeat(nother) # fill the array with repeats
        for k in range(1, len(seq)): # now handle all the other dimensions
            nseq = len(seq[k])
            nother = nent/nseq
            ns = seq[k].repeat(nother) # repeats against the other dimensions
            ns = ns.reshape(nseq, nother)
            ns = ns.T.reshape(prod(shape(ns)))
            seql = column_stack((seql, ns)) # creates an k*n arrray, where k is the number of stimuli and n is the number of varing parameters
        seqsh = shape(seql)

        if self.type == 'Pulse':
            for k in range(0, seqsh[0]):
                dur = float(str(self.Pulse_Duration))
                ipi = float(str(self.Pulse_IPI))
                lev = float(str(self.Pulse_Level)) # initial values
                delay = float(str(self.Pulse_Delay))
                rdelay = float(str(self.Pulse_RecoveryDelay))
                np = self.Pulse_NP
                # in this loop, should check that len seqtype is <= len(seq)
                for n in range(0, len(seqpar)): # iterate over the values in the sequence
                    if len(seqsh) is 1:
                        v = seql[k]
                    else:
                        v = seql[k,n]
                    if seqpar[n][0] is 'l': # assign variable values
                        lev = v
                    if seqpar[n][0] is 'w': # individual pulse width
                        dur = v
                    if seqpar[n][0] is 'i': # interpulse interval
                        ipi = v
                    if seqpar[n][0] is 'n': # number of pulses
                        np = v
                    if seqpar[n][0] is 'd': # Delay
                        delay = v
                    if seqpar[n][0] is 'r': # recovery delay
                        rdelay = v
                    self.Stim.append(self.__makePulse(lev, dur, ipi, delay, rdelay, np))
            
        if self.type == 'Step':
            # check for valid data:
            p = re.compile('[\s,]+') # we make spaces and/or commas into just commas
            sdur = p.sub(',', str(self.Step_Durations))
            slev = p.sub(',', str(self.Step_Levels))
            sdur = array(eval(sdur)) # convert input strings
            slev = array(eval(slev))
            if shape(sdur) != shape(slev):
                print "Duration and level arrays are unmatched"
                return
            for k in range(0, seqsh[0]):
                # in this loop, should check that len seqtype is <= len(seq)
                for n in range(0, len(seqpar)): # iterate over the values in the sequence
                    dur = sdur
                    lev = slev # provide clean initial values
                    seqpos = int(seqpar[n][1])-1 # Count from 1, not 0
                    if len(seqsh) is 1:
                        v = seql[k]
                    else:
                        v = seql[k,n]
                    if seqpar[n][0] is 'l': # assign variable values
                        lev[seqpos] = v
                    if seqpar[n][0] is 'd':
                        dur[seqpos] = v
                    self.Stim.append(self.__makeStep(lev, dur))
        # now make sure the arrays are all the same length in case we changed durations etc.
        maxlen = 0
        for k in range(0, len(self.Stim)):
           if len(self.Stim[k]) > maxlen: # find out max array length
                maxlen = len(self.Stim[k])
        for k in range(0, len(self.Stim)):
            if len(self.Stim[k]) < maxlen:
                self.Stim[k] = append(self.Stim[k], array(zeros(maxlen-len(self.Stim[k])+self.Stim[k][-1])))

    def __makePulse(self, level, duration, ipi, delay, rdelay, np):
        """Make one pulse waveform with the specfied paramaters."""
        self.Stim_Duration = delay + np*ipi + duration+1.0
        if rdelay > 0:
            self.Stim_Duration = self.Stim_Duration + rdelay
        w = self.__zeroStim() # first generate a zero pulse array
        pdur = floor(duration/self.rate)
        pdelay = floor(delay/self.rate)
        pipi = floor(ipi/self.rate)
        pstart = pdelay + cumsum(np*[pipi]) - pipi
        for p in pstart:
            w[int(p):int(p+pdur)] = level
        if rdelay > 0:
            rnp = 1
            pdelay = floor(rdelay/self.rate) + p # recovery is relative to last pulse in train
            pstart = pdelay + cumsum(rnp*[pipi]) - pipi
            for p in pstart:
                w[int(p):int(p+pdur)] = level
        return(w)

    def __makeStep(self, levs, durs):
        """Make one step waveform with the specfied paramaters."""
        self.Stim_Duration = sum(durs)
        w = self.__zeroStim() # first generate a zero pulse array
        durs = concatenate([array([0]), durs]) # start at 0 time
        pdur = floor(durs/self.rate)
        pstart = cumsum(floor(durs/self.rate))
        for p in range(0, len(pstart)-1):
            w[int(pstart[p]):int(pstart[p]+pdur[p+1])] = levs[p]
        w[int(pstart[-1]+pdur[-1]):] = levs[-1]
        return(w)
        
    def makeStimTime(self):
        self.time = arange(0, self.Stim_Duration, self.rate)
        
    def __zeroStim(self):
        self.points = floor(self.Stim_Duration/self.rate)
        w = array([0]*self.points)
        return(w)
        
    def getStim(self): # I think this is redundant.
        return(self.Stim)

def testcase():
    """ testcases generates a Stimulator object, calculates the waveforms, and
    displays the result.
    """
    ns = Stimulator(9)
    ns.compute()
    ns.display()
    
if __name__ == "__main__":
    """ if called from the command line, we are in a "test" mode and execute
    some waveform computation operations.
    """
    app = QtGui.QApplication(sys.argv)
    MainWindow = PyStim()
    MainWindow.show()
    sys.exit(app.exec_())



