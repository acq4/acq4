"""Simple-mode stimulus tree for StimGenerator, built on neuroanalysis.stimuli."""
import collections
import numbers
import re
import textwrap

import numpy as np
import pyqtgraph as pg
import pyqtgraph.units as pgunits
from pyqtgraph.parametertree.parameterTypes import SimpleParameter, GroupParameter, ListParameter

from neuroanalysis import stimuli

# version of the saved simple-mode 'stimuli' state; unversioned states are legacy pulse/pulseTrain dicts
STATE_FORMAT = 2

ALL_AXES = ('x', 'y', 'xy')

# SeqParameter children that describe a sequence
SEQ_KEYS = ('sequence', 'start', 'stop', 'steps', 'step size', 'log spacing', 'list', 'randomize')


def formatValue(value, units=None):
    """Return an expression string that evaluates exactly to *value*, with pyqtgraph units in scope.

    Floats use an SI-prefixed *units* suffix (e.g. ``10*ms``) when one round-trips exactly.
    """
    if isinstance(value, (bool, np.bool_)):
        return repr(bool(value))
    if isinstance(value, numbers.Integral):
        return str(int(value))
    if isinstance(value, str):
        return repr(value)
    value = float(value)
    if units and np.isfinite(value):
        for precision in range(5, 18):
            s = pg.siFormat(value, suffix=units, space='*', precision=precision, allowUnicode=False)
            try:
                if eval(s, {'__builtins__': {}}, pgunits.allUnits) == value:
                    return s
            except (NameError, SyntaxError):
                break  # units not expressible in the units namespace
    return repr(value)


def _mergeSeq(seq, new):
    for name, data in new.items():
        if name in seq:
            raise ValueError(f"Duplicate sequence parameter name {name!r}")
        seq[name] = data


def _stimState(cls, description, args, inputs=None, items=()):
    """Return the unversioned ``Stimulus.save()`` state of ``cls(description=description, **args)``."""
    state = {'type': cls.__name__, 'args': {'start_time': args.get('start_time', 0)}}
    for name in cls._attributes:
        if name == 'description':
            state['args'][name] = description
        elif name == 'units':
            state['args'][name] = None
        else:
            state['args'][name] = args.get(name, 0) if name == 'start_time' else args[name]
    state['items'] = list(items)
    if cls._inputs:
        state['inputs'] = dict(inputs or {})
    return state


def _safeName(name):
    name = re.sub(r'\W', '_', str(name)) or 'stim'
    return '_' + name if name[0].isdigit() else name


class SeqParameter(SimpleParameter):
    """A numeric parameter that may be sequenced over a range or list of values."""
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

    def seqName(self):
        """Name of this parameter's sequence variable."""
        parent = self.parent()
        if hasattr(parent, 'seqVarName'):
            return parent.seqVarName(self.name())
        return f"{parent.varName()}_{self.name()}"

    def compile(self):
        """Return ``(valueString, None)`` if not sequenced, else ``(seqName, seqData)``."""
        if self['sequence'] == 'off':
            return self.valueString(self), None
        else:
            name = self.seqName()
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
            elif self['sequence'] == 'list':
                seqData['list'] = self['list']
                seqData['randomize'] = self['randomize']
            return name, seqData

    def evalValue(self, ns):
        """Return this parameter's value at the sequence point *ns* ({seqName: value}).

        Unsequenced, or absent from *ns*: the parameter's own value. Int parameters are rounded.
        """
        v = self.value()
        if self['sequence'] != 'off':
            v = ns.get(self.seqName(), v)
        return int(round(float(v))) if self.opts['type'] == 'int' else float(v)

    def valueString(self, param):
        if param.opts['type'] == 'int':
            return str(int(param.value()))
        units = param.opts.get('units') or param.opts.get('suffix')
        return formatValue(param.value(), units if isinstance(units, str) else None)

    def setOpts(self, **opts):
        SimpleParameter.setOpts(self, **opts)
        if 'readonly' in opts:  ## if this param is set to readonly, then disable sequencing.
            if opts['readonly'] is False:
                self['sequence'] = 'off'
            self.param('sequence').setOpts(readonly=opts['readonly'], visible=False)

    def setState(self, state):
        self.setValue(state['value'])
        self.setDefault(state['value'])
        self.setSeqState({k: v for k, v in state.items() if k != 'value'})

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

    def getSeqState(self):
        """Return the sequence spec ({'sequence': mode, ...}) without the value."""
        mode = self['sequence']
        state = {'sequence': mode}
        for k in self.visibleParams[mode]:
            if k in SEQ_KEYS:
                state[k] = self[k]
        return state

    def setSeqState(self, state):
        """Set child values (sequence spec and helpers such as 'affect') from *state*."""
        for k, v in state.items():
            if k == 'sequence' and v == 'range':
                v = 'range (n)'  # legacy name
            self[k] = v
            self.param(k).setDefault(v)


