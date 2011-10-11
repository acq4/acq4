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
from ParameterTree import Parameter, GroupParameter


class StimGenerator(QtGui.QWidget):
    
    sigDataChanged = QtCore.Signal()
    sigStateChanged = QtCore.Signal()
    sigParametersChanged = QtCore.Signal()
    sigFunctionChanged = QtCore.Signal()
    
    def __init__(self, parent=None):
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
        
        self.advancedGroup = [
            self.ui.functionText,
            self.ui.paramText,
            self.ui.errorBtn,
            self.ui.helpBtn,
        ]
        self.updateWidgets()
        
        self.meta = {  ## holds some extra information about signals (units, expected scale and range, etc)
                       ## mostly information useful in configuring SpinBoxes
            'x': {},
            'y': {},
            'xy': {}  ## values that are the product of x and y values
        }
        
        self.stimParams = StimParameter()
        self.stimParams.monitorChildren()
        self.ui.paramTree.setParameters(self.stimParams)
        self.stimParams.sigStateChanged.connect(self.stimParamsChanged)
        
        self.ui.functionText.textChanged.connect(self.funcChanged)
        self.ui.paramText.textChanged.connect(self.paramChanged)
        self.ui.updateBtn.clicked.connect(self.update)
        self.ui.autoUpdateCheck.clicked.connect(self.autoUpdateClicked)
        self.ui.errorBtn.clicked.connect(self.updateWidgets)
        self.ui.helpBtn.clicked.connect(self.updateWidgets)
        self.ui.advancedBtn.toggled.connect(self.updateWidgets)

    def widgetGroupInterface(self):
        return (self.sigStateChanged, StimGenerator.saveState, StimGenerator.loadState)

    def setTimeScale(self, s):
        """Set the scale factor for X axis. See setScale for description."""
        if self.timeScale != s:
            self.timeScale = s
            self.clearCache()
            self.autoUpdate()

    def setScale(self, s):
        """Set the scale factor to be applied to all generated data.
        This allows, for example, to write waveform functions with values
        in units of mV and have the resulting data come out in units of V.
           pulse(10, 10, 100) => gives pulse 100 units tall, but a scale
                                 factor of 1e-3 converts it to 0.1 units
        This should become obsolete--instead we would write the function like
           pulse(10*ms, 10*ms, 100*mV)
        This is more verbose but far less ambiguous.
        """
        if self.scale != s:
            self.scale = s
            self.clearCache()
            self.autoUpdate()

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

    def update(self):
        if self.test():
            #self.emit(QtCore.SIGNAL('dataChanged'))
            self.sigDataChanged.emit()
        
    def autoUpdate(self):
        if self.ui.autoUpdateCheck.isChecked():
            self.update()
            
    def autoUpdateClicked(self):
        self.autoUpdate()
        #self.emit(QtCore.SIGNAL('stateChanged'))        
        self.sigStateChanged.emit()        

    def updateWidgets(self):
        ## show/hide widgets depending on the current mode.
        if self.ui.advancedBtn.isChecked():
            for w in self.advancedGroup:
                w.show()
            self.ui.paramTree.hide()
            self.ui.errorText.setVisible(self.ui.errorBtn.isChecked())
            if self.ui.helpBtn.isChecked():
                self.ui.stack.setCurrentIndex(1)
            else:
                self.ui.stack.setCurrentIndex(0)
        else:
            self.ui.stack.setCurrentIndex(0)
            for w in self.advancedGroup:
                w.hide()
            self.ui.paramTree.show()
            self.ui.errorText.hide()
            



    def funcChanged(self):
        ## called when the function string changes
        # test function. If ok, auto-update
        self.clearCache()
        if self.test():
            self.autoUpdate()
            #self.emit(QtCore.SIGNAL('functionChanged'))
            self.sigFunctionChanged.emit()
        #self.emit(QtCore.SIGNAL('stateChanged'))
        self.sigStateChanged.emit()
        
        
    def paramChanged(self):
        ## called when the param string changes
        # test params. If ok, auto-update
        self.clearCache()
        self.cacheOk = False
        if self.test():
            self.autoUpdate()
        #self.emit(QtCore.SIGNAL('parametersChanged'))
        self.sigParametersChanged.emit()
        #self.emit(QtCore.SIGNAL('stateChanged'))
        self.sigStateChanged.emit()

    def stimParamsChanged(self):
        ## called when the simple stim generator tree changes
        func, params = self.stimParams.compile()
        self.ui.functionText.setPlainText(func)
        self.ui.paramText.setPlainText('\n'.join(params))

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



        
class StimParameter(GroupParameter):
    def __init__(self):
        GroupParameter.__init__(self, name='Stimuli', type='group',
                           addText='Add Stimulus..', addList=['Pulse', 'Pulse Train'])
        self.monitorChildren()  ## watch for changes throughout tree
        
    def addNew(self, type):
        if type == 'Pulse':
            self.addChild(PulseParameter())
        elif type == 'Pulse Train':
            self.addChild(PulseTrainParameter())

    def setMeta(self, axis, opts, root=None):  ## set units, limits, etc.
        if root is None:
            root = self
        for ch in root:
            if ch.opts.get('axis', None) == axis:   ## set options on any parameter that matches axis
                ch.setOpts(**opts)
            self.setMeta(axis, opts, root=ch)
            
    def compile(self):
        fns = []
        params = []
        for ch in self:
            fn, par = ch.compile()
            fns.append(fn)
            params.extend(par)
        return ' + \n'.join(fns), params

