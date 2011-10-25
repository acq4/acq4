from pyqtgraph.parametertree.parameterTypes import SimpleParameter, GroupParameter
import pyqtgraph as pg
import collections

class StimParamSet(GroupParameter):
    ## top-level parameter in the simple stim generator tree
    def __init__(self):
        GroupParameter.__init__(self, name='Stimuli', type='group',
                           addText='Add Stimulus..', addList=['Pulse', 'Pulse Train'])
        self.meta = {}
        
    def addNew(self, type):
        with self.treeChangeBlocker():  ## about to make lots of tree changes;
                                        ## suppress change signal until we're done.
            if type == 'Pulse':
                ch = self.addChild(PulseParameter())
            elif type == 'Pulse Train':
                ch = self.addChild(PulseTrainParameter())
            else:
                raise Exception('Unknown type %s' % type)
            
            for ax in self.meta:
                self.setMeta(ax, self.meta[ax], ch)

    def setMeta(self, axis, opts=None, root=None, **kargs):  ## set units, limits, etc.
        ## Set meta-properties (units, limits, readonly, etc.) for specific sets of values
        ## axis should be 'x', 'y', or 'xy'
        if opts is None:
            opts = {}
        opts.update(kargs)
        if root is None:
            root = self
            self.meta[axis] = opts
        for ch in root:
            if ch.opts.get('axis', None) == axis:   ## set options on any parameter that matches axis
                ch.setOpts(**opts)
            self.setMeta(axis, opts, root=ch)
            
    def compile(self):
        fns = []
        params = {}
        for ch in self:
            fn, par = ch.compile()
            fns.append(fn)
            params.update(par)
        return ' + \n'.join(fns), params

    #def treeStateChanged(self, param, changes):
        #GroupParameter.treeStateChanged(self, param, changes)
        #print "\n\nStimParamSet got tree state changes:"
        #for ch in changes:
            #print ch

    def setState(self, state):
        with self.treeChangeBlocker():
            self.clearChildren()
            for k in state:
                if state[k]['type'] == 'pulse':
                    ch = PulseParameter(name=k)
                elif state[k]['type'] == 'pulseTrain':
                    ch = PulseTrainParameter(name=k)
                self.addChild(ch)
                ch.setState(state[k])
        
    def getState(self):
        state = collections.OrderedDict()
        for ch in self:
            state[ch.name()] = ch.getState()
        return state


class SeqParameter(SimpleParameter):
    def __init__(self, **args):
        axis = args.get('axis', None)
        args['expanded'] = args.get('expanded', False)
        SimpleParameter.__init__(self, **args)
        initialParams = [ch.name() for ch in self]
        
        newParams = [
            {'name': 'sequence', 'type': 'list', 'value': 'off', 'values': ['off', 'range', 'list']},
            {'name': 'start', 'type': 'float', 'axis': axis, 'value': 0, 'visible': False}, 
            {'name': 'stop', 'type': 'float', 'axis': axis, 'value': 0, 'visible': False}, 
            {'name': 'steps', 'type': 'int', 'value': 10, 'visible': False},
            {'name': 'log spacing', 'type': 'bool', 'value': False, 'visible': False}, 
            {'name': 'list', 'type': 'str', 'value': '', 'visible': False}, 
            {'name': 'randomize', 'type': 'bool', 'value': False, 'visible': False}, 
        ]
        for ch in newParams:
            self.addChild(ch)
        #print "Built sequence param:", id(self), args['name'], args['type']
        #self.sequence.sigTreeStateChanged.connect(self.seqChanged)
        
        self.visibleParams = {  ## list of params to display in each mode
            'off': initialParams+['sequence'],
            'range': initialParams+['sequence', 'start', 'stop', 'steps', 'log spacing', 'randomize'],
            'list': initialParams+['sequence', 'list', 'randomize'],
        }
        
        
    def treeStateChanged(self, param, changes):
        ## catch changes to 'sequence' so we can hide/show other params.
        ## Note: it would be easier to just catch self.sequence.sigValueChanged,
        ## but this approach allows us to block tree change events so they are all
        ## released as a single update.
        with self.treeChangeBlocker():
            ## queue up change 
            SimpleParameter.treeStateChanged(self, param, changes)
            
            ## if needed, add some more changes before releasing the signal
            for param, change, data in changes:
                ## if the sequence value changes, hide/show other parameters
                if param is self.sequence and change == 'value':
                    vis = self.visibleParams[self['sequence']]
                    for ch in self:
                        if ch.name() in vis:
                            ch.show()
                        else:
                            ch.hide()

    def compile(self):
        if self['sequence'] == 'off':
            return self.valueString(self), None
        else:
            name = "%s_%s" % (self.parent().varName(), self.name())
            #seq = "%s = %s; " % (name, self.valueString(self))
            seqData = {
                'default': self.valueString(self),
                'sequence': self['sequence'],
            }
            if self['sequence'] == 'range':
                seqData['start'] = self.valueString(self.start)
                seqData['stop'] = self.valueString(self.stop)
                seqData['steps'] = self['steps']
                seqData['log spacing'] = self['log spacing']
                seqData['randomize'] = self['randomize']
                #seq = seq + "%s : %s / %d" % (self.valueString(self.start), self.valueString(self.stop), self['steps'])
            elif self['sequence'] == 'list':
                seqData['list'] = self['list']
                #seq = seq + str(self['list'])
            return name, seqData
        
    def valueString(self, param):
        if 'units' in param.opts:
            val = pg.siFormat(param.value(), suffix=param.opts['units'], space='*', precision=5, allowUnicode=False)
        else:
            val = '%0.5g' % param.value()
        return val
    
    def setOpts(self, **opts):
        SimpleParameter.setOpts(self, **opts)
        if 'readonly' in opts:  ## if this param is set to readonly, then disable sequencing.
            if opts['readonly'] is False:
                self['sequence'] = 'off'
            self.sequence.setOpts(readonly=opts['readonly'])
    
    def setState(self, state):
        self.setValue(state['value'])
        self.setDefault(state['value'])
        for k in state:
            if k == 'value':
                continue
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
        state['value'] = self.value()
        return state


