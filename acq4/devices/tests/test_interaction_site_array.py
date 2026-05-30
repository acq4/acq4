# Tests for InteractionSiteArray: child-site creation, offsets, role selection, and calibration.
# Uses real InteractionSiteArray/InteractionSite with a mock DeviceManager.

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import numpy as np
import pytest


def _make_dm(extra_storage=None):
    """Create a mock device manager with per-path config file storage."""
    storage = {}
    if extra_storage:
        storage.update(extra_storage)

    dm = MagicMock()
    dm.readConfigFile.side_effect = lambda path: storage.get(path, {})
    dm.writeConfigFile.side_effect = lambda data, path: storage.update({path: data.copy()})
    dm.configFileName.side_effect = lambda path: path
    dm.listDevices.return_value = []
    dm.listInterfaces.return_value = []
    dm.getDevice.side_effect = lambda name: None
    return dm


@pytest.fixture(scope="module")
def qt_app():
    from acq4.util import Qt
    app = Qt.QApplication.instance()
    if app is None:
        app = Qt.QApplication(sys.argv)
    return app


@pytest.fixture
def make_array(qt_app):
    """Factory: make_array(rows, cols, siteRoleDefaults=None)."""
    from acq4.devices.InteractionSiteArray import InteractionSiteArray
    from acq4.devices.MockStage import MockStage

    def _factory(rows=2, cols=3, siteRoleDefaults=None):
        dm = _make_dm()
        stage = MockStage(dm, {'nAxes': 3}, 'TestStage')
        dm.getDevice.side_effect = lambda name: stage if name == 'TestStage' else None
        config = {
            'rows': rows,
            'cols': cols,
            'siteRadius': 1e-3,
            'siteHeight': 5e-3,
            'parentDevice': 'TestStage',
        }
        if siteRoleDefaults is not None:
            config['siteRoleDefaults'] = siteRoleDefaults
        return InteractionSiteArray(dm, config, 'TestArray')

    return _factory


def _make_pip(approach, stage_pos, interact=None):
    """Make a mock pipette at *approach* position with a mock stage at *stage_pos*."""
    pip = MagicMock(spec=['name', 'globalPosition'])
    pip.name.return_value = 'pip1'
    pip.globalPosition.return_value = np.asarray(approach, dtype=float)
    return pip, np.asarray(stage_pos, dtype=float)


def _calibrate(arr, col_spacing=2e-3, row_spacing=3e-3, approach=(0., 0., 0.)):
    """Apply a synthetic calibration so tests can verify site positions."""
    from unittest.mock import MagicMock
    P = np.asarray(approach, dtype=float)

    pip = MagicMock(spec=['name', 'globalPosition'])
    pip.name.return_value = 'pip1'
    pip.globalPosition.return_value = P

    # Stage positions for each corner: stage moves negatively to bring sites right/down.
    S_00 = np.array([0., 0., 0.])
    S_0_N = S_00 + (arr._cols - 1) * np.array([-col_spacing, 0., 0.])
    S_M_0 = S_00 + (arr._rows - 1) * np.array([0., -row_spacing, 0.])

    arr._parentStage.globalPosition = MagicMock(return_value=S_00)
    arr.calibrateCorner(pip, 'origin')

    arr._parentStage.globalPosition = MagicMock(return_value=S_0_N)
    arr.calibrateCorner(pip, 'col_end')

    if arr._rows > 1:
        arr._parentStage.globalPosition = MagicMock(return_value=S_M_0)
        arr.calibrateCorner(pip, 'row_end')

    arr.applySpacing(pip)
    return pip


class TestChildSiteCount:
    def test_creates_correct_number_of_sites(self, make_array):
        arr = make_array(rows=2, cols=3)
        assert len(arr.sites) == 6

    def test_single_row(self, make_array):
        arr = make_array(rows=1, cols=4)
        assert len(arr.sites) == 4

    def test_single_col(self, make_array):
        arr = make_array(rows=3, cols=1)
        assert len(arr.sites) == 3


class TestChildSiteOffsets:
    """After calibration, each site has a unique offset so it arrives at the approach
    position when the stage is moved to the correct position."""

    def test_all_sites_at_approach_pos_after_calibration(self, make_array):
        arr = make_array(rows=1, cols=3)
        _calibrate(arr, col_spacing=2e-3)
        # After applySpacing, each site's globalPosition() should equal approach (0,0,0)
        # only when the stage is at its calibrated position for that site.
        # We verify indirectly: site offsets differ by col_spacing.
        pos0 = arr.sites[0].mapToGlobal(np.zeros(3))
        pos1 = arr.sites[1].mapToGlobal(np.zeros(3))
        pos2 = arr.sites[2].mapToGlobal(np.zeros(3))
        np.testing.assert_allclose(pos1 - pos0, [2e-3, 0, 0], atol=1e-12)
        np.testing.assert_allclose(pos2 - pos0, [4e-3, 0, 0], atol=1e-12)

    def test_row_offsets_after_calibration(self, make_array):
        arr = make_array(rows=3, cols=1)
        _calibrate(arr, row_spacing=3e-3)
        pos0 = arr.sites[0].mapToGlobal(np.zeros(3))
        pos1 = arr.sites[1].mapToGlobal(np.zeros(3))
        np.testing.assert_allclose(pos1 - pos0, [0, 3e-3, 0], atol=1e-12)

    def test_row_major_ordering_after_calibration(self, make_array):
        arr = make_array(rows=2, cols=3)
        _calibrate(arr, col_spacing=2e-3, row_spacing=3e-3)
        pos0 = arr.sites[0].mapToGlobal(np.zeros(3))
        pos3 = arr.sites[3].mapToGlobal(np.zeros(3))  # row=1, col=0
        np.testing.assert_allclose(pos3 - pos0, [0, 3e-3, 0], atol=1e-12)

    def test_spacing_mm_helpers(self, make_array):
        arr = make_array(rows=2, cols=3)
        _calibrate(arr, col_spacing=2e-3, row_spacing=4e-3)
        assert abs(arr.columnSpacingMm('pip1') - 2.0) < 0.01
        assert abs(arr.rowSpacingMm('pip1') - 4.0) < 0.01