class SeqParameter(Parameter):
    def __init__(self, **args):
        axis = args.get('axis', None)
        args['params'] = [
            {'name': 'sequence', 'type': 'list', 'value': 'off', 'values': ['off', 'range', 'list']},
            {'name': 'start', 'type': 'float', 'axis': axis, 'value': 0, 'visible': False}, 
            {'name': 'stop', 'type': 'float', 'axis': axis, 'value': 0, 'visible': False}, 
            {'name': 'steps', 'type': 'int', 'value': 10, 'visible': False},
            {'name': 'log spacing', 'type': 'bool', 'value': False, 'visible': False}, 
            {'name': 'list', 'type': 'str', 'value': '', 'visible': False}, 
            {'name': 'randomize', 'type': 'bool', 'value': False, 'visible': False}, 
        ]
        args['expanded'] = args.get('expanded', False)
        Parameter.__init__(self, **args)
        self.sequence.sigValueChanged.connect(self.seqChanged)
        
    def seqChanged(self):
        if self['sequence'] == 'off':
            for ch in self:
                ch.hide()
        elif self['sequence'] == 'range':
            for ch in self:
                ch.show()
            self.list.hide()
        elif self['sequence'] == 'list':
            for ch in self:
                ch.hide()
            self.list.show()
            self.randomize.show()
        self.sequence.show()
        
    def compile(self):
        if self['sequence'] == 'off':
            return "%f"%self.value(), None
        else:
            name = "%s_%s" % (self.parent().name(), self.name())
            seq = "%s = %f; " % (name, self.value())
            if self['sequence'] == 'range':
                seq = seq + "%f:%f/%d" % (self['start'], self['stop'], self['steps'])
            elif self['sequence'] == 'list':
                seq = seq + str(self['list'])
        return name, seq
        
        
class PulseParameter(GroupParameter):
    def __init__(self, **kargs):
        GroupParameter.__init__(self, name="Pulse", autoIncrementName=True, type="pulse", removable=True, renamable=True,
            params=[
                SeqParameter(**{'name': 'start', 'type': 'float', 'axis': 'x', 'value': 0.01, 'suffix': 's', 'siPrefix': True, 'minStep': 1e-6, 'dec': True}),
                SeqParameter(**{'name': 'length', 'type': 'float', 'axis': 'x', 'value': 0.01, 'suffix': 's', 'siPrefix': True, 'minStep': 1e-6, 'dec': True}),
                SeqParameter(**{'name': 'amplitude', 'type': 'float', 'axis': 'y', 'value': 0}),
                SeqParameter(**{'name': 'sum', 'type': 'float', 'axis': 'xy', 'value': 0}),
            ], **kargs)
        self.length.sigValueChanged.connect(self.lenChanged)
        self.amplitude.sigValueChanged.connect(self.ampChanged)
        self.sum.sigValueChanged.connect(self.sumChanged)
        
    def lenChanged(self):
        self.sum.setValue(self['length'] * self['amplitude'], blockSignal=self.sumChanged)

    def ampChanged(self):
        self.sum.setValue(self['length'] * self['amplitude'], blockSignal=self.sumChanged)

    def sumChanged(self):
        self.length.setValue(self['sum'] / self['amplitude'], blockSignal=self.lenChanged)

    def compile(self):
        (start, seq1) = self.start.compile()
        (length, seq2) = self.length.compile()
        (amp, seq3) = self.amplitude.compile()
        fnStr = "pulse(%s, %s, %s)" % (start, length, amp)
        seq = [x for x in [seq1, seq2, seq3] if x is not None]
        return fnStr, seq
        

class PulseTrainParameter(GroupParameter):
    def __init__(self, **kargs):
        GroupParameter.__init__(self, name="Pulse Train", autoIncrementName=True, type="pulseTrain", removable=True, renamable=True,
        params=[
            {'name': 'start', 'type': 'float', 'value': 0.01, 'suffix': 's', 'siPrefix': True, 'minStep': 1e-6, 'dec': True},
            {'name': 'pulse length', 'type': 'float', 'value': 0.005, 'suffix': 's', 'siPrefix': True, 'minStep': 1e-6, 'dec': True},
            {'name': 'interpulse length', 'type': 'float', 'value': 0.01, 'suffix': 's', 'siPrefix': True, 'minStep': 1e-6, 'dec': True},
            {'name': 'pulse number', 'type': 'int', 'value': 10},
            {'name': 'amplitude', 'type': 'float', 'value': 0},
            {'name': 'sum', 'type': 'float', 'value': 0},
        ], **kargs)
        
        
        