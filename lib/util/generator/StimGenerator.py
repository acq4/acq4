#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
StimGenerator.py -  Stimulus waveform generator + Qt widget
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

The StimGenerator class is a Qt widget that provides a text box for 
entering python code used to generate waveforms. Functions available
for evaluation are provided in waveforms.py.
"""

import sys, types, re
from numpy import *
import numpy
from PyQt4 import QtCore, QtGui
from advancedTypes import OrderedDict
from functions import logSpace
from GeneratorTemplate import *
import waveforms
from debug import *

#from pyqtgraph.parametertree.parameterTypes import SimpleParameter, GroupParameter
from StimParamSet import StimParamSet
from SeqParamSet import SequenceParamSet

import units

class StimGenerator(QtGui.QWidget):
    
    sigDataChanged = QtCore.Signal()        ## Emitted when the output of getSingle() is expected to have changed
    sigStateChanged = QtCore.Signal()       ## Emitted when the output of saveState() is expected to have changed
    sigParametersChanged = QtCore.Signal()  ## Emitted when the sequence parameter space has changed
    sigFunctionChanged = QtCore.Signal()    ## Emitted when the waveform-generating function has changed
    
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        #self.timeScale = 1.0
        #self.scale = 1.0
        self.offset = 0.0
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.ui.functionText.setFontFamily('Courier')
        #self.ui.paramText.setFontFamily('Courier')
        self.ui.errorText.setVisible(False)
        
        self.simpleMode = True  ## if True, then the current state was generated from 
                                ## the simple tree. Otherwise, it was generated in advanced mode.
        
        self.pSpace = None    ## cached sequence parameter space
        
        self.cache = {}       ## cached waveforms
        self.cacheRate = None
        self.cacheNPts = None
        
        #self.advancedGroup = [
            #self.ui.advSplitter,
            ##self.ui.functionText,
            ##self.ui.seqTree,
            #self.ui.errorBtn,
            #self.ui.helpBtn,
        #]
        self.updateWidgets()
        
        self.meta = {  ## holds some extra information about signals (units, expected scale and range, etc)
                       ## mostly information useful in configuring SpinBoxes
            'x': {},
            'y': {},
            'xy': {}  ## values that are the product of x and y values
        }
        
        ## variables that are added into the function evaluation namespace.
        self.extraParams = {}
        
        ## Simple stim generator
        self.stimParams = StimParamSet()
        self.ui.stimulusTree.setParameters(self.stimParams)
        self.stimParams.sigTreeStateChanged.connect(self.stimParamsChanged)
        
        ## advanced stim generator
        self.seqParams = SequenceParamSet()
        self.ui.seqTree.setParameters(self.seqParams)
        self.seqParams.sigTreeStateChanged.connect(self.seqParamsChanged)
        self.ui.functionText.textChanged.connect(self.funcChanged)
        
        self.ui.updateBtn.clicked.connect(self.update)
        self.ui.autoUpdateCheck.clicked.connect(self.autoUpdateClicked)
        self.ui.errorBtn.clicked.connect(self.updateWidgets)
        self.ui.helpBtn.clicked.connect(self.updateWidgets)
        self.ui.advancedBtn.toggled.connect(self.updateWidgets)
        self.ui.forceAdvancedBtn.clicked.connect(self.forceAdvancedClicked)
        self.ui.forceSimpleBtn.clicked.connect(self.forceSimpleClicked)

    def setEvalNames(self, **kargs):
        """Make variables accessible for use by evaluated functions."""
        self.extraParams.update(kargs)
        self.clearCache()
        self.autoUpdate()
        
    def delEvalName(self, name):
        del self.extraParams[name]
        self.clearCache()
        self.autoUpdate()

    def widgetGroupInterface(self):
        return (self.sigStateChanged, StimGenerator.saveState, StimGenerator.loadState)

    #def setTimeScale(self, s):
        #"""Set the scale factor for X axis. See setScale for description."""
        #if self.timeScale != s:
            #self.timeScale = s
            #self.clearCache()
            #self.autoUpdate()

    #def setScale(self, s):
        #"""Set the scale factor to be applied to all generated data.
        #This allows, for example, to write waveform functions with values
        #in units of mV and have the resulting data come out in units of V.
           #pulse(10, 10, 100) => gives pulse 100 units tall, but a scale
                                 #factor of 1e-3 converts it to 0.1 units
        #This should become obsolete--instead we would write the function like
           #pulse(10*ms, 10*ms, 100*mV)
        #This is more verbose but far less ambiguous.
        #"""
        #if self.scale != s:
            #self.scale = s
            #self.clearCache()
            #self.autoUpdate()

    def setOffset(self, o):
        """Set the offset to be added to all generated data.
        This allows, for example, writing a pulse waveform such that 0 is 
        always assumed to mean the current holding value."""
        if self.offset != o:
            self.offset = o
            self.clearCache()
            self.autoUpdate()
            
    def setMeta(self, axis, **args):
        """Set meta data for X, Y, and XY axes. This is used primarily to configure
        SpinBoxes to display the correct units, limits, step sizes, etc.
        Suggested args are:
            suffix='units', dec=True, minStep=1e-3, step=1, limits=(min, max)        
        """
        self.meta[axis].update(args)
        self.stimParams.setMeta(axis, args)

    def clearCache(self):
        self.cache = {}
    
    def functionString(self):
        return str(self.ui.functionText.toPlainText())
    
    def update(self):
        ## Let others know that waveform generation has changed.
        ## Note: it's generally better to call autoUpdate instead.
        if self.test():
            self.sigDataChanged.emit()
    
    def autoUpdate(self):
        if self.ui.autoUpdateCheck.isChecked():
            self.update()
    
    def autoUpdateClicked(self):
        self.autoUpdate()
        self.sigStateChanged.emit()        

    #def errorBtnClicked(self, b):
        #self.updateWidgets()
        ##if b:  ## resize error text box if it is too small
            ##height = self.ui.advSplitter.height()
            ##sizes = self.ui.advSplitter.sizes()
            ##if sizes[2] < height/3.:
                ##diff = (height/3.) - sizes[2]
                ##sizes[2] = height/3.
                ##r = float(sizes[0]) / (sizes[0]+sizes[1])
                ##sizes[0] -= diff * r 
                ##sizes[1] -= diff * (1-r)
                ##self.ui.advSplitter.setSizes(sizes)

    def forceSimpleClicked(self):
        self.ui.advancedBtn.setChecked(False)
        self.setSimpleMode(True)

    def forceAdvancedClicked(self):
        self.ui.advancedBtn.setChecked(True)
        self.setSimpleMode(False)

    def updateWidgets(self):
        ## show/hide widgets depending on the current mode.
        if self.ui.advancedBtn.isChecked():
            self.ui.errorText.setVisible(self.ui.errorBtn.isChecked())
            #for w in self.advancedGroup:
                #w.show()
            #self.ui.stimulusTree.hide()
            if self.ui.helpBtn.isChecked():
                self.ui.stack.setCurrentIndex(3)
            else:
                self.ui.stack.setCurrentIndex(2)
        else:
            if self.simpleMode:
                self.ui.stack.setCurrentIndex(0)
            else:
                self.ui.stack.setCurrentIndex(1)
            #for w in self.advancedGroup:
                #w.hide()
            #self.ui.stimulusTree.show()
            self.ui.errorText.hide()

    def setSimpleMode(self, simple):
        self.simpleMode = simple
        self.updateWidgets()

    def funcChanged(self):
        ## called when the function string changes
        self.clearCache()
        self.setSimpleMode(False)
        
        if self.test(): # test function. If ok, auto-update
            self.autoUpdate()
            self.sigFunctionChanged.emit()
        self.sigStateChanged.emit()

    def seqParamsChanged(self, *args):
        ## called when advanced sequence parameter tree has changed
        
        ## need to filter out some uninteresting events here..
        
        self.setSimpleMode(False)
        self.clearCache()
        self.pSpace = None
        if self.test():
            self.autoUpdate()
        self.sigParametersChanged.emit()
        self.sigStateChanged.emit()
    
    def stimParamsChanged(self, param, changes):
        ## called when the simple stim generator tree changes
        funcStr, params = self.stimParams.compile()
        
        self.blockSignals(True) ## avoid emitting dataChanged signals twice
        try:
            self.seqParams.setState(params)
        finally:
            self.blockSignals(False)
        self.sigParametersChanged.emit()
        
        self.ui.functionText.setPlainText(funcStr)
        self.setSimpleMode(True)

    
    
    def test(self):
        try:
            self.paramSpace()
            self.setError()
        except:
            self.setError("Error parsing parameters:\n" + str(sys.exc_info()[1]))
            return False
        try:
            self.getSingle(1, 1, params={'test': True})
            self.setError()
            return True
        except:
            self.setError("Error in function:\n" + str(sys.exc_info()[1]))
            return False
    
    def saveState(self):
        """ Return a dict structure with the state of the widget """
        #print "Saving state:", self.functionString()
        return ({'function': self.functionString(), 'params': self.seqParams.getState(), 'autoUpdate': self.ui.autoUpdateCheck.isChecked()})
    
    def loadState(self, state):
        """set the parameters with the new state"""
        if 'function' in state:
            self.ui.advancedBtn.setChecked(True)
            self.ui.functionText.setPlainText(state['function'])
            
        if 'params' in state:
            self.ui.advancedBtn.setChecked(True)
            #self.ui.paramText.setPlainText(state['params'])
            self.seqParams.setState(state['params'])
            self.setSimpleMode(False)
        if 'autoUpdate' in state:
            self.ui.advancedBtn.setChecked(False)
            self.ui.autoUpdateCheck.setChecked(state['autoUpdate'])
            self.setSimpleMode(True)

    def paramSpace(self):
        """Return an ordered dict describing the parameter space"""
        ## return looks like:
        ## {
        ##   'param1': (singleVal, [sequence]),
        ##   'param2': (singleVal, [sequence]),
        ##   ...
        ## }
        
        if self.pSpace is None:
            #self.pSpace = seqListParse(self.paramString()) # get the sequence(s) and the targets
            self.pSpace = self.seqParams.compile()
        return self.pSpace


    def listSequences(self):
        """ return an ordered dict of the sequence parameter names and values in the same order as that
        of the axes returned by get Sequence"""
        ps = self.paramSpace()
        
        #l = [(k, (ps[k][1]*self.scale)+self.offset) for k in ps.keys() if ps[k][1] != None]
        l = [(k, ps[k][1]) for k in ps.keys() if ps[k][1] != None]
        d = OrderedDict(l)
        
        ## d should look like: { 'param1': [val1, val2, ...],  ...  }
        return d
        
    def flatParamSpace(self):
        """return a list of every point in the parameter space"""
        l = self.listSequences()
        shape = tuple(l.values())
        ar = ones(shape)
        return argwhere(ar)
        
    def setError(self, msg=None):
        if msg is None or msg == '':
            self.ui.errorText.setText('')
            self.ui.errorBtn.setStyleSheet('')
        else:
            self.ui.errorText.setText(msg)
            self.ui.errorBtn.setStyleSheet('QToolButton {border: 2px solid #F00; border-radius: 3px}')
            
        
    def getSingle(self, rate, nPts, params=None):
        """
        Return a single generated waveform (possibly cached) with the given sample rate
        number of samples, and sequence parameters.        
        """
        if params is None:
            params = {}
        if not re.search(r'\w', self.functionString()):
            return None
            
        if self.cacheRate != rate or self.cacheNPts != nPts:
            self.clearCache()
            
        paramKey = tuple(params.items())
        if paramKey in self.cache:
            return self.cache[paramKey]
            
        self.cacheRate = rate
        self.cacheNPts = nPts
            
        ## create namespace with generator functions. 
        ##   - iterates over all functions provided in waveforms module
        ##   - wrap each function to automatically provide rate and nPts arguments
        ns = {}
        #arg = {'rate': rate * self.timeScale, 'nPts': nPts}
        arg = {'rate': rate, 'nPts': nPts}
        ns.update(arg)  ## copy rate and nPts to eval namespace
        for i in dir(waveforms):
            obj = getattr(waveforms, i)
            if type(obj) is types.FunctionType:
                ns[i] = self.makeWaveFunction(i, arg)
        
        ## add current sequence parameter values into namespace
        seq = self.paramSpace()
        for k in seq:
            if k in params:  ## select correct value from sequence list
                try:
                    ns[k] = float(seq[k][1][params[k]])
                except IndexError:
                    print "Requested value %d for param %s, but only %d in the param list." % (params[k], str(k), len(seq[k][1]))
                    raise
            else:  ## just use single value
                ns[k] = float(seq[k][0])

        ## add units into namespace
        ns.update(units.allUnits)
        
        ## add extra parameters to namespace
        ns.update(self.extraParams)

        ## evaluate and return
        fn = self.functionString().replace('\n', '')
        
        ret = eval(fn, globals(), ns)
        if isinstance(ret, ndarray):
            #ret *= self.scale
            ret += self.offset
            #print "===eval===", ret.min(), ret.max(), self.scale
        if 'message' in arg:
            self.setError(arg['message'])
        else:
            self.setError()
            
        self.cache[paramKey] = ret
        return ret
        
    def makeWaveFunction(self, name, arg):
        ## Creates a copy of a wave function (such as steps or pulses) with the first parameter filled in
        ## Must be in its own function so that obj is properly scoped to the lambda function.
        obj = getattr(waveforms, name)
        return lambda *args, **kwargs: obj(arg, *args, **kwargs)
        


