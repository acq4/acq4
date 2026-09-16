"""A parked pipette is out of the tissue and out of the objective's way.

Pipette.parkPosition() answers where that is, given an occlusion circle in the
horizontal plane -- the region a run still has to see down into. The geometry is
the whole of the guarantee: a tip that is above the surface but still over the
circle is out of the *tissue* and no use at all, because the next thing that
happens is an objective focusing through the place it is standing in.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from acq4.devices.Pipette import Pipette


def _pipette(yaw=0.0, pitch=30.0, surface=0.0, parkHeight=100e-6, parkRadius=400e-6,
             camera_center=(0.0, 0.0, 0.0)):
    """A Pipette with just enough wired up to answer geometry questions.

    Built with __new__ and hand-set attributes rather than through the device
    config machinery, exactly as test_named_moves.py does: parkPosition() reads
    the pipette's angles, its scope's surface depth and its camera's ROI centre,
    and nothing else.
    """
    pip = Pipette.__new__(Pipette)
    pip.config = {"yaw": yaw, "pitch": pitch}
    pip._calibratedPitch = None
    pip._calibratedYaw = None
    pip._globalDirection = None
    pip._localDirection = None
    pip._opts = {"parkHeight": parkHeight, "parkRadius": parkRadius}

    scope = MagicMock()
    scope.getSurfaceDepth.return_value = surface
    camera = MagicMock()
    camera.globalCenterPosition.return_value = np.asarray(camera_center, dtype=float)
    pip._scopeDev = scope
    pip._imagingDev = camera
    pip.scopeDevice = lambda: scope
    pip.imagingDevice = lambda: camera
    return pip


def test_the_park_is_at_the_configured_height_above_the_surface():
    pip = _pipette(surface=-1.2e-3, parkHeight=100e-6)

    assert pip.parkPosition()[2] == pytest.approx(-1.2e-3 + 100e-6)


def test_the_park_is_exactly_the_radius_from_the_circles_centre():
    """The caller owns the padding: this puts the tip *on* the circle it was
    handed, so a caller that wants clearance beyond the cells it measured adds
    that to the radius rather than hoping this adds some of its own."""
    pip = _pipette(yaw=0.0)

    pos = pip.parkPosition(center=(3e-3, -2e-3, 0.0), radius=650e-6)

    assert np.linalg.norm(pos[:2] - np.array([3e-3, -2e-3])) == pytest.approx(650e-6)


@pytest.mark.parametrize("yaw", [0.0, 45.0, 90.0, 180.0, -135.0])
def test_the_park_is_behind_the_circle_along_the_pipettes_own_axis(yaw):
    """Backwards along its own axis is the one direction that carries the shaft
    away from the circle too: everything behind the tip is further out and
    higher up. Retracting any other way would clear the tip and leave the shaft
    lying over the cells."""
    pip = _pipette(yaw=yaw)

    pos = pip.parkPosition(center=(0.0, 0.0, 0.0), radius=400e-6)

    axis_xy = pip.globalDirection()[:2]
    axis_xy = axis_xy / np.linalg.norm(axis_xy)
    # The offset from the centre points *against* the direction the tip points.
    offset = pos[:2] / np.linalg.norm(pos[:2])
    assert offset == pytest.approx(-axis_xy)


def test_a_bigger_circle_parks_further_out_not_higher():
    """The two are independent: the height clears the tissue, the radius clears
    the field. A radius that leaked into the height would park the tip where the
    objective travels."""
    pip = _pipette()

    near = pip.parkPosition(center=(0.0, 0.0, 0.0), radius=300e-6)
    far = pip.parkPosition(center=(0.0, 0.0, 0.0), radius=900e-6)

    assert np.linalg.norm(far[:2]) > np.linalg.norm(near[:2])
    assert far[2] == pytest.approx(near[2])


def test_the_circle_defaults_to_the_cameras_roi_and_the_configured_radius():
    """The plain "get out of the field of view" retraction, for a caller with no
    cell list to build a circle from."""
    pip = _pipette(yaw=0.0, camera_center=(7e-3, 0.0, 0.0), parkRadius=400e-6)

    pos = pip.parkPosition()

    assert pos[:2] == pytest.approx(np.array([7e-3 - 400e-6, 0.0]))


def test_only_the_circles_x_and_y_are_read():
    """An occlusion circle is a horizontal footprint. A centre carrying the
    cells' depth must not drag the park down to it."""
    pip = _pipette(surface=0.0, parkHeight=100e-6)

    deep = pip.parkPosition(center=(0.0, 0.0, -900e-6), radius=400e-6)
    flat = pip.parkPosition(center=(0.0, 0.0, 0.0), radius=400e-6)

    assert deep == pytest.approx(flat)