class PulseParameter(GroupParameter):
    def __init__(self, **kargs):
        if 'name' not in kargs:
            kargs['name'] = 'Pulse'
            kargs['autoIncrementName'] = True
        GroupParameter.__init__(self, type="pulse", removable=True, renamable=True,
            params=[
                SeqParameter(**{'name': 'start', 'type': 'float', 'axis': 'x', 'value': 0.01, 'suffix': 's', 'siPrefix': True, 'minStep': 1e-6, 'dec': True}),
                SeqParameter(**{'name': 'length', 'type': 'float', 'axis': 'x', 'value': 0.01, 'suffix': 's', 'siPrefix': True, 'minStep': 1e-6, 'dec': True}),
                SeqParameter(**{'name': 'amplitude', 'type': 'float', 'axis': 'y', 'value': 0}),
                SeqParameter(**{'name': 'sum', 'type': 'float', 'axis': 'xy', 'value': 0, 'limits': (0, None),
                    'params': [{'name': 'affect', 'type': 'list', 'values': ['length', 'amplitude'], 'value': 'length'}]
                    }),
            ], **kargs)
        self.length.sigValueChanged.connect(self.lenChanged)
        self.amplitude.sigValueChanged.connect(self.ampChanged)
        self.sum.sigValueChanged.connect(self.sumChanged)
        
    def lenChanged(self):
        self.sum.setValue(abs(self['length']) * self['amplitude'], blockSignal=self.sumChanged)

    def ampChanged(self):
        self.sum.setValue(abs(self['length']) * self['amplitude'], blockSignal=self.sumChanged)

    def sumChanged(self):
        if self['sum', 'affect'] == 'length':
            sign = 1 if self['length'] >= 0 else -1
            self.length.setValue(sign * self['sum'] / self['amplitude'], blockSignal=self.lenChanged)
        else:
            sign = 1 if self['amplitude'] >= 0 else -1
            self.amplitude.setValue(sign * self['sum'] / self['length'], blockSignal=self.ampChanged)

    def varName(self):
        name = self.name()
        name.replace(' ', '_')
        return name

    def compile(self):
        seqParams = [self.start.compile(), self.length.compile(), self.amplitude.compile()] 
        (start, startSeq) = seqParams[0]
        (length, lenSeq) = seqParams[1]
        (amp, ampSeq) = seqParams[2]
        seq = {name:seq for name, seq in seqParams if seq is not None}
        
        ## If sequence is specified over sum, interpret that a bit differently.
        (sumName, sumSeq) = self.sum.compile()
        if sumSeq is not None:
            if self.sum['affect'] == 'length':
                if lenSeq is not None:
                    raise Exception("%s: Can not sequence over length and sum simultaneously." % self.name())
                length = "%s / (%s)" % (sumName, amp)
            else:
                if ampSeq is not None:
                    raise Exception("%s: Can not sequence over amplitude and sum simultaneously." % self.name())
                amp = "%s / (%s)" % (sumName, length)
            seq[sumName] = sumSeq
        
        fnStr = "pulse(%s, %s, %s)" % (start, length, amp)
        return fnStr, seq
        
    def setState(self, state):
        for k, v in state.iteritems():
            if k == 'type':
                continue
            self.param(k).setState(v)
        
    def getState(self):
        state = collections.OrderedDict()
        for ch in self:
            state[ch.name()] = ch.getState()
        state['type'] = self.opts['type']
        return state
        

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
        
        