class InputParameter(GroupParameter):
    """Container for a named input of a stimulus; its items are summed into one Stimulus.

    Only meta for the axes in *axes* propagates into it.
    """
    def __init__(self, name, axes=ALL_AXES):
        self.axes = tuple(axes)
        GroupParameter.__init__(self, name=name, type='group', addText='Add input..',
                                addList=[cls.menuName for cls in STIM_TYPES])

    def addNew(self, typ):
        with self.treeChangeBlocker():
            child = self.addChild(STIM_TYPES_BY_MENU[typ]())
            child['start_time'] = 0  # relative to the host's start

    def addChild(self, child, *args, **kwargs):
        child = GroupParameter.addChild(self, child, *args, **kwargs)
        root = _stimRoot(self)
        if root is not None:
            root.applyMeta(child)
        return child

    def buildStimulus(self, ns):
        return stimuli.Stimulus(description=self.name(), items=[ch.buildStimulus(ns) for ch in self])

    def compile(self):
        exprs, seq = [], {}
        for ch in self:
            e, s = ch.compile()
            exprs.append(e)
            _mergeSeq(seq, s)
        if not exprs:
            return 'Stimulus()', seq
        body = textwrap.indent(',\n'.join(exprs), '  ')
        return f"Stimulus(items=[\n{body},\n])", seq

    def stimulusState(self):
        return _stimState(stimuli.Stimulus, self.name(), {}, items=[ch.stimulusState() for ch in self])

    def setStimulusState(self, state):
        """Replace this input's items from a saved Stimulus state (a plain Stimulus of items, or a single stimulus)."""
        if state['type'] == 'Stimulus':
            if state.get('args', {}).get('start_time', 0) != 0:
                raise ValueError(f"Input {self.name()!r}: container start_time must be 0")
            itemStates = state.get('items', [])
        else:
            itemStates = [state]
        with self.treeChangeBlocker():
            self.clearChildren()
            for itemState in itemStates:
                cls = stimParamClass(itemState['type'])
                desc = itemState.get('args', {}).get('description', cls.defaultName)
                ch = self.addChild(cls(name=_safeName(desc), autoIncrementName=True))
                ch.setStimulusState(itemState)


def _stimRoot(param):
    while param is not None and not isinstance(param, StimParamSet):
        param = param.parent()
    return param


def _axisAllowed(param, axis):
    while param is not None and not isinstance(param, StimParamSet):
        if isinstance(param, InputParameter) and axis not in param.axes:
            return False
        param = param.parent()
    return True


