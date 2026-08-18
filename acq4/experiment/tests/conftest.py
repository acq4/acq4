"""Shared fixtures for acq4.experiment tests."""
import pytest

from acq4.experiment.protocol_file import ProtocolFile


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


class FakePatchPipette:
    """Minimal fake of PatchPipette for FSM-action tests.

    ``state_sequence`` is the list of state names ``getState()`` reports on successive
    polls (simulating the FSM self-driving). ``setState`` records its calls and sets the
    current state to the requested entry state. ``stop_calls`` records state-job stops
    (the Cancel-style safeAbort path).

    An empty ``state_sequence`` (the default) is the deliberate "never advances"
    shape some tests rely on: ``getState()`` then repeats whatever ``setState()``
    last set, forever, so a mid-poll ``check_stop``/``next_cell_requested`` is
    what has to end the drive. A *non-empty* ``state_sequence`` that runs out
    without ``getState()`` ever reporting one of the caller's terminal states is
    instead a broken test setup, not that shape -- with ``sleep`` commonly
    monkeypatched to a no-op in these tests, silently repeating the last state
    would turn it into a hanging hot loop instead of a fast, clear failure.
    """

    def __init__(self, state_sequence=()):
        self._seq = list(state_sequence)
        self._had_sequence = bool(self._seq)
        self._current = "out"
        self.setState_calls = []
        self.stop_calls = []
        self.cell = None
        self.setCell_calls = []

    def setCell(self, cell, target=True):
        # The orchestrator hands each cell to its pipette before running the
        # protocol; recorded rather than acted on, since these tests' "cells"
        # are sentinels with no position to target.
        self.setCell_calls.append((cell, target))
        self.cell = cell

    def setState(self, state, **config):
        self.setState_calls.append((state, config))
        self._current = state
        return FakeStateJob(state, self)

    def getState(self):
        if self._seq:
            self._current = self._seq.pop(0)
        elif self._had_sequence:
            raise RuntimeError(
                f"FakePatchPipette: declared state_sequence exhausted while parked "
                f"at {self._current!r} -- it never reached a declared terminal state"
            )
        return FakeStateJob(self._current, self)


@pytest.fixture
def fake_pip_factory():
    def make(state_sequence):
        return FakePatchPipette(state_sequence)

    return make
