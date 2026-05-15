# Tests for plan data structures and helpers.
from __future__ import annotations

import numpy as np
import pytest

from acq4.motion.plan import AtomicMove, ParallelGroup, SequentialGroup, collect_devices
from acq4.motion.tests.conftest import MockDevice


def test_atomic_move_stores_fields():
    dev = MockDevice("d1", (1.0, 2.0, 3.0))
    move = AtomicMove(dev, [1.0, 2.0, 3.0], "fast", "test move")
    assert move.device is dev
    np.testing.assert_array_equal(move.position, [1.0, 2.0, 3.0])
    assert move.speed == "fast"
    assert move.explanation == "test move"


def test_atomic_move_position_is_ndarray():
    dev = MockDevice("d1")
    move = AtomicMove(dev, [0, 0, 0], "slow")
    assert isinstance(move.position, np.ndarray)


def test_sequential_group_stores_steps():
    d = MockDevice("d")
    steps = [AtomicMove(d, [0, 0, 0], "fast"), AtomicMove(d, [1, 0, 0], "slow")]
    group = SequentialGroup(steps, "my seq")
    assert group.steps is steps
    assert group.explanation == "my seq"


def test_parallel_group_stores_steps():
    d = MockDevice("d")
    steps = [AtomicMove(d, [0, 0, 0], "fast")]
    group = ParallelGroup(steps, "my par")
    assert group.steps is steps
    assert group.explanation == "my par"


def test_collect_devices_atomic():
    d = MockDevice("d")
    move = AtomicMove(d, [0, 0, 0], "fast")
    assert collect_devices(move) == {d}


def test_collect_devices_sequential():
    d1 = MockDevice("d1")
    d2 = MockDevice("d2")
    group = SequentialGroup([AtomicMove(d1, [0, 0, 0], "fast"), AtomicMove(d2, [0, 0, 0], "fast")])
    assert collect_devices(group) == {d1, d2}


def test_collect_devices_parallel():
    d1 = MockDevice("d1")
    d2 = MockDevice("d2")
    group = ParallelGroup([AtomicMove(d1, [0, 0, 0], "fast"), AtomicMove(d2, [0, 0, 0], "fast")])
    assert collect_devices(group) == {d1, d2}


def test_collect_devices_nested():
    d1 = MockDevice("d1")
    d2 = MockDevice("d2")
    d3 = MockDevice("d3")
    inner = ParallelGroup([AtomicMove(d2, [0, 0, 0], "fast"), AtomicMove(d3, [0, 0, 0], "fast")])
    outer = SequentialGroup([AtomicMove(d1, [0, 0, 0], "fast"), inner])
    assert collect_devices(outer) == {d1, d2, d3}


def test_collect_devices_deduplicates():
    d = MockDevice("d")
    group = SequentialGroup([AtomicMove(d, [0, 0, 0], "fast"), AtomicMove(d, [1, 0, 0], "fast")])
    assert collect_devices(group) == {d}
