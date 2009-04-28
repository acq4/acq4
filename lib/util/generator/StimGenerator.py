#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stim_Generator is the module for computing a single set of stimulus waveforms

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
import sys, types, re
from numpy import *
from PyQt4 import Qt, QtCore, QtGui
from lib.util.advancedTypes import OrderedDict
from lib.util.functions import logSpace
import waveforms

#import PyQt4.Qwt5 as Qwt
#from PyQt4.Qwt5.anynumpy import *
#from Stim_Form import Ui_Form
#import MPlot # our graphics support...


class StimGenerator(QtGui.QWidget):
    """ PyStim creates an object with multiple stimulus channels
    and handles the GUI interface. 
    """
    def __init__(self, parent=None):
        """ PyStim.__init__ defines standard variables, and initialzes the GUI interface
        """
        QtGui.QWidget.__init__(self, parent)
        self.layout = QtGui.QVBoxLayout(self)
        self.functionText = QtGui.QPlainTextEdit(self)
        self.sequenceText = QtGui.QPlainTextEdit(self)
        font = QtGui.QFont()
        font.setFixedPitch(True)
        self.functionText.setFont(font)
        self.sequenceText.setFont(font)
        self.layout.addWidget(self.functionText)
        self.layout.addWidget(self.sequenceText)
        
        self.cacheOk = False
        QtCore.QObject.connect(self.functionText, QtCore.SIGNAL('textChanged()'), self.funcChanged)
        QtCore.QObject.connect(self.sequenceText, QtCore.SIGNAL('textChanged()'), self.seqChanged)
        
    def funcChanged(self):
        self.emit(QtCore.SIGNAL('changed()'))
        
        
    def seqChanged(self):
        self.cacheOk = False
        self.emit(QtCore.SIGNAL('changed()'))
        
    def functionString(self):
        return str(self.functionText.toPlainText())
        
    def sequenceString(self):
        return str(self.sequenceText.toPlainText())
    
    def storeState(self):
        """ Return a dict structure with the state of the widget """
        return ({'waveform': self.functionString(), 'sequence': self.sequenceString()})
    
    def loadState(self, state):
        """set the parameters with the new state"""
        if 'waveform' in state:
            self.functionText.setPlainText(state['waveform'])
        if 'sequence' in state:
            self.sequenceText.setPlainText(state['sequence'])            
    
    def listSequences(self):
        """ return a list of the sequence parameter names in the same order as that
        of the axes returned by get Sequence"""
        ps = self.paramSpace()
        return [(k, len(ps[k][1])) for k in ps.keys() if ps[k][1] != None]
        
    def getSingle(self, rate, nPts, params={}):
        if not re.search(r'\w', self.functionString()):
            return None
            
        ## create namespace with generator functions
        ns = {}
        arg = {'rate': rate, 'nPts': nPts}
        for i in dir(waveforms):
            obj = getattr(waveforms, i)
            if type(obj) is types.FunctionType:
                ns[i] = lambda *args, **kwargs: obj(arg, *args, **kwargs)
        
        ## add parameter values into namespace
        seq = self.paramSpace()
        for k in seq:
            if k in params:  ## select correct value from sequence list
                ns[k] = float(seq[k][1][params[k]])
            else:  ## just use single value
                ns[k] = float(seq[k][0])
                
        ## evaluate and return
        return eval(self.functionString(), globals(), ns)
        
    def paramSpace(self):
        """Return an ordered dict describing the parameter space"""
        if not self.cacheOk:
            self.pSpace = seqListParse(self.sequenceString()) # get the sequence(s) and the targets
            self.cacheOk = True
        return self.pSpace


def seqListParse(text):
    s = OrderedDict()
    for l in text.split('\n'):
        if re.match(r'\w', l):
            (name, single, seq) = seqParse(l)
            s[name] = (single, seq)
    return s
    

def seqParse(seqStr):
    seqStr = re.sub(r'\s', '', seqStr)
    
    ## Match like this: "varName=singleValue;sequenceString"
    m = re.match(r'(\w+)=([\deE\-\.]+)(;(.*))?', seqStr)
    if m is None:
        raise Exception("Syntax error in variable definition '%s'" % seqStr)
    (name, single, junk, seqStr) = m.groups()
    if seqStr is None:  ## no sequence specified, return now
        return (name, single, None)
    
    ## Match list format: "[val1,val2,...]"
    m = re.match(r'\[[\deE\-\.,]+\]', seqStr)
    if m is not None:
        seq = eval(seqStr)
        return (name, single, seq)
    
    ## Match like this: "start:stop/length:opts" or "start:stop:step:opts"
    m = re.match(r'([\deE\-\.]+):([\deE\-\.]+)(/|:)([\deE\-\.]+)(:(\w+))?', seqStr)
    if m is None:
        raise Exception("Syntax error in sequence string '%s'" % seqStr)
    
    (v1, v2, stepChar, v3, junk, opts) = m.groups()
    v1 = float(v1)
    v2 = float(v2)
    v3 = float(v3)
    if opts is None:
        opts = ''
    
    if stepChar == '/':
        if 'l' in opts:
            seq = logSpace(v1, v2, v3)
        else:
            seq = linspace(v1, v2, v3)
    else:
        if 'l' in opts:
            n = (log(v2/v1) / log(v3)) + 1
            seq = logSpace(v1, v2, n)
        else:
            seq = arange(v1, v2, v3)
    print "seq:", seq
    if 'r' in opts:
        random.shuffle(seq)
    print "seqr:", seq
    return (name, single, seq)
