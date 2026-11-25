"""Tests that PipetteTracker.measureTipPosition asks the pipette_detector_class tuning point."""

import random

import pytest

import acq4.util.DataManager as dm
from acq4.devices.Pipette.tracker import CorrelationPipetteTracker
from acq4.util import tuning_points
from acq4.util.tests.memory_ledger import MemoryLedger
from acq4.util.tuning_points import Runtime


class DetectorWasBuilt(Exception):
    pass


class SentinelDetector:
    def __init__(self, tracker, pipette):
        raise DetectorWasBuilt


class DetectorMutator:
    name = "recording_detector"
    unit = "slice"
    answers = {"pipette_detector_class"}
    conditions = ["sentinel"]

    def eligible(self, facts):
        return True

    def value(self, point, default, condition, facts):
        return SentinelDetector


def test_measure_tip_position_builds_the_assigned_detector_class(tmp_path):
    root = dm.getDirHandle(str(tmp_path), create=True)
    slice_dir = root.mkdir("slice_000", info={"dirType": "Slice"})
    tuning_points.install(
        Runtime("run-1", [DetectorMutator()], MemoryLedger(random.Random(0)))
    )
    # __new__ skips __init__, which only loads reference frames from the pipette's config dir.
    tracker = CorrelationPipetteTracker.__new__(CorrelationPipetteTracker)
    tracker.pipette = None
    try:
        sliceUnit = tuning_points.open_unit("slice", slice_dir=slice_dir)
        with pytest.raises(DetectorWasBuilt):
            tracker.measureTipPosition(frame=None)
        tuning_points.close_unit(sliceUnit)
    finally:
        tuning_points.uninstall()