class StimParameter(GroupParameter):
    """One neuroanalysis stimulus in the simple stim tree.

    Subclasses set ``stimClass``, ``menuName``, ``defaultName`` and ``paramSpecs``: child parameter
    options named after ``stimClass`` constructor arguments (``type='list'`` gives a fixed choice,
    anything else a SeqParameter). Each name in ``stimClass._inputs`` gets an InputParameter child,
    receiving meta for ``inputAxes[name]`` (default all axes).
    """
    stimClass = None
    menuName = None
    defaultName = None
    paramSpecs = []
    inputAxes = {}

    def __init__(self, name=None, **kargs):
        if name is None:
            name = self.defaultName
            kargs['autoIncrementName'] = True
        children = [self._makeParam(spec) for spec in self.paramSpecs]
        children += [InputParameter(n, axes=self.inputAxes.get(n, ALL_AXES)) for n in self.stimClass._inputs]
        kargs.setdefault('type', self.stimClass.__name__)
        GroupParameter.__init__(self, name=name, removable=True, renamable=True, strictNaming=True,
                                children=children, **kargs)

    @staticmethod
    def _makeParam(spec):
        if spec.get('type') == 'list':
            return ListParameter(**spec)
        return SeqParameter(**spec)

    def varName(self):
        return self.name().replace(' ', '_')

    def seqVarName(self, attr):
        """Sequence variable name for *attr*: ``<item>_<attr>``, prefixed by ``<owner>_<input>_`` when nested."""
        parent = self.parent()
        if isinstance(parent, InputParameter):
            return f"{parent.parent().seqVarName(parent.name())}_{self.varName()}_{attr}"
        return f"{self.varName()}_{attr}"

    def inputParams(self):
        return [self.param(n) for n in self.stimClass._inputs]

    def iterSeqParams(self, prefix=()):
        """Yield ``(path, SeqParameter)`` for this item and its nested inputs; path is relative to this item."""
        for ch in self:
            if isinstance(ch, SeqParameter):
                yield prefix + (ch.name(),), ch
            elif isinstance(ch, InputParameter):
                for item in ch:
                    yield from item.iterSeqParams(prefix + (ch.name(), item.name()))

    def argValues(self, ns):
        """Return {attr: value} for this item's own parameters at sequence point *ns*."""
        vals = {}
        for spec in self.paramSpecs:
            p = self.param(spec['name'])
            vals[spec['name']] = p.evalValue(ns) if isinstance(p, SeqParameter) else p.value()
        return vals

    def argExprs(self):
        """Return ``({attr: expression}, {seqName: seqData})`` for this item's own parameters."""
        exprs, seq = {}, {}
        for spec in self.paramSpecs:
            p = self.param(spec['name'])
            if isinstance(p, SeqParameter):
                s, seqData = p.compile()
                if seqData is not None:
                    seq[s] = seqData
                    if p.opts['type'] == 'int':
                        s = f"round({s})"
            else:
                s = repr(p.value())
            exprs[spec['name']] = s
        return exprs, seq

    def buildStimulus(self, ns):
        """Return this item's Stimulus at sequence point *ns* ({seqName: value}).

        Sequenced parameters read *ns*, falling back to their own value.
        """
        kwargs = self.argValues(ns)
        for inp in self.inputParams():
            kwargs[inp.name()] = inp.buildStimulus(ns)
        return self.stimClass(description=self.name(), **kwargs)

    def compile(self):
        """Return ``(expression, {seqName: seqData})``; the expression builds this item's Stimulus."""
        exprs, seq = self.argExprs()
        args = ', '.join(f"{k}={v}" for k, v in exprs.items())
        cls = self.stimClass.__name__
        inputs = self.inputParams()
        if not inputs:
            return f"{cls}({args})", seq
        parts = [args]
        for inp in inputs:
            e, s = inp.compile()
            _mergeSeq(seq, s)
            parts.append(f"{inp.name()}={e}")
        body = textwrap.indent(',\n'.join(parts), '  ')
        return f"{cls}(\n{body},\n)", seq

    def stimulusState(self):
        """Return the unversioned ``save()`` state of this item's default (unsequenced) Stimulus.

        Built without instantiating, so it works for parameters the Stimulus would reject.
        """
        inputs = {inp.name(): inp.stimulusState() for inp in self.inputParams()}
        return _stimState(self.stimClass, self.name(), self.argValues({}), inputs)

    def setStimulusState(self, state):
        """Set parameter values and inputs from a saved Stimulus state."""
        if state['type'] != self.stimClass.__name__:
            raise ValueError(f"{self.name()}: expected {self.stimClass.__name__} state, got {state['type']!r}")
        if state.get('items'):
            raise ValueError(f"{self.name()}: child items are not supported")
        args = state.get('args', {})
        for spec in self.paramSpecs:
            if spec['name'] in args:
                p = self.param(spec['name'])
                p.setValue(args[spec['name']])
                p.setDefault(args[spec['name']])
        inputs = state.get('inputs', {})
        for inp in self.inputParams():
            if inp.name() in inputs:
                inp.setStimulusState(inputs[inp.name()])

    def sequenceState(self):
        """Return {dotted path: sequence spec} for every sequenced parameter, including nested ones."""
        return {'.'.join(path): p.getSeqState() for path, p in self.iterSeqParams() if p['sequence'] != 'off'}

    def setSequenceState(self, sequences):
        for path, spec in sequences.items():
            parts = path.split('.')
            item = self
            while len(parts) > 1:
                item = item.param(parts[0], parts[1])
                parts = parts[2:]
            item.param(parts[0]).setSeqState(spec)

    def uiState(self):
        """Return acq4-only parameter values (not part of the Stimulus)."""
        return {}

    def setUiState(self, state):
        pass


