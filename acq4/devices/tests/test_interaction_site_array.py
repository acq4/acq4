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
    """Factory: make_array(rows, cols, role=None)."""
    from acq4.devices.InteractionSiteArray import InteractionSiteArray
    from acq4.devices.MockStage import MockStage

    def _factory(rows=2, cols=3, role=None):
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
        if role is not None:
            config['role'] = role
        return InteractionSiteArray(dm, config, 'TestArray')

    return _factory


def _calibrate(arr, col_spacing=2e-3, row_spacing=3e-3,
               interact=(0., 0., -5e-3), approach_offset=(0., 0., 5e-3)):
    """Apply a synthetic calibration in the realistic fixed-pipette / moving-stage scenario.

    The pipette tip stays at a fixed global interact point while the stage moves to bring
    each corner under it; the stage deltas encode the grid spacing. This exercises the
    common-frame correction in the array math. The approach is one measurement offset from
    the origin interact by *approach_offset*.
    """
    pip = MagicMock(spec=['name', 'globalPosition'])
    pip.name.return_value = 'pip1'
    I = np.asarray(interact, dtype=float)

    # Stage positions: moving the stage by -delta brings the next site under the fixed pipette.
    S_00 = np.array([0., 0., 0.])
    S_0N = S_00 - (arr._cols - 1) * np.array([col_spacing, 0., 0.])
    S_M0 = S_00 - (arr._rows - 1) * np.array([0., row_spacing, 0.])

    arr._parentStage.globalPosition = MagicMock(return_value=S_00)
    pip.globalPosition.return_value = I
    arr.calibrateInteractCorner(pip, 'origin')

    arr._parentStage.globalPosition = MagicMock(return_value=S_0N)
    pip.globalPosition.return_value = I
    arr.calibrateInteractCorner(pip, 'col_end')

    if arr._rows > 1:
        arr._parentStage.globalPosition = MagicMock(return_value=S_M0)
        pip.globalPosition.return_value = I
        arr.calibrateInteractCorner(pip, 'row_end')

    arr._parentStage.globalPosition = MagicMock(return_value=S_00)
    pip.globalPosition.return_value = I + np.asarray(approach_offset, dtype=float)
    arr.calibrateApproach(pip)

    arr.applyCalibration(pip)
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
    def test_returns_first_site(self, make_array):
        arr = make_array(rows=1, cols=3, role='nucleus')
        assert arr.getFirstAvailableSite() is arr.sites[0]

    def test_skips_used_up_sites(self, make_array):
        arr = make_array(rows=1, cols=3, role='nucleus')
        arr.sites[0].used_up = True
        assert arr.getFirstAvailableSite() is arr.sites[1]

    def test_returns_none_when_all_used_up(self, make_array):
        arr = make_array(rows=1, cols=2, role='nucleus')
        arr.sites[0].used_up = True
        arr.sites[1].used_up = True
        assert arr.getFirstAvailableSite() is None


class TestRole:
    def test_default_role_is_empty(self, make_array):
        arr = make_array(rows=1, cols=2)
        assert arr.role == 'empty'
        assert arr.sites[0].role == 'empty'
        assert arr.sites[1].role == 'empty'

    def test_role_applied_to_all_sites(self, make_array):
        arr = make_array(rows=2, cols=3, role='clean')
        assert arr.role == 'clean'
        assert all(site.role == 'clean' for site in arr.sites)

    def test_config_role_overrides_stale_persisted_site_role(self, qt_app):
        """A per-site role left over from an earlier config must not override the array role."""
        from acq4.devices.InteractionSiteArray import InteractionSiteArray
        from acq4.devices.MockStage import MockStage

        storage = {
            "devices/TestArray[1]_config/saved_positions": {'TestArray[1]': {'role': 'rinse'}},
        }
        dm = MagicMock()
        dm.readConfigFile.side_effect = lambda p: storage.get(p, {})
        dm.writeConfigFile.side_effect = lambda d, p: storage.update({p: d.copy()})
        dm.configFileName.side_effect = lambda p: p
        dm.listDevices.return_value = []
        dm.listInterfaces.return_value = []
        stage = MockStage(dm, {'nAxes': 3}, 'TestStage')
        dm.getDevice.side_effect = lambda n: stage if n == 'TestStage' else None

        arr = InteractionSiteArray(dm, {
            'rows': 1, 'cols': 3, 'siteRadius': 1e-3, 'siteHeight': 5e-3,
            'parentDevice': 'TestStage', 'role': 'nucleus',
        }, 'TestArray')
        assert all(site.role == 'nucleus' for site in arr.sites)


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


