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
        self.timeScale = 1.0
        self.scale = 1.0
        self.offset = 0.0
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.ui.functionText.setFontFamily('Courier')
        self.ui.paramText.setFontFamily('Courier')
        self.ui.errorText.setVisible(False)
        self.cacheOk = False
        self.cache = {}
        self.cacheRate = None
        self.cacheNPts = None
        QtCore.QObject.connect(self.ui.functionText, QtCore.SIGNAL('textChanged()'), self.funcChanged)
        QtCore.QObject.connect(self.ui.paramText, QtCore.SIGNAL('textChanged()'), self.paramChanged)
        QtCore.QObject.connect(self.ui.updateBtn, QtCore.SIGNAL('clicked()'), self.update)
        QtCore.QObject.connect(self.ui.autoUpdateCheck, QtCore.SIGNAL('clicked()'), self.autoUpdateClicked)
        QtCore.QObject.connect(self.ui.errorBtn, QtCore.SIGNAL('clicked()'), self.errorBtnClicked)
        QtCore.QObject.connect(self.ui.helpBtn, QtCore.SIGNAL('clicked()'), self.helpBtnClicked)

    def widgetGroupInterface(self):
        return ('stateChanged', StimGenerator.saveState, StimGenerator.loadState)

    def setTimeScale(self, s):
        if self.timeScale != s:
            self.timeScale = s
            self.clearCache()
            self.autoUpdate()

    def setScale(self, s):
        if self.scale != s:
            self.scale = s
            self.clearCache()
            self.autoUpdate()

    def setOffset(self, o):
        if self.offset != o:
            self.offset = o
            self.clearCache()
            self.autoUpdate()

    def clearCache(self):
        self.cache = {}

    def update(self):
        if self.test():
            self.emit(QtCore.SIGNAL('dataChanged'))
        
    def autoUpdate(self):
        if self.ui.autoUpdateCheck.isChecked():
            self.update()
            
    def autoUpdateClicked(self):
        self.autoUpdate()
        self.emit(QtCore.SIGNAL('stateChanged'))        
        
    def errorBtnClicked(self):
        self.ui.errorText.setVisible(self.ui.errorBtn.isChecked())
        
    def helpBtnClicked(self):
        if self.ui.helpBtn.isChecked():
            self.ui.stack.setCurrentIndex(1)
        else:
            self.ui.stack.setCurrentIndex(0)

    def funcChanged(self):
        # test function. If ok, auto-update
        self.clearCache()
        if self.test():
            self.autoUpdate()
            self.emit(QtCore.SIGNAL('functionChanged'))
        self.emit(QtCore.SIGNAL('stateChanged'))
        
        
    def paramChanged(self):
        # test params. If ok, auto-update
        self.clearCache()
        self.cacheOk = False
        if self.test():
            self.autoUpdate()
        self.emit(QtCore.SIGNAL('parametersChanged'))
        self.emit(QtCore.SIGNAL('stateChanged'))
        
    def functionString(self):
        return str(self.ui.functionText.toPlainText())
        
    def paramString(self):
        return str(self.ui.paramText.toPlainText())
    
    
    
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
        return ({'function': self.functionString(), 'params': self.paramString(), 'autoUpdate': self.ui.autoUpdateCheck.isChecked()})
    
    def loadState(self, state):
        """set the parameters with the new state"""
        if 'function' in state:
            self.ui.functionText.setPlainText(state['function'])
        if 'params' in state:
            self.ui.paramText.setPlainText(state['params'])            
        if 'autoUpdate' in state:
            self.ui.autoUpdateCheck.setChecked(state['autoUpdate'])
    
    def listSequences(self):
        """ return an ordered dict of the sequence parameter names and values in the same order as that
        of the axes returned by get Sequence"""
        ps = self.paramSpace()
        l = [(k, (ps[k][1]*self.scale)+self.offset) for k in ps.keys() if ps[k][1] != None]
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
            
        ## create namespace with generator functions
        ns = {}
        arg = {'rate': rate * self.timeScale, 'nPts': nPts}
        for i in dir(waveforms):
            obj = getattr(waveforms, i)
            if type(obj) is types.FunctionType:
                ns[i] = self.makeWaveFunction(i, arg)
        
        ## add parameter values into namespace
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
        
        ## evaluate and return
        fn = self.functionString().replace('\n', '')
        ret = eval(fn, globals(), ns)
        if isinstance(ret, ndarray):
            ret *= self.scale
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
        
    def paramSpace(self):
        """Return an ordered dict describing the parameter space"""
        ## return looks like:
        ## {
        ##   'param1': (singleVal, [sequence]),
        ##   'param2': (singleVal, [sequence]),
        ##   ...
        ## }
        
        if not self.cacheOk:
            self.pSpace = seqListParse(self.paramString()) # get the sequence(s) and the targets
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
    m = re.match(r'(\w+)=([\deE\-\.]+)(;$|;(.*))?$', seqStr)
    if m is None:
        raise Exception("Syntax error in variable definition '%s'" % seqStr)
    (name, single, junk, seqStr) = m.groups()
    if seqStr is None:  ## no sequence specified, return now
        return (name, single, None)
    
    ## Match list format: "[val1,val2,...]"
    m = re.match(r'\[[\deE\-\.,]+\]$', seqStr)
    if m is not None:
        seq = array(eval(seqStr))
        return (name, single, seq)
    
    ## Match like this: "start:stop/length:opts" or "start:stop:step:opts"
    m = re.match(r'([\deE\-\.]+):([\deE\-\.]+)(/|:)([\deE\-\.]+)(:(\w+))?$', seqStr)
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
    if 'r' in opts:
        random.shuffle(seq)
    return (name, single, seq)