class PulseParameter(StimParameter):
    """SquarePulse, with a 'sum' (duration * amplitude) helper that may be sequenced instead of its *affect* target."""
    stimClass = stimuli.SquarePulse
    menuName = 'Pulse'
    defaultName = 'Pulse'
    durationAttr = 'duration'
    paramSpecs = [
        dict(name='start_time', type='float', axis='x', value=0.01),
        dict(name='duration', type='float', axis='x', value=0.01),
        dict(name='amplitude', type='float', axis='y', value=0),
    ]

    def __init__(self, name=None, **kargs):
        StimParameter.__init__(self, name, **kargs)
        dur = self.durationAttr
        self.addChild(SeqParameter(
            name='sum', type='float', axis='xy', value=0, limits=(0, None),
            children=[{'name': 'affect', 'type': 'list', 'limits': [dur, 'amplitude'], 'value': dur}]))
        self.param(dur).sigValueChanged.connect(self.lenChanged)
        self.param('amplitude').sigValueChanged.connect(self.ampChanged)
        self.param('sum').sigValueChanged.connect(self.sumChanged)

    def lenChanged(self):
        self.param('sum').setValue(abs(self[self.durationAttr]) * self['amplitude'], blockSignal=self.sumChanged)

    def ampChanged(self):
        self.param('sum').setValue(abs(self[self.durationAttr]) * self['amplitude'], blockSignal=self.sumChanged)

    def sumChanged(self):
        dur = self.durationAttr
        if self['sum', 'affect'] == dur:
            sign = 1 if self[dur] >= 0 else -1
            if self['amplitude'] == 0:
                self.param(dur).setValue(0, blockSignal=self.lenChanged)
            else:
                self.param(dur).setValue(sign * self['sum'] / self['amplitude'], blockSignal=self.lenChanged)
        else:
            sign = 1 if self['amplitude'] >= 0 else -1
            if self[dur] == 0:
                self.param('amplitude').setValue(0, blockSignal=self.ampChanged)
            else:
                self.param('amplitude').setValue(sign * self['sum'] / self[dur], blockSignal=self.ampChanged)

    def _sumTarget(self):
        """Return ``(target, other)`` attrs for a sequenced sum (target = sum / other); raise if not allowed."""
        target = self['sum', 'affect']
        other = 'amplitude' if target == self.durationAttr else self.durationAttr
        p = self.param(target)
        if not p.writable():
            raise ValueError(f"{self.name()}: Can not sequence over {target}; it is a read-only parameter.")
        if p['sequence'] != 'off':
            raise ValueError(f"{self.name()}: Can not sequence over {target} and sum simultaneously.")
        return target, other

    def argValues(self, ns):
        vals = StimParameter.argValues(self, ns)
        sumParam = self.param('sum')
        if sumParam['sequence'] != 'off' and sumParam.seqName() in ns:
            target, other = self._sumTarget()
            vals[target] = ns[sumParam.seqName()] / vals[other]
        return vals

    def argExprs(self):
        exprs, seq = StimParameter.argExprs(self)
        sumName, sumSeq = self.param('sum').compile()
        if sumSeq is not None:
            target, other = self._sumTarget()
            exprs[target] = f"{sumName} / ({exprs[other]})"
            seq[sumName] = sumSeq
        return exprs, seq

    def uiState(self):
        return {'sum': self['sum'], 'affect': self['sum', 'affect']}

    def setUiState(self, state):
        if 'affect' in state:
            affect = self.durationAttr if state['affect'] == 'length' else state['affect']
            self.param('sum', 'affect').setValue(affect)
        if 'sum' in state:
            self.param('sum').setValue(state['sum'], blockSignal=self.sumChanged)


