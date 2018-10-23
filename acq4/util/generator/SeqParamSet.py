from __future__ import print_function
import acq4.util.units as units
from acq4.pyqtgraph.parametertree.parameterTypes import SimpleParameter, GroupParameter
import acq4.pyqtgraph as pg
import numpy as np
import acq4.util.functions as fn
import sys, collections


class SequenceParamSet(GroupParameter):
    ## top-level parameter in the simple stim generator tree
    def __init__(self):
        GroupParameter.__init__(self, name='SequenceParams', type='group',
                           addText='Add Sequence Parameter')
        self.meta = {}
        
    def addNew(self):
        with self.treeChangeBlocker():  ## about to make lots of tree changes;
                                        ## suppress change signal until we're done.
            ch = self.addChild(SeqParameter())
                                        
                                        
            #if type == 'Pulse':
                #ch = self.addChild(PulseParameter())
            #elif type == 'Pulse Train':
                #ch = self.addChild(PulseTrainParameter())
            #else:
                #raise Exception('Unknown type %s' % type)
            
            #for ax in self.meta:
                #self.setMeta(ax, self.meta[ax], ch)

    def compile(self):
        params = collections.OrderedDict()
        for ch in self:
            try:
                params[ch.name()] = ch.compile()
            except SeqEvalError as ex:
                #print sys.exc_info()
                raise Exception("'%s.%s': %s" % (ch.name(), ex.name, ex.exc))
            except:
                raise Exception("'%s': %s" % (ch.name(), str(sys.exc_info()[1])))
            
        return params
    
    def setState(self, state):
        with self.treeChangeBlocker():
            self.clearChildren()
            for k in state:
                ch = self.addChild(SeqParameter())
                ch.setName(k)
                ch.setState(state[k])
        
    def getState(self):
        state = collections.OrderedDict()
        for ch in self:
            state[ch.name()] = ch.getState()
        return state
        

class SeqEvalError(Exception):  ## raised when a sequence parameter field fails to evaluate
    def __init__(self, name, exc):
        Exception.__init__(self)
        self.name = name
        self.exc = str(exc)

class SeqParameter(GroupParameter):
    def __init__(self, **args):
        
        self.evalLocals = units.allUnits.copy()
        exec('from numpy import *', self.evalLocals)  ## import all of numpy into the eval namespace
        
        args['renamable'] = True
        args['removable'] = True
        args['name'] = args.get('name', 'Param')
        args['autoIncrementName'] = True
        args['strictNaming'] = True
        
        args['children'] = [
            {'name': 'default', 'type': 'str', 'value': '0'},
            {'name': 'sequence', 'type': 'list', 'value': 'off', 'values': ['off', 'range', 'list', 'eval']},
            {'name': 'start', 'type': 'str', 'value': '0', 'visible': False}, 
            {'name': 'stop', 'type': 'str', 'value': '0', 'visible': False}, 
            {'name': 'steps', 'type': 'int', 'value': 10, 'visible': False},
            {'name': 'log spacing', 'type': 'bool', 'value': False, 'visible': False}, 
            {'name': 'list', 'type': 'str', 'value': '', 'visible': False}, 
            {'name': 'randomize', 'type': 'bool', 'value': False, 'visible': False}, 
            {'name': 'expression', 'type': 'str', 'visible': False},
        ]
        
        GroupParameter.__init__(self, **args)
        #self.sequence.sigValueChanged.connect(self.seqChanged)
        
        self.visibleParams = {  ## list of params to display in each mode
            'off': ['default', 'sequence'],
            'range': ['default', 'sequence', 'start', 'stop', 'steps', 'log spacing', 'randomize'],
            'list': ['default', 'sequence', 'list', 'randomize'],
            'eval': ['default', 'sequence', 'expression']
        }
        
        
    def treeStateChanged(self, param, changes):
        ## catch changes to 'sequence' so we can hide/show other params.
        ## Note: it would be easier to just catch self.sequence.sigValueChanged,
        ## but this approach allows us to block tree change events so they are all
        ## released as a single update.
        with self.treeChangeBlocker():
            ## queue up change 
            GroupParameter.treeStateChanged(self, param, changes)
            
            ## if needed, add some more changes before releasing the signal
            for param, change, data in changes:
                ## if the sequence value changes, hide/show other parameters
                if param is self.param('sequence') and change == 'value':
                    vis = self.visibleParams[self['sequence']]
                    for ch in self:
                        if ch.name() in vis:
                            ch.show()
                        else:
                            ch.hide()
    #def seqChanged(self):
        #with self.treeChangeBlocker():
            #vis = self.visibleParams[self['sequence']]
            #for ch in self:
                #if ch.name() in vis:
                    #ch.show()
                #else:
                    #ch.hide()
        
    def compile(self):
        name = self.name()
        default = self.evalStr('default')
        mode = self['sequence']
        if mode == 'off':
            seq = []
        elif mode == 'range':
            start = self.evalStr('start')
            stop = self.evalStr('stop')
            nPts = self['steps']
            if self['log spacing']:
                seq = fn.logSpace(start, stop, nPts)
            else:
                seq = np.linspace(start, stop, nPts)
        elif mode == 'list':
            seq = list(self.evalStr('list'))
        elif mode == 'eval':
            seq = self.evalStr('expression')
        else:
            raise Exception('Unknown sequence mode %s' % mode)
        
        if self['randomize']:
            np.random.shuffle(seq)
        
        ## sanity check
        try:
            len(seq)
        except:
            raise Exception("Parameter %s generated invalid sequence: %s" % (name, str(seq)))
        
        return default, seq

    def evalStr(self, name):
        try:
            s = eval(self[name], self.evalLocals)
        except:
            raise SeqEvalError(name, sys.exc_info()[1])
        return s
        
    def setState(self, state):
        for k in state:
            self[k] = state[k]
            self.param(k).setDefault(state[k])
        
    def getState(self):
        state = collections.OrderedDict()
        for ch in self:
            if not ch.opts['visible']:
                continue
            name = ch.name()
            val = ch.value()
            if val is False:
                continue
            state[name] = val
        return state





