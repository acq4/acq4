"""Rig smoke test for StimsetRunner: one VC and one IC production stimset with a pass-through function.

Run inside ACQ4, off the GUI thread::

    from acq4.util.allen_stimsets.tools import runner_smoke
    report = runner_smoke.run(man)

Stimulates whatever is on the headstage (VC smoke test pulses; IC steps of *icDascale* pA), changes
and restores amplifier settings, switches to I=0 mid-sweep and stops one sweep early. Does not move
anything or change pressure.
"""

from __future__ import annotations

import time

import numpy as np

from ..core import (
    AmplifierSettings,
    EarlyStop,
    SetConfig,
    SetResult,
    SweepConfig,
    SweepDecision,
    ZeroCommand,
)
from ..functions.base import AnalysisFunction
from ..notebook import Notebook
from ..runner import StimsetRunner
from .. import stimset as stimsetModule

VC_STIMSET = 'EXTPSMOKET180424_DA_0'
IC_STIMSET = 'X1PS_SubThresh_DA_0'


def passThrough(
    mode,
    sampleInterval,
    numSweeps,
    dascale=1.0,
    amplifier=None,
    runAmplifier=None,
    mid=None,
    iti=None,
):
    """Return an AnalysisFunction class that plays *numSweeps* sweeps and records what it saw.

    *mid* is {set sweep index: (time ms, action)}: midSweep returns action once data reaches time.
    """
    mid = mid or {}

    class PassThrough(AnalysisFunction):
        miesName = 'PassThrough'
        analysisType = 'PT'
        clampMode = mode
        seen = []

        def preSet(self):
            return SetConfig(
                clampMode=mode,
                sampleInterval=sampleInterval,
                amplifier=amplifier or AmplifierSettings(),
                runAmplifier=runAmplifier or AmplifierSettings(),
            )

        def preSweep(self, i, layout):
            self.i = i
            self.acted = False
            self.calls = []
            return SweepConfig(dascale=dascale)

        def midSweep(self, data):
            self.calls.append((time.perf_counter(), data.numValid))
            when, action = mid.get(self.i, (None, None))
            if action is not None and not self.acted and data.acquiredDuration >= when:
                self.acted = True
                return action
            return None

        def postSweep(self, data):
            valid = data.data[: data.numValid]
            self.seen.append(
                {
                    'sweep': data.sweep,
                    'numValid': data.numValid,
                    'planned': len(data.data),
                    'finite': bool(np.all(np.isfinite(valid))),
                    'nanTail': bool(np.all(np.isnan(data.data[data.numValid :]))),
                    'stoppedEarly': data.stoppedEarly,
                    'commandZeroedAt': data.commandZeroedAt,
                    'midSweepCalls': len(self.calls),
                    'partialCounts': [n for _, n in self.calls],
                    'mean': float(np.mean(valid)) if len(valid) else None,
                }
            )
            last = self.i + 1 >= numSweeps
            return SweepDecision(True, 'endSetPassed' if last else 'continue', iti=iti)

        def postSet(self):
            return SetResult(passed=True)

    return PassThrough


def ampState(clamp):
    """Return the amplifier settings the runner may touch, per mode, plus holding and autobias."""
    state = {'mode': clamp.getMode(), 'holding': dict(clamp.holding)}
    params = ['HoldingEnable', 'PrimarySignalLPF', 'PipetteOffset']
    icParams = ['BridgeBalEnable', 'BridgeBalResist', 'NeutralizationEnable', 'NeutralizationCap']
    original = clamp.getMode()
    for mode in ('VC', 'IC'):
        clamp.setMode(mode)
        state[mode] = clamp.mc.getParams(params + (icParams if mode == 'IC' else []))
    clamp.setMode(original)
    state['autobias'] = (clamp.autoBiasEnabled(), clamp.autoBiasTarget())
    state['testPulse'] = clamp.testPulseEnabled()
    return state


def run(man, clampName='Clamp1', storageDir=None, icDascale=20.0, vcIti=2.0, icIti=6.0):
    """Run the VC and IC smoke sets; return a report dict. Blocks for about half a minute.

    *vcIti*/*icIti* are the ITIs after each sweep, s; the test pulse and autobias run during them.
    """
    clamp = man.getDevice(clampName)
    stimsets = stimsetModule.loadProductionStimsets()
    if storageDir is None:
        storageDir = man.getCurrentDir()
    notebook = Notebook()
    report = {'before': ampState(clamp)}
    tpCounts = []

    vc = passThrough(
        'VC',
        0.005,
        numSweeps=2,
        amplifier=AmplifierSettings(besselFilter=5000.0, holding=-20.0),
        iti=vcIti,
    )
    ic = passThrough(
        'IC',
        0.02,
        numSweeps=3,
        dascale=icDascale,
        amplifier=AmplifierSettings(
            bridgeBalanceEnabled=False,
            bridgeBalance=10.0,
            capNeutralizationEnabled=False,
            capNeutralization=1.0,
            besselFilter=6000.0,
        ),
        runAmplifier=AmplifierSettings(autobiasEnabled=True, autobiasTarget=-65.0),
        mid={1: (1000.0, ZeroCommand('smoke')), 2: (1000.0, EarlyStop('smoke', extraIti=0.5))},
        iti=icIti,
    )
    runner = StimsetRunner(
        clamp,
        stimsets,
        notebook,
        storageDir,
        manager=man,
        functions={VC_STIMSET: vc, IC_STIMSET: ic},
        recordSecondary=True,
    )
    runner.addListener(
        lambda ev, info: (
            tpCounts.append((ev, time.time(), clamp._testPulseHistorySize))
            if ev in ('iti', 'sweepStarted', 'sweepFinished')
            else None
        )
    )
    for name, fn in [(VC_STIMSET, vc), (IC_STIMSET, ic)]:
        t0 = time.time()
        result = runner.runSet(name)
        report[name] = {
            'passed': result.passed,
            'duration': time.time() - t0,
            'sweeps': list(fn.seen),
            'during': ampStateAfterSet(clamp),
        }
    report['after'] = ampState(clamp)
    report['tpCounts'] = tpCounts
    report['notebook'] = [(r.sweep, r.stimset) for r in notebook.sweeps()]
    report['storage'] = storageDir.name()
    return report


def ampStateAfterSet(clamp):
    return {
        'mode': clamp.getMode(),
        'holding': dict(clamp.holding),
        'autobias': (clamp.autoBiasEnabled(), clamp.autoBiasTarget()),
    }