class PulseTrainParameter(PulseParameter):
    stimClass = stimuli.SquarePulseTrain
    menuName = 'Pulse Train'
    defaultName = 'PulseTrain'
    durationAttr = 'pulse_duration'
    paramSpecs = [
        dict(name='start_time', type='float', axis='x', value=0.01),
        dict(name='n_pulses', type='int', value=10, limits=(1, None)),
        dict(name='pulse_duration', type='float', axis='x', value=0.005),
        dict(name='amplitude', type='float', axis='y', value=0),
        dict(name='interval', type='float', axis='x', value=0.01),
    ]


_HZ = dict(units='Hz', siPrefix=True, dec=True)


class SineParameter(StimParameter):
    stimClass = stimuli.Sine
    menuName = 'Sine'
    defaultName = 'Sine'
    paramSpecs = [
        dict(name='start_time', type='float', axis='x', value=0.01),
        dict(name='duration', type='float', axis='x', value=0.1, limits=(0, None)),
        dict(name='frequency', type='float', value=10.0, limits=(0, None), **_HZ),
        dict(name='amplitude', type='float', axis='y', value=0),
        dict(name='phase', type='float', value=0, tip='Initial phase (radians)'),
        dict(name='offset', type='float', axis='y', value=0),
    ]


class ChirpParameter(StimParameter):
    stimClass = stimuli.Chirp
    menuName = 'Chirp'
    defaultName = 'Chirp'
    paramSpecs = [
        dict(name='start_time', type='float', axis='x', value=0.01),
        dict(name='duration', type='float', axis='x', value=0.1, limits=(0, None)),
        dict(name='start_frequency', type='float', value=1.0, limits=(0, None), **_HZ),
        dict(name='end_frequency', type='float', value=100.0, limits=(0, None), **_HZ),
        dict(name='amplitude', type='float', axis='y', value=0),
        dict(name='phase', type='float', value=0, tip='Initial phase (radians)'),
        dict(name='offset', type='float', axis='y', value=0),
    ]


class RampParameter(StimParameter):
    stimClass = stimuli.Ramp
    menuName = 'Ramp'
    defaultName = 'Ramp'
    paramSpecs = [
        dict(name='start_time', type='float', axis='x', value=0.01),
        dict(name='duration', type='float', axis='x', value=0.1, limits=(0, None)),
        dict(name='slope', type='float', value=0, tip='Units per second'),
        dict(name='offset', type='float', axis='y', value=0),
    ]


class PspParameter(StimParameter):
    stimClass = stimuli.Psp
    menuName = 'Psp'
    defaultName = 'Psp'
    paramSpecs = [
        dict(name='start_time', type='float', axis='x', value=0.01),
        dict(name='rise_time', type='float', axis='x', value=0.002, limits=(0, None)),
        dict(name='decay_tau', type='float', axis='x', value=0.01, limits=(0, None)),
        dict(name='amplitude', type='float', axis='y', value=0),
        dict(name='rise_power', type='float', value=2.0, limits=(0, None)),
    ]


class OffsetParameter(StimParameter):
    stimClass = stimuli.Offset
    menuName = 'Offset'
    defaultName = 'Offset'
    paramSpecs = [
        dict(name='start_time', type='float', axis='x', value=0),
        dict(name='amplitude', type='float', axis='y', value=0),
    ]


