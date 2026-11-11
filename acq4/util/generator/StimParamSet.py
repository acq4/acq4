import collections

import pyqtgraph as pg
from pyqtgraph.parametertree.parameterTypes import SimpleParameter, GroupParameter


class StimParamSet(GroupParameter):
    ## top-level parameter in the simple stim generator tree
    def __init__(self):
        GroupParameter.__init__(self, name='Stimuli', type='group',
                           addText='Add Stimulus..', addList=[cls.menuName for cls in STIM_TYPES])
        self.meta = {}

    def addNew(self, typ):
        cls = {c.menuName: c for c in STIM_TYPES}[typ]
        with self.treeChangeBlocker():  ## suppress change signal until all children are built
            self.addChild(cls())

    def addChild(self, ch):
        GroupParameter.addChild(self, ch)
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

    def setState(self, state):
        with self.treeChangeBlocker():
            self.clearChildren()
            types = {c.stimType: c for c in STIM_TYPES}
            for k in state:
                stimType = state[k]['type']
                if stimType not in types:
                    raise ValueError(f"Unknown stimulus type {stimType!r} for {k!r}")
                ch = types[stimType](name=k)
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
            {'name': 'sequence', 'type': 'list', 'value': 'off', 'limits': ['off', 'range (n)', 'range (step)', 'list']},
            {'name': 'start', 'type': 'float', 'axis': axis, 'value': 0, 'visible': False},
            {'name': 'stop', 'type': 'float', 'axis': axis, 'value': 0, 'visible': False},
            {'name': 'steps', 'type': 'int', 'value': 10, 'visible': False},
            {'name': 'step size', 'type': 'float', 'axis': axis, 'value': 10, 'visible': False},
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
            'range (n)': initialParams+['sequence', 'start', 'stop', 'steps', 'log spacing', 'randomize'],
            'range (step)': initialParams+['sequence', 'start', 'stop', 'step size', 'randomize'],
            'list': initialParams+['sequence', 'list', 'randomize'],
        }

    def treeStateChanged(self, param, changes):
        # catch changes to 'sequence' so we can hide/show other params.
        # Note: it would be easier to just catch self.sequence.sigValueChanged,
        # but this approach allows us to block tree change events so they are all
        # released as a single update.
        with self.treeChangeBlocker():
            # queue up change
            SimpleParameter.treeStateChanged(self, param, changes)

            # if needed, add some more changes before releasing the signal
            for param, change, data in changes:
                # if the sequence value changes, hide/show other parameters
                if param is self.param('sequence') and change == 'value':
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
            name = f"{self.parent().varName()}_{self.name()}"
            #seq = "%s = %s; " % (name, self.valueString(self))
            seqData = {
                'default': self.valueString(self),
                'sequence': self['sequence'],
            }
            if self['sequence'] == 'range (n)':
                seqData['start'] = self.valueString(self.param('start'))
                seqData['stop'] = self.valueString(self.param('stop'))
                seqData['steps'] = self['steps']
                seqData['log spacing'] = self['log spacing']
                seqData['randomize'] = self['randomize']
            elif self['sequence'] == 'range (step)':
                seqData['start'] = self.valueString(self.param('start'))
                seqData['stop'] = self.valueString(self.param('stop'))
                seqData['step size'] = self['step size']
                seqData['randomize'] = self['randomize']
                #seq = seq + "%s : %s / %d" % (self.valueString(self.start), self.valueString(self.stop), self['steps'])
            elif self['sequence'] == 'list':
                seqData['list'] = self['list']
                seqData['randomize'] = self['randomize']
                #seq = seq + str(self['list'])
            return name, seqData

    def valueString(self, param):
        units = param.opts.get('units', None)
        if isinstance(units, str) and len(units) > 0:
            val = pg.siFormat(param.value(), suffix=units, space='*', precision=5, allowUnicode=False)
        else:
            val = '%0.5g' % param.value()
        return val

    def setOpts(self, **opts):
        SimpleParameter.setOpts(self, **opts)
        if 'readonly' in opts:  ## if this param is set to readonly, then disable sequencing.
            if opts['readonly'] is False:
                self['sequence'] = 'off'
            self.param('sequence').setOpts(readonly=opts['readonly'], visible=False)

    def setState(self, state):
        self.setValue(state['value'])
        self.setDefault(state['value'])
        for k in state:
            if k == 'value':
                continue
            if k == 'range':
                k = 'range (n)'  # backward compatibility
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


