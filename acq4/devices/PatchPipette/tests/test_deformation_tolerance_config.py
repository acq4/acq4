"""Tests for PatchPipetteState deformationTolerance config plumbing.

Cover that deformationTolerance defaults to None in the state's resolved config,
and that an explicitly passed deformationTolerance value is preserved.
"""
from types import SimpleNamespace

import pytest

from acq4.devices.PatchPipette.states._base import PatchPipetteState


class _FakeSignal:
    """Minimal Qt signal substitute."""
    def connect(self, *args, **kwargs):
        pass

    def disconnect(self, *args, **kwargs):
        pass

    def emit(self, *args, **kwargs):
        pass


class _FakeDev:
    """Minimal device substitute for state instantiation."""
    def __init__(self):
        self.sigTargetChanged = _FakeSignal()
        self.sigActiveChanged = _FakeSignal()


def test_deformation_tolerance_defaults_to_none():
    """defaultConfig() includes deformationTolerance with default None."""
    config = PatchPipetteState.defaultConfig()
    assert 'deformationTolerance' in config
    assert config['deformationTolerance'] is None


def test_deformation_tolerance_explicit_config(qapp):
    """State merges explicit deformationTolerance into resolved config."""
    dev = _FakeDev()
    state = PatchPipetteState(dev, config={'deformationTolerance': 0.3})
    assert state.config.get('deformationTolerance') == 0.3


def test_deformation_tolerance_explicit_zero(qapp):
    """State preserves zero as an explicit deformationTolerance value."""
    dev = _FakeDev()
    state = PatchPipetteState(dev, config={'deformationTolerance': 0.0})
    assert state.config.get('deformationTolerance') == 0.0