class TestGetFirstAvailableSite:
    def test_returns_first_matching_role(self, make_array):
        arr = make_array(rows=1, cols=3, siteRoleDefaults=['nucleus', 'nucleus', 'empty'])
        site = arr.getFirstAvailableSite('nucleus')
        assert site is arr.sites[0]

    def test_skips_used_up_sites(self, make_array):
        arr = make_array(rows=1, cols=3, siteRoleDefaults=['nucleus', 'nucleus', 'empty'])
        arr.sites[0].used_up = True
        site = arr.getFirstAvailableSite('nucleus')
        assert site is arr.sites[1]

    def test_returns_none_when_all_used_up(self, make_array):
        arr = make_array(rows=1, cols=2, siteRoleDefaults=['nucleus', 'nucleus'])
        arr.sites[0].used_up = True
        arr.sites[1].used_up = True
        assert arr.getFirstAvailableSite('nucleus') is None

    def test_returns_none_when_no_matching_role(self, make_array):
        arr = make_array(rows=1, cols=2, siteRoleDefaults=['nucleus', 'empty'])
        assert arr.getFirstAvailableSite('clean') is None


class TestSiteRoleDefaults:
    def test_default_role_is_empty(self, make_array):
        arr = make_array(rows=1, cols=2)
        assert arr.sites[0].role == 'empty'
        assert arr.sites[1].role == 'empty'

    def test_siteRoleDefaults_applied(self, make_array):
        arr = make_array(rows=1, cols=3, siteRoleDefaults=['clean', 'nucleus', 'rinse'])
        assert arr.sites[0].role == 'clean'
        assert arr.sites[1].role == 'nucleus'
        assert arr.sites[2].role == 'rinse'

    def test_siteRoleDefaults_shorter_than_sites(self, make_array):
        arr = make_array(rows=1, cols=3, siteRoleDefaults=['clean'])
        assert arr.sites[0].role == 'clean'
        assert arr.sites[1].role == 'empty'
        assert arr.sites[2].role == 'empty'


class TestChildSiteDeviceInterface:
    def test_child_sites_return_none_from_device_interface(self, make_array, qt_app):
        arr = make_array(rows=1, cols=2)
        win = MagicMock()
        for site in arr.sites:
            assert site.deviceInterface(win) is None

    def test_child_site_is_array_child(self, make_array):
        arr = make_array(rows=1, cols=2)
        for site in arr.sites:
            assert site._is_array_child() is True


class TestGetSite:
    def test_get_site_by_index(self, make_array):
        arr = make_array(rows=2, cols=3)
        for i in range(6):
            assert arr.getSite(i) is arr.sites[i]


class TestCalibrateInteract:
    def test_interact_position_stored_for_all_sites(self, make_array, qt_app):
        arr = make_array(rows=1, cols=2)
        pip = _calibrate(arr, col_spacing=2e-3)

        # Lower pip to interact depth
        interact_global = np.array([0., 0., -5e-3])
        pip.globalPosition.return_value = interact_global
        arr.calibrateInteract(pip)

        # All sites should have the same interact global stored
        for site in arr.sites:
            stored = site.positions.get('pip1', {}).get('interact global')
            assert stored is not None
            np.testing.assert_allclose(stored, interact_global, atol=1e-12)

    def test_interactLocalFor_is_consistent_with_site_position(self, make_array, qt_app):
        """The interact local position, when mapped back to global, should equal interact_global."""
        arr = make_array(rows=1, cols=2)
        pip = _calibrate(arr, col_spacing=2e-3)

        interact_global = np.array([0., 0., -5e-3])
        pip.globalPosition.return_value = interact_global
        arr.calibrateInteract(pip)

        # For site[0] (at approach pos [0,0,0]): interact local = interact_global - site.globalPos
        # When stage moves to approach [0,0], site[0].globalPosition() = approach = [0,0,0]
        # So interactLocalFor should be [0,0,-5e-3] in site[0]'s frame
        local0 = arr.sites[0].interactLocalFor(pip)
        assert local0 is not None
        reconstructed = arr.sites[0].mapToGlobal(local0)
        np.testing.assert_allclose(reconstructed, interact_global, atol=1e-12)