class NoiseParameter(StimParameter):
    """Noise; new items start with a random seed."""
    stimClass = stimuli.Noise
    menuName = 'Noise'
    defaultName = 'Noise'
    paramSpecs = [
        dict(name='start_time', type='float', axis='x', value=0.01),
        dict(name='duration', type='float', axis='x', value=0.1, limits=(0, None)),
        dict(name='sigma', type='float', axis='y', value=0, limits=(0, None)),
        dict(name='mean', type='float', axis='y', value=0),
        dict(name='noise_type', type='list', limits=list(stimuli.Noise.spectral_exponents), value='white'),
        dict(name='seed', type='int', value=0, limits=(0, None)),
    ]

    def __init__(self, name=None, **kargs):
        StimParameter.__init__(self, name, **kargs)
        self.param('seed').setValue(int(np.random.SeedSequence().entropy % 2**31))


class PwmParameter(StimParameter):
    """Pwm; the 'duty' input is dimensionless, so only time-axis meta reaches it."""
    stimClass = stimuli.Pwm
    menuName = 'Pwm'
    defaultName = 'Pwm'
    inputAxes = {'duty': ('x',)}
    paramSpecs = [
        dict(name='start_time', type='float', axis='x', value=0.01),
        dict(name='duration', type='float', axis='x', value=0.1, limits=(0, None)),
        dict(name='period', type='float', axis='x', value=0.001, limits=(0, None)),
        dict(name='amplitude', type='float', axis='y', value=0),
    ]


class FilterParameter(StimParameter):
    stimClass = stimuli.Filter
    menuName = 'Filter'
    defaultName = 'Filter'
    paramSpecs = [
        dict(name='start_time', type='float', axis='x', value=0),
        dict(name='filter_type', type='list', limits=list(stimuli.Filter.filter_types), value='bessel'),
        dict(name='cutoff', type='float', value=1000.0, limits=(0, None), **_HZ),
        dict(name='order', type='int', value=4, limits=(1, None)),
    ]


## Stimulus classes offered in the "Add Stimulus" menus, in menu order.
STIM_TYPES = [
    PulseParameter,
    PulseTrainParameter,
    SineParameter,
    ChirpParameter,
    RampParameter,
    PspParameter,
    OffsetParameter,
    NoiseParameter,
    PwmParameter,
    FilterParameter,
]
STIM_TYPES_BY_MENU = {cls.menuName: cls for cls in STIM_TYPES}


def stimParamClass(stimType):
    """Return the StimParameter class for a neuroanalysis class name; raise ValueError if unknown."""
    for cls in STIM_TYPES:
        if cls.stimClass.__name__ == stimType:
            return cls
    raise ValueError(f"Unknown stimulus type {stimType!r}")


class StimParamSet(GroupParameter):
    """Top-level parameter of the simple stim generator tree."""
    def __init__(self):
        GroupParameter.__init__(self, name='Stimuli', type='group',
                           addText='Add Stimulus..', addList=[cls.menuName for cls in STIM_TYPES])
        self.meta = {}

    def addNew(self, typ):
        with self.treeChangeBlocker():  ## suppress change signal until all children are built
            self.addChild(STIM_TYPES_BY_MENU[typ]())

    def addChild(self, child, *args, **kwargs):
        child = GroupParameter.addChild(self, child, *args, **kwargs)
        self.applyMeta(child)
        return child

    def applyMeta(self, item):
        """Apply stored meta to the descendants of *item*, honoring input axis restrictions."""
        for axis, opts in self.meta.items():
            if _axisAllowed(item, axis):
                self.setMeta(axis, opts, root=item)

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
            if isinstance(ch, InputParameter) and axis not in ch.axes:
                continue
            self.setMeta(axis, opts, root=ch)

    def compile(self):
        """Return ``(functionString, {seqName: seqData})``; the string is an equivalent advanced-mode expression."""
        exprs, seq = [], {}
        for ch in self:
            e, s = ch.compile()
            exprs.append(e)
            _mergeSeq(seq, s)
        if not exprs:
            return '', seq
        body = textwrap.indent(',\n'.join(exprs), '  ')
        return f"stim(\n{body},\n)", seq

    def buildStimuli(self, ns):
        """Return the list of item Stimuli at sequence point *ns*."""
        return [ch.buildStimulus(ns) for ch in self]

    def setState(self, state):
        """Load a saved 'stimuli' state (current or legacy format)."""
        state = normalizeStimuliState(state)
        with self.treeChangeBlocker():
            self.clearChildren()
            for item in state['items']:
                stimState = item['stimulus']
                ch = self.addChild(stimParamClass(stimState['type'])(name=item['name']))
                ch.setStimulusState(stimState)
                ch.setSequenceState(item.get('sequences', {}))
                ch.setUiState(item.get('ui', {}))

    def getState(self):
        items = []
        for ch in self:
            stimState = {'schema_version': stimuli.STIMULUS_SCHEMA_VERSION}
            stimState.update(ch.stimulusState())
            items.append({
                'name': ch.name(),
                'stimulus': stimState,
                'sequences': ch.sequenceState(),
                'ui': ch.uiState(),
            })
        return {'format': STATE_FORMAT, 'items': items}