class ExprParameter(SimpleParameter):
    """Non-sequenceable parameter whose string value is inserted verbatim into the
    generated function (e.g. a comma-separated list such as ``0, 10*ms, 20*ms``).
    """
    def __init__(self, **args):
        args.setdefault('type', 'str')
        SimpleParameter.__init__(self, **args)

    def compile(self):
        return self.value(), None

    def setState(self, state):
        self.setValue(state['value'])
        self.setDefault(state['value'])

    def getState(self):
        return collections.OrderedDict(value=self.value())


class StimParameter(GroupParameter):
    """Base for one stimulus component in the simple stim tree.

    Subclasses set ``stimType`` (type string stored in saved state), ``menuName``
    (shown in the "Add Stimulus" menu) and ``defaultName``, and implement
    ``compile()`` returning ``(functionString, sequenceDict)``.
    """
    stimType = None
    menuName = None
    defaultName = None

    def __init__(self, children, **kargs):
        if 'name' not in kargs:
            kargs['name'] = self.defaultName
            kargs['autoIncrementName'] = True
        kargs.setdefault('type', self.stimType)
        kargs['strictNaming'] = True
        GroupParameter.__init__(self, removable=True, renamable=True, children=children, **kargs)

    def varName(self):
        return self.name().replace(' ', '_')

    def compileChildren(self, names):
        """Compile the named children; return ``(valueStrings, sequenceDict)``."""
        vals = []
        seq = {}
        for name in names:
            val, valSeq = self.param(name).compile()
            vals.append(val)
            if valSeq is not None:
                seq[val] = valSeq
        return vals, seq

    def setState(self, state):
        for k, v in state.items():
            if k == 'type':
                continue
            self.param(k).setState(v)

    def getState(self):
        state = collections.OrderedDict()
        for ch in self:
            state[ch.name()] = ch.getState()
        state['type'] = self.opts['type']
        return state


class PulseParameter(StimParameter):
    stimType = 'pulse'
    menuName = 'Pulse'
    defaultName = 'Pulse'

    def __init__(self, **kargs):
        StimParameter.__init__(self, children=[
                SeqParameter(**{'name': 'start', 'type': 'float', 'axis': 'x', 'value': 0.01,}),
                SeqParameter(**{'name': 'length', 'type': 'float', 'axis': 'x', 'value': 0.01}),
                SeqParameter(**{'name': 'amplitude', 'type': 'float', 'axis': 'y', 'value': 0}),
                SeqParameter(**{'name': 'sum', 'type': 'float', 'axis': 'xy', 'value': 0, 'limits': (0, None),
                    'children': [{'name': 'affect', 'type': 'list', 'limits': ['length', 'amplitude'], 'value': 'length'}]
                    }),
            ], **kargs)
        self.param('length').sigValueChanged.connect(self.lenChanged)
        self.param('amplitude').sigValueChanged.connect(self.ampChanged)
        self.param('sum').sigValueChanged.connect(self.sumChanged)

    def lenChanged(self):
        self.param('sum').setValue(abs(self['length']) * self['amplitude'], blockSignal=self.sumChanged)

    def ampChanged(self):
        self.param('sum').setValue(abs(self['length']) * self['amplitude'], blockSignal=self.sumChanged)

    def sumChanged(self):
        if self['sum', 'affect'] == 'length':
            sign = 1 if self['length'] >= 0 else -1
            if self['amplitude'] == 0:
                self.param('length').setValue(0, blockSignal=self.lenChanged)
            else:
                self.param('length').setValue(sign * self['sum'] / self['amplitude'], blockSignal=self.lenChanged)
        else:
            sign = 1 if self['amplitude'] >= 0 else -1
            if self['length'] == 0:
                self.param('amplitude').setValue(0, blockSignal=self.ampChanged)
            else:
                self.param('amplitude').setValue(sign * self['sum'] / self['length'], blockSignal=self.ampChanged)

    def preCompile(self):
        # prepare data for compile
        seqParams = [self.param('start').compile(), self.param('length').compile(), self.param('amplitude').compile()]
        (start, startSeq) = seqParams[0]
        (length, lenSeq) = seqParams[1]
        (amp, ampSeq) = seqParams[2]
        seq = {name: seq for name, seq in seqParams if seq is not None}

        # If sequence is specified over sum, interpret that a bit differently.
        (sumName, sumSeq) = self.param('sum').compile()
        if sumSeq is not None:
            if self['sum', 'affect'] == 'length':
                if not self.param('length').writable():
                    raise ValueError(f"{self.name()}: Can not sequence over length; it is a read-only parameter.")
                if lenSeq is not None:
                    raise ValueError(f"{self.name()}: Can not sequence over length and sum simultaneously.")
                length = "%s / (%s)" % (sumName, amp)
            else:
                if not self.param('amplitude').writable():
                    raise ValueError(f"{self.name()}: Can not sequence over amplitude; it is a read-only parameter.")
                if ampSeq is not None:
                    raise ValueError(f"{self.name()}: Can not sequence over amplitude and sum simultaneously.")
                amp = f"{sumName} / ({length})"
            seq[sumName] = sumSeq

        return start, length, amp, seq

    def compile(self):
        start, length, amp, seq = self.preCompile()
        fnStr = "pulse(%s, %s, %s)" % (start, length, amp)
        return fnStr, seq


