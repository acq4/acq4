"""Pipette moves name themselves, so the throughline says where the tip was going.

Pipette.goHome() and friends hand a motion plan to the manager; the name they pass is
what reaches the planner's throughline frame and every move underneath it. Without a
name the log shows an anonymous move with no hint of its destination.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from acq4.devices.Pipette import Pipette


class _RecordingManager:
    """Stands in for the Manager, capturing the name each motion plan is given."""

    def __init__(self):
        self.calls = []

    def move(self, *specs, name: str = ""):
        self.calls.append(name)
        return MagicMock()


@pytest.fixture
def pipette(monkeypatch):
    pip = Pipette.__new__(Pipette)
    pip.dm = _RecordingManager()
    return pip


def test_go_home_names_its_move(pipette, monkeypatch):
    monkeypatch.setattr(Pipette, "homePosition", lambda self: np.zeros(3))
    monkeypatch.setattr(Pipette, "name", lambda self: "Pipette1")

    pipette.goHome(speed="fast")

    assert pipette.dm.calls == ["move Pipette1 to home"]


def test_go_target_names_its_move(pipette, monkeypatch):
    monkeypatch.setattr(Pipette, "targetPosition", lambda self: np.zeros(3))
    monkeypatch.setattr(Pipette, "name", lambda self: "Pipette1")

    pipette.goTarget(speed="fast")

    assert pipette.dm.calls == ["move Pipette1 to target"]