class TestCalibration:
    """The array interpolates the three interact corners and transmits a unique interact
    (and derived approach) position to each child site."""

    def test_interact_interpolated_and_transmitted_to_each_child(self, make_array, qt_app):
        arr = make_array(rows=2, cols=3, role='nucleus')
        I = np.array([1e-3, 2e-3, -5e-3])
        col, rowsp = 2e-3, 3e-3
        _calibrate(arr, col_spacing=col, row_spacing=rowsp, interact=I,
                   approach_offset=(0., 0., 5e-3))

        # Each child's stored interact global = I + c*[col,0,0] + r*[0,rowsp,0]
        for i, site in enumerate(arr.sites):
            r, c = divmod(i, arr._cols)
            expected = I + c * np.array([col, 0, 0]) + r * np.array([0, rowsp, 0])
            stored = site.positions['pip1']['interact global']
            np.testing.assert_allclose(stored, expected, atol=1e-12)

    def test_approach_derived_from_shared_offset(self, make_array, qt_app):
        arr = make_array(rows=2, cols=3, role='nucleus')
        I = np.array([0., 0., -5e-3])
        approach_off = np.array([0., 0., 5e-3])
        _calibrate(arr, col_spacing=2e-3, row_spacing=3e-3, interact=I,
                   approach_offset=approach_off)

        # Each child's approach ('site global') = its interact + the shared approach offset
        for site in arr.sites:
            interact = np.asarray(site.positions['pip1']['interact global'])
            approach = np.asarray(site.positions['pip1']['site global'])
            np.testing.assert_allclose(approach - interact, approach_off, atol=1e-12)

    def test_interactLocalFor_reconstructs_interact_global(self, make_array, qt_app):
        """After the stage brings a site to its approach pose, the stored interact-local maps
        back to the calibrated interact global."""
        arr = make_array(rows=1, cols=3, role='nucleus')
        I = np.array([0., 0., -5e-3])
        _calibrate(arr, col_spacing=2e-3, interact=I, approach_offset=(0., 0., 5e-3))

        # At calibration the reference stage position is S_ref = origin stage = 0, so each
        # site sits at its approach pose with the stage at 0 (the mock's current position).
        for i, site in enumerate(arr.sites):
            local = site.interactLocalFor(arr_pip(site))
            assert local is not None
            reconstructed = site.mapToGlobal(local)
            expected = I + i * np.array([2e-3, 0, 0])
            np.testing.assert_allclose(reconstructed, expected, atol=1e-12)

    def test_apply_requires_approach_and_corners(self, make_array, qt_app):
        arr = make_array(rows=1, cols=2, role='nucleus')
        pip = MagicMock(spec=['name', 'globalPosition'])
        pip.name.return_value = 'pip1'
        pip.globalPosition.return_value = np.zeros(3)
        arr._parentStage.globalPosition = MagicMock(return_value=np.zeros(3))
        # Only origin interact calibrated; applyCalibration should raise (missing keys).
        arr.calibrateInteractCorner(pip, 'origin')
        with pytest.raises(KeyError):
            arr.applyCalibration(pip)


