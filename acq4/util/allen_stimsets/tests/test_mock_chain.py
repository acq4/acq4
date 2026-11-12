"""The production stimsets end to end on a MockClamp (neuroanalysis ModelCell) and the mock NI-DAQ.

Real analysis functions, buildSweep, Manager tasks, storage and notebook. The ModelCell runs in
process instead of in MockClamp's teleprox child. The mock DAQ clock and ``ptime`` run SPEED times
faster than wall time; everything that paces acquisition reads one of the two.

Slow: skipped unless ACQ4_SLOW_TESTS=1. Run as a script to print the per-set report::

    python -m acq4.util.allen_stimsets.tests.test_mock_chain [speed]
"""

from __future__ import annotations

import contextlib
import importlib
import os
import sys
import threading
import time
import types
from pathlib import Path

import numpy as np
import pytest

from acq4.devices.DAQGeneric.tests.daq_task_fakes import WaveDAQ, readerThreads, waitUntil
from acq4.util.allen_stimsets.notebook import Keys, Notebook
from acq4.util.allen_stimsets.stimset import loadProductionStimsets

from .test_runner import RunnerManager

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not os.environ.get('ACQ4_SLOW_TESTS'), reason="slow; set ACQ4_SLOW_TESTS=1"),
]

SPEED = 8.0  # mock clock seconds per wall-clock second
VC_SETS = [
    'EXTPSMOKET180424_DA_0',
    'EXTPINBATH180424_DA_0',
    'EXTPCllATT180424_DA_0',
    'EXTPBREAKN180424_DA_0',
]
WHOLE_CELL_CHAIN = ('X0NRMP_DA_0', 'X7RampN3_DA_0')
CHIRP_CHAIN = ('C2CHIRPA180503_DA_0', 'C2CHIRPB180503_DA_0')
EXPERIMENT_END = 'EXTPEXPEND180424_DA_0'
CLAMP_CONFIG = {
    'simulator': 'neuroanalysis',
    'commandChannel': {'device': 'DAQ', 'channel': '/Dev1/ao0', 'type': 'ao'},
    'primaryChannel': {'device': 'DAQ', 'channel': '/Dev1/ai0', 'type': 'ai'},
    'icHolding': 0.0,
    'vcHolding': -75e-3,  # the ModelCell's resting potential
}


class ScaledClock:
    """``time``/``sleep`` running *speed* times faster than ``ptime.time``, from now on."""

    def __init__(self, speed: float, realTime):
        self.speed = speed
        self._real = realTime
        self._t0 = realTime()

    def time(self) -> float:
        return self._t0 + (self._real() - self._t0) * self.speed

    def sleep(self, seconds: float) -> None:
        time.sleep(max(seconds, 0.0) / self.speed)


class _InProcessJob:
    def __init__(self, fn, arg):
        self._value = fn(arg)

    def result(self, timeout=None):
        return self._value


class _InProcessModule:
    """A simulator module whose ``run(cmd, _sync='async')`` computes now and returns a job."""

    def __init__(self, module):
        self._module = module

    def run(self, cmd, _sync='sync'):
        job = _InProcessJob(self._module.run, cmd)
        return job if _sync == 'async' else job.result()


class _InProcessClient:
    def _import(self, name):
        if name == 'sys':
            return types.SimpleNamespace(path=[])
        if name in ('hhSim', 'neuronSim', 'neuroanalysisSim'):
            return _InProcessModule(importlib.import_module(f'acq4.devices.MockClamp.{name}'))
        raise ImportError(name)


class _InProcessProcess:
    """Stands in for teleprox.start_process()."""

    client = _InProcessClient()

    def stop(self):
        pass