class PulseTrainParameter(PulseParameter):
    stimType = 'pulseTrain'
    menuName = 'Pulse Train'
    defaultName = 'PulseTrain'

    def __init__(self, **kargs):
        PulseParameter.__init__(self, **kargs)

        params = [
            SeqParameter(**{'name': 'period', 'type': 'float', 'value': 0.01, 'axis': 'x'}),
            SeqParameter(**{'name': 'pulse_number', 'type': 'int', 'value': 10}),
        ]
        for p in params:
            self.addChild(p)

    def preCompile(self):
        start, length, amp, seq = PulseParameter.preCompile(self)

        seqParams = [self.param('period').compile(), self.param('pulse_number').compile()]
        (interval, intSeq) = seqParams[0]
        (number, numSeq) = seqParams[1]
        seq.update({name:seq for name, seq in seqParams if seq is not None})

        start = "%s + np.linspace(0, %s * (%s-1), %s)" % (start, interval, number, number)
        return start, length, amp, seq

    def compile(self):
        start, length, amp, seq = self.preCompile()
        fnStr = "pulse(\n  times=%s,\n  widths=%s,\n  values=%s\n)" % (start, length, amp)
        return fnStr, seq

    def setState(self, state):
        # for backward compatibility
        if 'interpulse_length' in state:
            state['period'] = state['interpulse_length']
            del state['interpulse_length']
        return PulseParameter.setState(self, state)


def _windowParams():
    return [
        SeqParameter(name='start', type='float', axis='x', value=0.01),
        SeqParameter(name='duration', type='float', axis='x', value=0.1, limits=(0, None)),
    ]


class PeriodicWaveParameter(StimParameter):
    """Base for periodic waveforms generated by ``funcName(period, amplitude, phase, ...)``
    over [start, start+duration]. Phase is in cycles.
    """
    funcName = None
    extraParams = []  # (name, SeqParameter kwargs) appended after phase

    def __init__(self, **kargs):
        children = _windowParams() + [
            SeqParameter(name='period', type='float', axis='x', value=0.01, limits=(0, None)),
            SeqParameter(name='amplitude', type='float', axis='y', value=0),
            SeqParameter(name='phase', type='float', value=0, tip='Phase offset in cycles'),
        ] + [SeqParameter(name=name, **opts) for name, opts in self.extraParams]
        StimParameter.__init__(self, children=children, **kargs)

    def compile(self):
        names = ['start', 'duration', 'period', 'amplitude', 'phase'] + [n for n, _ in self.extraParams]
        vals, seq = self.compileChildren(names)
        a = dict(zip(names, vals))
        extra = ''.join(f",\n  {n}={a[n]}" for n, _ in self.extraParams)
        fnStr = (f"{self.funcName}(\n  period={a['period']},\n  amplitude={a['amplitude']},\n"
                 f"  phase={a['phase']}{extra},\n  start={a['start']},\n"
                 f"  stop=({a['start']}) + ({a['duration']})\n)")
        return fnStr, seq


