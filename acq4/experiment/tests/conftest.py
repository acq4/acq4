"""Shared fixtures for acq4.experiment tests."""
import time

import pytest

from acq4.experiment.protocol_file import ProtocolFile
from acq4.util import Qt


@pytest.fixture
def make_pf(tmp_path):
    """Factory for a minimally valid ProtocolFile, loaded from a real file on
    disk so param_values()/param_tree behave like the genuine article. Tests
    that need run() to do something in particular overwrite pf.run afterward
    with a sentinel; `params` (a pyqtgraph Parameter children spec) becomes the
    protocol's PARAMS."""

    def make(params=None, name="protocol.py"):
        path = tmp_path / name
        path.write_text(
            f"PARAMS = {params or []!r}\n\n\ndef run(ctx, **kwargs):\n    return None\n"
        )
        pf = ProtocolFile(str(path))
        pf.load()
        return pf

    return make


class FakeStateJob:
    """Stand-in for a PatchPipetteState job: exposes .stateName and a stop() that
    mirrors the real state job (records the cancel on the owning pipette)."""

    def __init__(self, name, pipette=None):
        self.stateName = name
        self._pipette = pipette

    def stop(self, reason=None, wait=False):
        if self._pipette is not None:
            self._pipette.stop_calls.append((self.stateName, reason, wait))


class FakePatchPipette(Qt.QObject):
    """Minimal fake of PatchPipette for FSM-action tests.

    ``setState`` records its calls, then changes state to the requested entry state
    and on through every state in ``state_sequence``, all before it returns
    (simulating the FSM self-driving). Each change emits a ``state_change``
    sigNewEvent and then sigStateChanged, in that order, as PatchPipette._setState
    does. ``changeState`` drives a change by hand. ``stop_calls`` records state-job
    stops (the Cancel-style safeAbort path).

    An empty ``state_sequence`` (the default) leaves the pipette in the entry state,
    so a ``check_stop``/``next_cell_requested`` is what has to end the drive.
    """

    sigStateChanged = Qt.Signal(object, object, object)  # self, newState, oldState
    sigNewEvent = Qt.Signal(object, object)  # self, event

    def __init__(self, state_sequence=(), name="Pipette1"):
        super().__init__()
        self._seq = list(state_sequence)
        self._name = name
        self._current = "out"
        self.setState_calls = []
        self.stop_calls = []
        self.cell = None
        self.setCell_calls = []

    def name(self):
        return self._name

    def setCell(self, cell, target=True):
        # The orchestrator hands each cell to its pipette before running the
        # protocol; recorded rather than acted on, since these tests' "cells"
        # are sentinels with no position to target.
        self.setCell_calls.append((cell, target))
        self.cell = cell

    def setState(self, state, **config):
        self.setState_calls.append((state, config))
        self.changeState(state)
        sequence, self._seq = self._seq, []
        for nextState in sequence:
            self.changeState(nextState)
        return FakeStateJob(state, self)

    def changeState(self, state):
        oldState, self._current = self._current, state
        self.sigNewEvent.emit(
            self,
            {
                "device": self._name,
                "event_time": time.time(),
                "event": "state_change",
                "state": state,
                "old_state": oldState,
            },
        )
        self.sigStateChanged.emit(self, state, oldState)

    def getState(self):
        return FakeStateJob(self._current, self)


@pytest.fixture
def fake_pip_factory():
    def make(state_sequence):
        return FakePatchPipette(state_sequence)

    return make