@contextlib.contextmanager
def mockRig(cellDir: Path, speed: float = SPEED):
    """Yield (manager, clamp, storage dir) with the mock clock sped up by *speed*."""
    from acq4.devices.PatchClamp import testpulse
    from acq4.drivers.nidaq import mock as mockDriver
    from acq4.util import DataManager, ptime

    mockClampModule = importlib.import_module('acq4.devices.MockClamp.MockClamp')
    clock = ScaledClock(speed, ptime.time)
    dm = RunnerManager()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ptime, 'time', clock.time)
        mp.setattr(mockDriver, 'time', types.SimpleNamespace(time=clock.time, sleep=clock.sleep))
        mp.setattr(testpulse, 'getManager', lambda: dm)
        mp.setattr(mockClampModule.teleprox, 'start_process', lambda **kw: _InProcessProcess())
        mp.setattr(mockClampModule, 'log_server', types.SimpleNamespace(address=None))
        WaveDAQ(dm)
        clamp = mockClampModule.MockClamp(dm, dict(CLAMP_CONFIG), 'Clamp1')
        storage = DataManager.getDirHandle(str(cellDir), create=True)
        try:
            yield dm, clamp, storage
        finally:
            waitUntil(lambda: readerThreads() == [], timeout=30)


def ampState(clamp) -> dict:
    """Return what the runner may change on *clamp*: parameters, holdings, autobias."""
    return {
        'params': {m: dict(p) for m, p in clamp.params.items()},
        'holding': dict(clamp.holding),
        'autobias': (clamp.autoBiasEnabled(), clamp.autoBiasTarget()),
        'testPulse': clamp.testPulseEnabled(),
    }


def runPlan(runner, clamp) -> list[dict]:
    """Run the VC sets, the whole-cell chain, the chirps and EXTPEXPEND; return one entry per run.

    The chirps run twice: as the protocol runs them (a run of their own, which starts from the
    autobias target restored at the end of the whole-cell run), then with the autobias target set
    to the VM result first. The mock has no autobias, so only the second run holds the cell at the
    target its baseline QC checks.
    """
    from acq4.util.allen_stimsets.functions.plain import plainRecording

    plan = [('set', name) for name in VC_SETS]
    plan += [('chain', WHOLE_CELL_CHAIN), ('chain', CHIRP_CHAIN), ('vmTarget', CHIRP_CHAIN)]
    plan += [('plain', EXPERIMENT_END)]
    runs = []
    for kind, arg in plan:
        if kind == 'vmTarget':
            vm = runner.notebook.lastSet('VM', lambda s: s.values.get(Keys.SET_QC))
            clamp.setAutoBiasTarget(vm.values[Keys.FULL_AVERAGE] * 1e-3)
        before = ampState(clamp)
        t0 = time.perf_counter()
        if kind in ('chain', 'vmTarget'):
            results = runner.runChain(*arg)
        elif kind == 'plain':
            runner.functions[arg] = plainRecording('VC')
            results = [(arg, runner.runSet(arg))]
        else:
            results = [(arg, runner.runSet(arg))]
        runs.append(
            {
                'run': arg,
                'results': results,
                'wall': time.perf_counter() - t0,
                'before': before,
                'after': ampState(clamp),
            }
        )
    return runs


def runInThread(fn):
    """Call *fn* on a worker thread (the runner refuses the GUI thread); return its result."""
    out = {}

    def target():
        try:
            out['result'] = fn()
        except BaseException as exc:
            out['error'] = exc

    th = threading.Thread(target=target, name='mockChain')
    th.start()
    th.join()
    if 'error' in out:
        raise out['error']
    return out['result']


def describeSet(notebook: Notebook, sci: int) -> str:
    s = notebook.set(sci)
    recs = [notebook.sweep(sw) for sw in s.sweeps]
    dascales = ' '.join(f"{r.dascale:g}" for r in recs)
    qc = ''.join('P' if r.values.get(Keys.SWEEP_QC) else '.' for r in recs)
    keys = [
        Keys.FULL_AVERAGE,
        Keys.RESISTANCE_FROM_FIT,
        Keys.PULSE_DURATION,
        'InitialScale',
        'PipetteResistance',
        'SealResistanceMax',
        'AccessResistance',
        'abortSet',
    ]
    extra = ', '.join(
        f"{k}={s.values[k]:.4g}" if isinstance(s.values[k], float) else f"{k}={s.values[k]}"
        for k in keys
        if k in s.values
    )
    last = recs[-1].values if recs else {}
    lastKeys = [k for k in (Keys.FINAL_SCALE, Keys.SPIKE_COUNT, Keys.SPIKE_DETECT) if k in last]
    extra += ''.join(f", last {k}={last[k]}" for k in lastKeys)
    return (
        f"{s.stimset:24s} SCI {sci:2d} {s.analysisType:5s} SetQC={s.values.get(Keys.SET_QC)} "
        f"sweeps={len(recs)} QC={qc} DAScale=[{dascales}] {extra}"
    )