class SineWaveParameter(PeriodicWaveParameter):
    stimType = 'sineWave'
    menuName = 'Sine Wave'
    defaultName = 'Sine'
    funcName = 'sineWave'


class SquareWaveParameter(PeriodicWaveParameter):
    stimType = 'squareWave'
    menuName = 'Square Wave'
    defaultName = 'Square'
    funcName = 'squareWave'
    extraParams = [('duty', {'type': 'float', 'value': 0.5, 'limits': (0, 1)})]


class SawWaveParameter(PeriodicWaveParameter):
    stimType = 'sawWave'
    menuName = 'Saw Wave'
    defaultName = 'Saw'
    funcName = 'sawWave'


class ListWaveParameter(StimParameter):
    """Steps through a list of values, each held for period/len(values), repeating every period."""
    stimType = 'listWave'
    menuName = 'List Wave'
    defaultName = 'ListWave'

    def __init__(self, **kargs):
        children = _windowParams() + [
            SeqParameter(name='period', type='float', axis='x', value=0.01, limits=(0, None)),
            ExprParameter(name='values', value='0, 1', tip='Comma-separated values; unit names allowed'),
            SeqParameter(name='phase', type='float', value=0, tip='Phase offset in cycles'),
        ]
        StimParameter.__init__(self, children=children, **kargs)

    def compile(self):
        (start, duration, period, values, phase), seq = self.compileChildren(
            ['start', 'duration', 'period', 'values', 'phase'])
        fnStr = (f"listWave(\n  period={period},\n  values=[{values}],\n  phase={phase},\n"
                 f"  start={start},\n  stop=({start}) + ({duration})\n)")
        return fnStr, seq


class StepsParameter(StimParameter):
    """Holds values[i] from times[i] until times[i+1]; the last value holds to the end."""
    stimType = 'steps'
    menuName = 'Steps'
    defaultName = 'Steps'

    def __init__(self, **kargs):
        children = [
            ExprParameter(name='times', value='0.01, 0.05', tip='Comma-separated step times; unit names allowed'),
            ExprParameter(name='values', value='0, 0', tip='Comma-separated values, one per time'),
        ]
        StimParameter.__init__(self, children=children, **kargs)

    def compile(self):
        (times, values), seq = self.compileChildren(['times', 'values'])
        return f"steps(\n  times=[{times}],\n  values=[{values}]\n)", seq


class NoiseParameter(StimParameter):
    """Gaussian noise over [start, start+duration]."""
    stimType = 'noise'
    menuName = 'Noise'
    defaultName = 'Noise'

    def __init__(self, **kargs):
        children = _windowParams() + [
            SeqParameter(name='mean', type='float', axis='y', value=0),
            SeqParameter(name='sigma', type='float', axis='y', value=0, limits=(0, None)),
        ]
        StimParameter.__init__(self, children=children, **kargs)

    def compile(self):
        (start, duration, mean, sigma), seq = self.compileChildren(['start', 'duration', 'mean', 'sigma'])
        fnStr = (f"noise(\n  mean={mean},\n  sigma={sigma},\n  start={start},\n"
                 f"  stop=({start}) + ({duration})\n)")
        return fnStr, seq


## Stimulus classes offered in the "Add Stimulus" menu, in menu order.
STIM_TYPES = [
    PulseParameter,
    PulseTrainParameter,
    SineWaveParameter,
    SquareWaveParameter,
    SawWaveParameter,
    ListWaveParameter,
    StepsParameter,
    NoiseParameter,
]
