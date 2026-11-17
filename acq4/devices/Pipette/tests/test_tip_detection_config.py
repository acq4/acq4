"""The Pipette's tipDetection config selects the ML tip-detection model for every detector call.

Both detection call sites -- the tracker's single-frame estimate and the calibration
z-stack scan -- hand the same keyword arguments to acq4_automation's
do_pipette_tip_detection, so a rig chooses its checkpoint in one place.
"""
from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from acq4.devices.Pipette import Pipette
from acq4.devices.Pipette import calibration
from acq4.devices.Pipette.tracker import ResnetPipetteTracker


def _pipette(config):
    pip = Pipette.__new__(Pipette)
    pip.config = config
    return pip


def test_unconfigured_pipette_uses_the_default_detector():
    assert _pipette({}).tipDetectionArgs() == {}


def test_config_maps_to_detector_keyword_arguments():
    pip = _pipette({"tipDetection": {
        "checkpoint": "/models/x1/best.pt", "modelType": "x1", "neuronDetectionRoot": "/src/Neuron_Detection",
    }})

    assert pip.tipDetectionArgs() == {
        "neuron_detection_checkpoint": "/models/x1/best.pt",
        "neuron_detection_model_type": "x1",
        "neuron_detection_root": "/src/Neuron_Detection",
    }


def test_checkpoint_alone_leaves_model_type_and_root_to_the_detector():
    pip = _pipette({"tipDetection": {"checkpoint": "/models/pd4/best.pt"}})

    assert pip.tipDetectionArgs() == {"neuron_detection_checkpoint": "/models/pd4/best.pt"}


def test_unknown_key_is_rejected():
    pip = _pipette({"tipDetection": {"checkpoint": "/m.pt", "modeltype": "x1"}})

    with pytest.raises(ValueError, match="modeltype"):
        pip.tipDetectionArgs()


def test_options_without_a_checkpoint_are_rejected():
    pip = _pipette({"tipDetection": {"modelType": "x1"}})

    with pytest.raises(ValueError, match="checkpoint"):
        pip.tipDetectionArgs()


class _RecordingDetector:
    def __init__(self):
        self.calls = []

    def __call__(self, img, angle, px_size, **kwargs):
        self.calls.append(kwargs)
        return np.array([10.0, 20.0]), 1.5, 0.9, {}


@pytest.fixture
def detector(monkeypatch):
    recorder = _RecordingDetector()
    module = types.ModuleType("acq4_automation.object_detection")
    module.do_pipette_tip_detection = recorder
    monkeypatch.setitem(sys.modules, "acq4_automation.object_detection", module)
    return recorder


ARGS = {"neuron_detection_checkpoint": "/m.pt", "neuron_detection_model_type": "x1"}


class _StubPipette:
    def tipDetectionArgs(self):
        return ARGS


def test_tracker_forwards_configured_arguments(detector):
    tracker = ResnetPipetteTracker(_StubPipette())

    tracker.estimateOffset(np.zeros((8, 8)), 0.0, 1e-6)

    assert detector.calls == [{"show": False, **ARGS}]


class _Vector(np.ndarray):
    def __new__(cls, values):
        return np.asarray(values, dtype=float).view(cls)

    def x(self):
        return self[0]

    def y(self):
        return self[1]

    def z(self):
        return self[2]


class _Frame:
    def data(self):
        return np.zeros((8, 8))

    def info(self):
        return {"pixelSize": [1e-6, 1e-6]}

    def mapFromGlobalToFrame(self, pos):
        return np.asarray(pos, dtype=float)

    def mapFromFrameToGlobal(self, pos):
        return _Vector([pos[0], pos[1], 0.0])


class _Imager:
    def getFocusDepth(self):
        return 0.0


class _ScanPipette(_StubPipette):
    def globalDirection(self):
        return np.array([1.0, 0.0, 0.0])


def test_z_stack_scan_forwards_configured_arguments(detector, monkeypatch):
    monkeypatch.setattr(calibration, "acquire_z_stack", lambda *args, **kwargs: [_Frame(), _Frame()])

    calibration.scan_pipette_z_stack(_ScanPipette(), imager=_Imager())

    assert detector.calls == [{"show": False, **ARGS}] * 2