def checkStorage(storage, notebook: Notebook) -> int:
    """Re-read every sweep through DataManager; return the number of sweeps read."""
    from acq4.util import DataManager

    root = DataManager.getDirHandle(storage.name())
    n = 0
    for runName in root.ls():
        run = root[runName]
        if not run.isDir() or run.info().get('dirType') != 'StimsetRun':
            continue
        for setName in run.ls():
            setDir = run[setName]
            if not setDir.isDir():
                continue
            assert setDir.info()['dirType'] == 'StimsetSet'
            for sweepName in setDir.ls():
                sweepDir = setDir[sweepName]
                if not sweepDir.isDir():
                    continue
                info = sweepDir.info()
                files = [f for f in sweepDir.ls() if f.endswith('.ma')]
                assert files, f"no .ma file in {sweepDir.name()}"
                data = sweepDir[files[0]].read()
                primary = np.asarray(data['Channel':'primary'])
                assert len(primary) == info['numValid'], sweepDir.name()
                assert notebook.sweep(info['sweep']).sci == info['sci']
                n += 1
    return n


def runMockChain(cellDir: Path, speed: float = SPEED, log=print):
    """Run the plan on a fresh mock rig; return (runs, notebook, sweeps read back)."""
    from acq4.util.allen_stimsets.runner import StimsetRunner

    cellDir.mkdir(parents=True, exist_ok=True)
    with mockRig(cellDir, speed) as (dm, clamp, storage):
        notebook = Notebook(cellDir / 'notebook.json')
        runner = StimsetRunner(
            clamp,
            loadProductionStimsets(),
            notebook,
            storage,
            manager=dm,
            testPulseDuringIti=False,
        )
        runner.addListener(
            lambda event, info: (
                log(f"  {event} {info.get('stimset', '')}") if event in ('setStarted',) else None
            )
        )
        runs = runInThread(lambda: runPlan(runner, clamp))
        read = checkStorage(storage, notebook)
    return runs, Notebook(cellDir / 'notebook.json'), read


def report(runs, notebook) -> str:
    lines = []
    for r in runs:
        names = ' -> '.join(n for n, _ in r['results'])
        restored = r['before'] == r['after']
        lines.append(
            f"{r['run']}: {names}  ({r['wall']:.0f} s wall, amplifier restored: {restored})"
        )
    lines += [describeSet(notebook, s.sci) for s in notebook.sets()]
    return '\n'.join(lines)


def test_mockChain(tmp_path):
    runs, notebook, read = runMockChain(tmp_path / 'cell', log=lambda msg: None)
    print(report(runs, notebook))
    for r in runs:
        assert r['before'] == r['after'], r['run']
    # the ModelCell passes every whole-cell set; runPlan explains the two chirp runs
    assert [n for n, _ in runs[4]['results']][-1] == WHOLE_CELL_CHAIN[1]
    assert all(r.passed for _, r in runs[4]['results'])
    assert read == len(notebook.sweeps()) > 0
    assert [s.stimset for s in notebook.sets()][:4] == VC_SETS


if __name__ == '__main__':
    import tempfile

    speed = float(sys.argv[1]) if len(sys.argv) > 1 else SPEED
    with tempfile.TemporaryDirectory() as d:
        runs, notebook, read = runMockChain(Path(d) / 'cell', speed)
        print(report(runs, notebook))
        print(f"{read} sweeps read back through DataManager")
