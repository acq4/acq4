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
    """Factory: make_array(rows, cols, spacing_x, spacing_y, site_role_defaults=None)."""
    from acq4.devices.InteractionSiteArray import InteractionSiteArray

    def _factory(rows=2, cols=3, spacing_x=2e-3, spacing_y=3e-3, site_role_defaults=None):
        dm = _make_dm()
        config = {
            'rows': rows,
            'cols': cols,
            'spacing_x': spacing_x,
            'spacing_y': spacing_y,
            'site_radius': 1e-3,
            'site_height': 5e-3,
        }
        if site_role_defaults is not None:
            config['site_role_defaults'] = site_role_defaults
        return InteractionSiteArray(dm, config, 'TestArray')

    return _factory


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
    def test_first_site_has_zero_offset(self, make_array):
        arr = make_array(rows=2, cols=3, spacing_x=2e-3, spacing_y=3e-3)
        pos = arr.sites[0].mapToGlobal(np.zeros(3))
        np.testing.assert_allclose(pos, [0, 0, 0], atol=1e-12)

    def test_col_offset(self, make_array):
        arr = make_array(rows=1, cols=3, spacing_x=2e-3, spacing_y=3e-3)
        # site at col=1 should be 2e-3 in x from site at col=0
        pos0 = arr.sites[0].mapToGlobal(np.zeros(3))
        pos1 = arr.sites[1].mapToGlobal(np.zeros(3))
        np.testing.assert_allclose(pos1 - pos0, [2e-3, 0, 0], atol=1e-12)

    def test_row_offset(self, make_array):
        arr = make_array(rows=3, cols=1, spacing_x=2e-3, spacing_y=3e-3)
        # site at row=1 should be 3e-3 in y from site at row=0
        pos0 = arr.sites[0].mapToGlobal(np.zeros(3))
        pos1 = arr.sites[1].mapToGlobal(np.zeros(3))
        np.testing.assert_allclose(pos1 - pos0, [0, 3e-3, 0], atol=1e-12)

    def test_row_major_ordering(self, make_array):
        arr = make_array(rows=2, cols=3, spacing_x=2e-3, spacing_y=3e-3)
        # index 3 == row=1, col=0
        pos0 = arr.sites[0].mapToGlobal(np.zeros(3))
        pos3 = arr.sites[3].mapToGlobal(np.zeros(3))
        np.testing.assert_allclose(pos3 - pos0, [0, 3e-3, 0], atol=1e-12)


class TestGetFirstAvailableSite:
    def test_returns_first_matching_role(self, make_array):
        arr = make_array(rows=1, cols=3, site_role_defaults=['nucleus', 'nucleus', 'empty'])
        site = arr.getFirstAvailableSite('nucleus')
        assert site is arr.sites[0]

    def test_skips_used_up_sites(self, make_array):
        arr = make_array(rows=1, cols=3, site_role_defaults=['nucleus', 'nucleus', 'empty'])
        arr.sites[0].used_up = True
        site = arr.getFirstAvailableSite('nucleus')
        assert site is arr.sites[1]

    def test_returns_none_when_all_used_up(self, make_array):
        arr = make_array(rows=1, cols=2, site_role_defaults=['nucleus', 'nucleus'])
        arr.sites[0].used_up = True
        arr.sites[1].used_up = True
        assert arr.getFirstAvailableSite('nucleus') is None

    def test_returns_none_when_no_matching_role(self, make_array):
        arr = make_array(rows=1, cols=2, site_role_defaults=['nucleus', 'empty'])
        assert arr.getFirstAvailableSite('clean') is None


class TestSiteRoleDefaults:
    def test_default_role_is_empty(self, make_array):
        arr = make_array(rows=1, cols=2)
        assert arr.sites[0].role == 'empty'
        assert arr.sites[1].role == 'empty'

    def test_site_role_defaults_applied(self, make_array):
        arr = make_array(rows=1, cols=3, site_role_defaults=['clean', 'nucleus', 'rinse'])
        assert arr.sites[0].role == 'clean'
        assert arr.sites[1].role == 'nucleus'
        assert arr.sites[2].role == 'rinse'

    def test_site_role_defaults_shorter_than_sites(self, make_array):
        arr = make_array(rows=1, cols=3, site_role_defaults=['clean'])
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


class TestSaveInteractPosition:
    def test_saves_interact_position_in_each_site_local_frame(self, make_array, qt_app):
        arr = make_array(rows=1, cols=2, spacing_x=2e-3, spacing_y=0)

        pip = MagicMock()
        pip.name.return_value = 'pip1'
        pip.globalPosition.return_value = np.array([1e-3, 0.0, -1e-3])

        arr.saveInteractPosition(pip)

        for site in arr.sites:
            local = site.interactLocalFor(pip)
            assert local is not None
            # reconstruct global from local and verify it matches pip's position
            reconstructed = site.mapToGlobal(local)
            np.testing.assert_allclose(reconstructed, [1e-3, 0.0, -1e-3], atol=1e-12)