def test_a_vertical_pipette_has_no_parking_position():
    """Retracting a vertical pipette along its axis lifts it straight up and
    leaves it over the circle. There is no answer to give, so this says so
    instead of handing back a position that does not clear anything."""
    pip = _pipette(pitch=90.0)
    pip._name = "Pipette1"

    with pytest.raises(ValueError, match="vertical"):
        pip.parkPosition(center=(0.0, 0.0, 0.0), radius=400e-6)


def test_an_unknown_surface_depth_is_refused_rather_than_guessed():
    pip = _pipette()
    pip.scopeDevice().getSurfaceDepth.return_value = None

    with pytest.raises(ValueError, match="surface depth"):
        pip.parkPosition()


# -- isParked ----------------------------------------------------------------


def test_a_tip_at_the_park_position_reads_as_parked():
    pip = _pipette()
    pip.globalPosition = lambda: pip.parkPosition(center=(0.0, 0.0, 0.0), radius=400e-6)

    assert pip.isParked(center=(0.0, 0.0, 0.0), radius=400e-6)


def test_a_tip_further_out_and_higher_up_also_reads_as_parked():
    """Deliberately weaker than "is at parkPosition()": home, a cleaning well
    and the search position are all already clear, and driving such a tip *down*
    to the park position would be a move in the wrong direction."""
    pip = _pipette(surface=0.0, parkHeight=100e-6)
    pip.globalPosition = lambda: np.array([-5e-3, 0.0, 2e-3])

    assert pip.isParked(center=(0.0, 0.0, 0.0), radius=400e-6)


def test_a_tip_above_the_surface_but_over_the_circle_is_not_parked():
    """The failure this whole feature is about: out of the tissue is not out of
    the way, because the next thing that happens is an objective focusing
    through the place the tip is standing in."""
    pip = _pipette(surface=0.0, parkHeight=100e-6)
    pip.globalPosition = lambda: np.array([50e-6, 0.0, 1e-3])

    assert not pip.isParked(center=(0.0, 0.0, 0.0), radius=400e-6)


def test_a_tip_clear_laterally_but_still_in_the_tissue_is_not_parked():
    pip = _pipette(surface=0.0, parkHeight=100e-6)
    pip.globalPosition = lambda: np.array([-3e-3, 0.0, -80e-6])

    assert not pip.isParked(center=(0.0, 0.0, 0.0), radius=400e-6)


# -- the named move ----------------------------------------------------------


class _RecordingManager:
    """Stands in for the Manager, capturing each motion plan's name and target."""

    def __init__(self):
        self.calls = []

    def move(self, *specs, name: str = ""):
        self.calls.append((name, [np.asarray(s.position, dtype=float) for s in specs]))
        return MagicMock()


def test_go_park_names_its_move_and_targets_the_park_position(monkeypatch):
    pip = _pipette()
    pip.dm = _RecordingManager()
    monkeypatch.setattr(Pipette, "name", lambda self: "Pipette1")

    pip.goPark(speed="fast", center=(0.0, 0.0, 0.0), radius=400e-6)

    (name, positions), = pip.dm.calls
    assert name == "move Pipette1 to park"
    assert positions[0] == pytest.approx(
        pip.parkPosition(center=(0.0, 0.0, 0.0), radius=400e-6)
    )


def test_move_to_park_is_the_named_position_for_it(monkeypatch):
    """moveTo() is what protocols and the FSM reach for named positions, so
    "park" has to be one of them rather than a method only direct callers find."""
    pip = _pipette()
    pip.dm = _RecordingManager()
    monkeypatch.setattr(Pipette, "name", lambda self: "Pipette1")

    pip.moveTo("park", "fast", center=(0.0, 0.0, 0.0), radius=400e-6)

    assert pip.dm.calls[0][0] == "move Pipette1 to park"
