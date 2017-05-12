from PyQt4 import QtCore, QtGui
from acq4.devices.Device import TaskGui
from acq4.pyqtgraph.parametertree.ParameterTree import ParameterTree
from acq4.util.generator.StimParamSet import SeqParameter
import acq4.util.units as units
import sys
import numpy as np
import acq4.util.functions as fn

class TDTTaskGui(TaskGui):
    
    def __init__(self, dev, taskRunner):
        TaskGui.__init__(self, dev, taskRunner)
        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)
        #self.attenSpin = QtGui.QSpinBox()
        #self.attenSpin.setMaximum(120)
        #self.attenSpin.setMinimum(0)
        #self.attenSpin.setValue(30)
        #self.layout.addWidget(self.attenSpin)
        self.paramTree = ParameterTree()
        self.layout.addWidget(self.paramTree)
        self.attParam = SimpleSequenceParamSet(name='Attenuation', type='int', limits=[0,120], expanded=True, value=30, units='dB')
        self.paramTree.addParameters(self.attParam)

        self.attParam.sigSequenceChanged.connect(self.sequenceChanged)

    def sequenceChanged(self, paramSet, sequence):
        self.sequence = sequence
        self.sigSequenceChanged.emit(self.dev.name())

    def generateTask(self, params=None):
        
        if params is None or 'attenuation' not in params:
            attenuation = self.attParam.value()
        else:
            attenuation = self.sequence[params['attenuation']]
        
        task = {'PA5.1': {'attenuation': attenuation}}
        #print "TDT_Taskgui:", task
        return task

        

    
    def listSequence(self):
        """Return an OrderedDict of sequence parameter names and values {name: [val1, val2, val3]}"""
        #print "TDT compile:", self.attParam.compile()
        return {'attenuation': self.attParam.compile()[1]}

    def saveState(self):
        """Return a dictionary representing the current state of the widget."""
        return self.attParam.saveState()

    def restoreState(self, state):
        """Restore the state of the widget from a dictionary previously generated using saveState"""
        #attenuation = state.get('attenuation', 30)
        #self.attenSpin.setValue(attenuation)
        self.attParam.restoreState(state)

class SimpleSequenceParamSet(SeqParameter):

    sigSequenceChanged = QtCore.Signal(object, object) ## (self, sequence)

    def __init__(self, **args):
        SeqParameter.__init__(self, **args)

        self.evalLocals = units.allUnits.copy()
        exec('from numpy import *', self.evalLocals)  ## import all of numpy into the eval namespace

        ### add a field that displays the calculated sequence values, since we aren't using a plot to confirm output
        self.addChild({'name': 'values', 'type': 'str', 'value': '', 'visible': False, 'readonly':True})
        for k in ['range', 'list']:
            self.visibleParams[k].append('values')

        for name in ['start', 'stop', 'steps', 'log spacing', 'randomize', 'list', 'sequence']:
            self.param(name).sigValueChanged.connect(self.sequenceParameterChanged)

        #self.param('values').sigValueChanged.connect(self.sequenceChanged)

    def sequenceParameterChanged(self, *args):
        #SeqParameter.treeStateChanged(self, param, changes)
        default, seq = self.compile()
        self.param('values').setValue(str(seq))
        self.sequenceChanged(seq)

    def sequenceChanged(self, sequence):
        self.sigSequenceChanged.emit(self, sequence)

    def compile(self):
        name = self.name()
        #default = self.evalStr('default')
        default = self.value()
        mode = self['sequence']
        if mode == 'off':
            seq = []
        elif mode == 'range':
            #start = self.evalStr('start')
            start = self['start']
            #stop = self.evalStr('stop')
            stop = self['stop']
            nPts = self['steps']
            if self['log spacing']:
                seq = fn.logSpace(start, stop, nPts)
            else:
                seq = np.linspace(start, stop, nPts)
        elif mode == 'list':
            seq = list(self.evalStr('list'))
        #elif mode == 'eval':
        #    seq = self.evalStr('expression')
        else:
            raise Exception('Unknown sequence mode %s' % mode)
        
        if self['randomize']:
            np.random.shuffle(seq)
        
        ## sanity check
        try:
            len(seq)
        except:
            raise Exception("Parameter %s generated invalid sequence: %s" % (name, str(seq)))

        self.param('values').setOpts(value=str(seq), blockSignal=True)

        return default, seq

    def evalStr(self, name):
        try:
            #print "evalStr:", name, self[name], type(self[name]), type(self.evalLocals)
            s = eval(self[name], self.evalLocals)
        except:
            print "Error evaluating %s parameter : %s" % (name, self[name])
            #raise SeqEvalError(name, sys.exc_info()[1])
            raise
        return s