#def seqListParse(text):
    #s = OrderedDict()
    #for l in text.split('\n'):
        #if re.match(r'\w', l):
            #(name, single, seq) = seqParse(l)
            #s[name] = (single, seq)
    #return s
    

#def seqParse(seqStr):
    #seqStr = re.sub(r'\s', '', seqStr)
    
    ### Match like this: "varName=singleValue;sequenceString"
    #valRegex = r'(([\deE\-\.]+)\s*(\*\s*(\w+))?)'  ## matches -1.03e-3.8 * mV
    #m = re.match(r'(\w+)='+valRegex+r'(;$|;(.*))?$', seqStr)
    #if m is None:
        #raise Exception("Syntax error in variable definition '%s'" % seqStr)
    #(name, single, junk, seqStr) = m.groups()
    #if seqStr is None:  ## no sequence specified, return now
        #return (name, single, None)
    
    ### Match list format: "[val1,val2,...]"
    #m = re.match(r'\[[\deE\-\.,]+\]$', seqStr)
    #if m is not None:
        #seq = array(eval(seqStr))
        #return (name, single, seq)
    
    ### Match like this: "start:stop/length:opts" or "start:stop:step:opts"
    #m = re.match(r'([\deE\-\.]+):([\deE\-\.]+)(/|:)([\deE\-\.]+)(:(\w+))?$', seqStr)
    #if m is None:
        #raise Exception("Syntax error in sequence string '%s'" % seqStr)
    
    #(v1, v2, stepChar, v3, junk, opts) = m.groups()
    #v1 = float(v1)
    #v2 = float(v2)
    #v3 = float(v3)
    #if opts is None:
        #opts = ''
    
    #if stepChar == '/':
        #if 'l' in opts:
            #seq = logSpace(v1, v2, v3)
        #else:
            #seq = linspace(v1, v2, v3)
    #else:
        #if 'l' in opts:
            #n = (log(v2/v1) / log(v3)) + 1
            #seq = logSpace(v1, v2, n)
        #else:
            #seq = arange(v1, v2, v3)
    #if 'r' in opts:
        #random.shuffle(seq)
    #return (name, single, seq)



        
        