# legacy type -> (StimParameter class, {legacy param name: attr})
_LEGACY_TYPES = {
    'pulse': (PulseParameter, {'start': 'start_time', 'length': 'duration'}),
    'pulseTrain': (PulseTrainParameter, {
        'start': 'start_time', 'length': 'pulse_duration', 'period': 'interval',
        'interpulse_length': 'interval', 'pulse_number': 'n_pulses'}),
}


def _legacySeqSpec(paramState):
    mode = paramState.get('sequence', 'off')
    if mode == 'range':
        mode = 'range (n)'
    if mode == 'off':
        return None
    spec = {k: v for k, v in paramState.items() if k in SEQ_KEYS}
    spec['sequence'] = mode
    return spec


def convertLegacyState(state):
    """Convert a legacy {name: {'type': 'pulse'|'pulseTrain', <param>: {...}}} 'stimuli' state to the current format."""
    items = []
    for name, itemState in state.items():
        typ = itemState.get('type')
        if typ not in _LEGACY_TYPES:
            raise ValueError(f"Unknown stimulus type {typ!r} for {name!r}")
        cls, renames = _LEGACY_TYPES[typ]
        specs = {spec['name']: spec for spec in cls.paramSpecs}
        args = {n: spec['value'] for n, spec in specs.items()}
        sequences, ui = {}, {}
        for key, paramState in itemState.items():
            if key == 'type':
                continue
            attr = renames.get(key, key)
            if attr == 'sum':
                ui['sum'] = paramState['value']
                ui['affect'] = cls.durationAttr if paramState.get('affect', 'length') == 'length' else 'amplitude'
            elif attr in args:
                cast = int if specs[attr]['type'] == 'int' else float
                args[attr] = cast(paramState['value'])
            else:
                raise ValueError(f"Unknown parameter {key!r} in legacy {typ} {name!r}")
            seq = _legacySeqSpec(paramState)
            if seq is not None:
                sequences[attr] = seq
        stimState = {'schema_version': stimuli.STIMULUS_SCHEMA_VERSION}
        stimState.update(_stimState(cls.stimClass, name, args))
        items.append({'name': name, 'stimulus': stimState, 'sequences': sequences, 'ui': ui})
    return {'format': STATE_FORMAT, 'items': items}


def normalizeStimuliState(state):
    """Return *state* in the current format, converting a legacy state; raise ValueError for an unknown format."""
    fmt = state.get('format')
    if isinstance(fmt, numbers.Integral):
        if fmt != STATE_FORMAT:
            raise ValueError(f"Unsupported stimuli state format {fmt!r}")
        return state
    return convertLegacyState(state)


def stimuliFromState(stimuliState):
    """Return OrderedDict {item name: default (unsequenced) Stimulus} from a saved simple-mode 'stimuli' state.

    Accepts the current and legacy formats; needs no QApplication.
    """
    state = normalizeStimuliState(stimuliState)
    return collections.OrderedDict(
        (item['name'], stimuli.Stimulus.load(item['stimulus'])) for item in state['items'])