def arr_pip(site):
    """Return a mock pipette named 'pip1' for querying a site's saved positions."""
    pip = MagicMock(spec=['name'])
    pip.name.return_value = 'pip1'
    return pip


class TestCalibrationFlow:
    def _flow(self, arr):
        from acq4.devices.InteractionSiteArray import InteractionArrayCalibrationFlow
        pip = MagicMock(spec=['name', 'globalPosition'])
        pip.name.return_value = 'pip1'
        pip.globalPosition.return_value = np.zeros(3)
        return InteractionArrayCalibrationFlow(arr, pip), pip

    def test_step_order_full_grid(self, make_array, qt_app):
        arr = make_array(rows=2, cols=5, role='nucleus')
        flow, _ = self._flow(arr)
        corners = [(s[0], s[1]) for s in flow._steps]
        assert corners == [
            ('origin', 'interact'),
            ('origin', 'approach'),
            ('row_end', 'interact'),
            ('col_end', 'interact'),
        ]

    def test_single_row_skips_row_end(self, make_array, qt_app):
        arr = make_array(rows=1, cols=4, role='nucleus')
        flow, _ = self._flow(arr)
        corners = [(s[0], s[1]) for s in flow._steps]
        assert ('row_end', 'interact') not in corners
        assert ('col_end', 'interact') in corners

    def test_single_col_skips_col_end(self, make_array, qt_app):
        arr = make_array(rows=3, cols=1, role='nucleus')
        flow, _ = self._flow(arr)
        corners = [(s[0], s[1]) for s in flow._steps]
        assert ('col_end', 'interact') not in corners
        assert ('row_end', 'interact') in corners

    def test_walking_all_steps_applies_calibration(self, make_array, qt_app):
        arr = make_array(rows=2, cols=3, role='nucleus')
        flow, pip = self._flow(arr)
        I = np.array([1e-3, 2e-3, -5e-3])
        # stage stays at origin for every capture; pipette positions encode the geometry
        arr._parentStage.globalPosition = MagicMock(return_value=np.zeros(3))
        captures = {
            ('origin', 'interact'): I,
            ('origin', 'approach'): I + np.array([0, 0, 5e-3]),
            ('row_end', 'interact'): I + np.array([0, 3e-3, 0]),
            ('col_end', 'interact'): I + np.array([2 * 2e-3, 0, 0]),
        }
        results = []
        flow.finished.connect(results.append)
        for _ in range(len(flow._steps)):
            corner, kind, _, _ = flow._steps[flow._index]
            pip.globalPosition.return_value = captures[(corner, kind)]
            flow._useCurrent()
        qt_app.processEvents()
        # Dialog accepted and calibration applied to children.
        assert results == [Qt_accepted()]
        np.testing.assert_allclose(
            arr.sites[0].positions['pip1']['interact global'], I, atol=1e-12
        )
        assert arr.columnSpacingMm('pip1') is not None

    def test_keep_existing_enabled_only_when_saved(self, make_array, qt_app):
        arr = make_array(rows=1, cols=2, role='nucleus')
        # Pre-save the origin interact so the first step can keep it.
        pip = MagicMock(spec=['name', 'globalPosition'])
        pip.name.return_value = 'pip1'
        pip.globalPosition.return_value = np.array([0., 0., -5e-3])
        arr._parentStage.globalPosition = MagicMock(return_value=np.zeros(3))
        arr.calibrateInteractCorner(pip, 'origin')

        from acq4.devices.InteractionSiteArray import InteractionArrayCalibrationFlow
        flow = InteractionArrayCalibrationFlow(arr, pip)
        # Step 1 (origin interact) has a saved value -> keep enabled
        assert flow._keepBtn.isEnabled()
        flow._keepExisting()
        # Step 2 (approach) has no saved value -> keep disabled
        assert not flow._keepBtn.isEnabled()


def Qt_accepted():
    from acq4.util import Qt
    return Qt.QDialog.Accepted
