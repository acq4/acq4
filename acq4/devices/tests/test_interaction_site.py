# Tests for InteractionSite role/used_up tracking and array-child UI suppression.
# Uses a real InteractionSite with a mock DeviceManager to avoid hardware dependencies.

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest


def _make_dm(saved_positions=None):
    """Create a mock device manager that simulates per-device config file storage."""
    storage = {}
    if saved_positions:
        # store under the canonical path prefix matching configPath()
        storage[os.path.join("devices", "TestSite_config", "saved_positions")] = saved_positions.copy()

    dm = MagicMock()
    dm.readConfigFile.side_effect = lambda path: storage.get(path, {})
    dm.writeConfigFile.side_effect = lambda data, path: storage.update({path: data.copy()})
    dm.configFileName.side_effect = lambda path: path
    dm.listDevices.return_value = []
    return dm


@pytest.fixture(scope="module")
def qt_app():
    from acq4.util import Qt
    app = Qt.QApplication.instance()
    if app is None:
        app = Qt.QApplication(sys.argv)
    return app


@pytest.fixture
def make_site(qt_app):
    """Factory fixture: make_site(saved_positions=None, parent=None)."""
    from acq4.devices.InteractionSite import InteractionSite

    def _factory(saved_positions=None, parent=None):
        dm = _make_dm(saved_positions)
        config = {'radius': 1e-3, 'height': 5e-3}
        site = InteractionSite(dm, config, 'TestSite')
        if parent is not None:
            site.parentDevice = lambda: parent
        return site

    return _factory


class TestRoleDefault:
    def test_role_defaults_to_empty(self, make_site):
        site = make_site()
        assert site.role == 'empty'


class TestRoleValidation:
    def test_valid_roles_accepted(self, make_site):
        site = make_site()
        for role in ('clean', 'rinse', 'nucleus', 'refill', 'empty'):
            site.role = role  # should not raise

    def test_invalid_role_raises(self, make_site):
        site = make_site()
        with pytest.raises(ValueError):
            site.role = 'invalid_role'


class TestRolePersistence:
    def test_role_setter_writes_to_config(self, make_site):
        site = make_site()
        site.role = 'clean'
        assert site.dm.writeConfigFile.called
        args = site.dm.writeConfigFile.call_args[0]
        data = args[0]
        assert data.get('TestSite', {}).get('role') == 'clean'

    def test_role_loaded_from_saved_positions(self, make_site):
        site = make_site(saved_positions={'TestSite': {'role': 'nucleus', 'offset': [0, 0, 0]}})
        assert site.role == 'nucleus'


class TestRoleSignal:
    def test_role_change_emits_signal(self, make_site, qt_app):
        site = make_site()
        emitted = []
        site.sigRoleChanged.connect(emitted.append)
        site.role = 'clean'
        Qt_app = qt_app
        from acq4.util import Qt
        Qt.QApplication.processEvents()
        assert emitted == ['clean']

    def test_role_signal_not_emitted_if_unchanged(self, make_site, qt_app):
        site = make_site()
        site.role = 'rinse'
        emitted = []
        site.sigRoleChanged.connect(emitted.append)
        site.role = 'rinse'
        from acq4.util import Qt
        Qt.QApplication.processEvents()
        assert emitted == []


class TestUsedUp:
    def test_used_up_defaults_to_false(self, make_site):
        site = make_site()
        assert site.used_up is False

    def test_used_up_loaded_from_saved_positions(self, make_site):
        site = make_site(saved_positions={'TestSite': {'used_up': True, 'offset': [0, 0, 0]}})
        assert site.used_up is True

    def test_used_up_setter_writes_to_config(self, make_site):
        site = make_site()
        site.used_up = True
        assert site.dm.writeConfigFile.called
        args = site.dm.writeConfigFile.call_args[0]
        data = args[0]
        assert data.get('TestSite', {}).get('used_up') is True

    def test_used_up_signal_emitted(self, make_site, qt_app):
        site = make_site()
        emitted = []
        site.sigUsedUpChanged.connect(emitted.append)
        site.used_up = True
        from acq4.util import Qt
        Qt.QApplication.processEvents()
        assert emitted == [True]

    def test_used_up_signal_not_emitted_if_unchanged(self, make_site, qt_app):
        site = make_site()
        site.used_up = True
        emitted = []
        site.sigUsedUpChanged.connect(emitted.append)
        site.used_up = True
        from acq4.util import Qt
        Qt.QApplication.processEvents()
        assert emitted == []


class TestParentStageResolution:
    def test_a_site_with_no_parent_rides_no_stage(self, make_site):
        site = make_site()
        assert site._parentStage is None

    def test_a_parent_assigned_after_construction_is_still_found(self, make_site):
        from acq4.devices.MockStage import MockStage

        site = make_site()
        stage = MockStage(site.dm, {'nAxes': 3}, 'LateStage')
        try:
            site.parentDevice = lambda: stage
            assert site._parentStage is stage
        finally:
            stage.quit()


class TestIsArrayChild:
    def test_is_array_child_false_with_no_parent(self, make_site):
        site = make_site()
        assert site._is_array_child() is False

    def test_is_array_child_false_with_regular_parent(self, make_site):
        parent = MagicMock(spec=[])  # no getFirstAvailableSite
        site = make_site(parent=parent)
        assert site._is_array_child() is False

    def test_is_array_child_true_with_array_parent(self, make_site):
        parent = MagicMock()
        parent.getFirstAvailableSite = MagicMock()
        site = make_site(parent=parent)
        assert site._is_array_child() is True


class TestDeviceInterface:
    def test_device_interface_returns_widget_for_standalone(self, make_site, qt_app):
        from acq4.devices.InteractionSite import InteractionSiteDeviceGui
        site = make_site()
        win = MagicMock()
        result = site.deviceInterface(win)
        assert isinstance(result, InteractionSiteDeviceGui)

    def test_device_interface_returns_none_for_array_child(self, make_site, qt_app):
        parent = MagicMock()
        parent.getFirstAvailableSite = MagicMock()
        site = make_site(parent=parent)
        win = MagicMock()
        result = site.deviceInterface(win)
        assert result is None


class TestTubeId:
    def test_tube_id_defaults_to_none(self, make_site):
        site = make_site()
        assert site.tube_id is None

    def test_tube_id_loaded_from_saved_positions(self, make_site):
        site = make_site(
            saved_positions={'TestSite': {'tube_id': 'PFS4_251103_701_A01', 'offset': [0, 0, 0]}}
        )
        assert site.tube_id == 'PFS4_251103_701_A01'

    def test_tube_id_setter_writes_to_config(self, make_site):
        site = make_site()
        site.tube_id = 'PFS4_251103_701_A01'
        args = site.dm.writeConfigFile.call_args[0]
        assert args[0].get('TestSite', {}).get('tube_id') == 'PFS4_251103_701_A01'

    def test_tube_id_signal_emitted(self, make_site, qt_app):
        site = make_site()
        emitted = []
        site.sigTubeIdChanged.connect(emitted.append)
        site.tube_id = 'T1'
        from acq4.util import Qt
        Qt.QApplication.processEvents()
        assert emitted == ['T1']

    def test_tube_id_signal_not_emitted_if_unchanged(self, make_site, qt_app):
        site = make_site()
        site.tube_id = 'T1'
        emitted = []
        site.sigTubeIdChanged.connect(emitted.append)
        site.tube_id = 'T1'
        from acq4.util import Qt
        Qt.QApplication.processEvents()
        assert emitted == []


def _pip(name='pip1', pos=(0.0, 0.0, 0.0)):
    import numpy as np
    pip = MagicMock(spec=['name', 'globalPosition'])
    pip.name.return_value = name
    pip.globalPosition.return_value = np.asarray(pos, dtype=float)
    return pip


class TestSaveCalibration:
    def test_origin_moves_to_approach_and_interact_lands_where_captured(self, make_site):
        import numpy as np
        site = make_site()
        A = np.array([1e-3, 2e-3, 3e-3])
        I = np.array([1.5e-3, 2e-3, -2e-3])
        site.saveCalibration(_pip(), A, I)
        np.testing.assert_allclose(site.globalPosition(), A, atol=1e-12)
        np.testing.assert_allclose(site.approachGlobal(_pip()), A, atol=1e-12)
        np.testing.assert_allclose(site.positions['pip1']['interact global'], I, atol=1e-12)

    def test_rotation_points_local_down_from_approach_to_interact(self, make_site):
        import numpy as np
        site = make_site()
        A = np.array([0.0, 0.0, 5e-3])
        I = np.array([3e-3, 0.0, 1e-3])
        site.saveCalibration(_pip(), A, I)
        dist = np.linalg.norm(I - A)
        np.testing.assert_allclose(site.interactLocalFor(_pip()), [0, 0, -dist], atol=1e-9)

    def test_recalibrating_replaces_both_points_regardless_of_previous(self, make_site):
        import numpy as np
        site = make_site()
        site.saveCalibration(_pip(), np.array([0, 0, 5e-3]), np.array([1e-3, 0, 0]))
        A2 = np.array([4e-3, 4e-3, 6e-3])
        I2 = np.array([4e-3, 3e-3, 1e-3])
        site.saveCalibration(_pip(), A2, I2)
        np.testing.assert_allclose(site.approachGlobal(_pip()), A2, atol=1e-12)
        np.testing.assert_allclose(site.positions['pip1']['interact global'], I2, atol=1e-12)

    def test_calibration_is_written_to_config(self, make_site):
        import numpy as np
        site = make_site()
        site.saveCalibration(_pip(), np.array([0, 0, 5e-3]), np.array([0, 0, 0]))
        written = site.readConfigFile("saved_positions")
        assert 'interact global' in written['pip1']
        assert 'site global' in written['pip1']

    def test_second_pipette_is_refused(self, make_site):
        import numpy as np
        site = make_site()
        site.saveCalibration(_pip('pip1'), np.array([0, 0, 5e-3]), np.array([0, 0, 0]))
        with pytest.raises(RuntimeError):
            site.saveCalibration(_pip('pip2'), np.array([0, 0, 5e-3]), np.array([0, 0, 0]))

    def test_single_point_save_methods_are_gone(self, make_site):
        site = make_site()
        assert not hasattr(site, 'saveApproachPosition')
        assert not hasattr(site, 'saveInteractPosition')


class TestSiteCalibrationFlow:
    def test_steps_are_interact_then_approach(self, make_site, qt_app):
        from acq4.devices.InteractionSite import InteractionSiteCalibrationFlow
        flow = InteractionSiteCalibrationFlow(make_site(), _pip())
        assert [s[0] for s in flow._steps] == ['interact', 'approach']

    def test_no_step_can_be_skipped(self, make_site, qt_app):
        from acq4.devices.InteractionSite import InteractionSiteCalibrationFlow
        flow = InteractionSiteCalibrationFlow(make_site(), _pip())
        assert not hasattr(flow, '_keepBtn')

    def test_walking_both_steps_saves_both_points(self, make_site, qt_app):
        import numpy as np
        from acq4.util import Qt
        from acq4.devices.InteractionSite import InteractionSiteCalibrationFlow
        site = make_site()
        pip = _pip()
        flow = InteractionSiteCalibrationFlow(site, pip)
        results = []
        flow.finished.connect(results.append)
        I = np.array([1e-3, 0, 0])
        A = np.array([1e-3, 0, 5e-3])
        pip.globalPosition.return_value = I
        flow._useCurrent()
        assert 'pip1' not in site.positions  # nothing saved until both are captured
        pip.globalPosition.return_value = A
        flow._useCurrent()
        qt_app.processEvents()
        assert results == [Qt.QDialog.Accepted]
        np.testing.assert_allclose(site.approachGlobal(pip), A, atol=1e-12)
        np.testing.assert_allclose(site.positions['pip1']['interact global'], I, atol=1e-12)

    def test_cancel_after_first_step_saves_nothing(self, make_site, qt_app):
        from acq4.devices.InteractionSite import InteractionSiteCalibrationFlow
        site = make_site()
        flow = InteractionSiteCalibrationFlow(site, _pip())
        flow._useCurrent()
        flow.reject()
        assert 'pip1' not in site.positions


class TestDeviceGuiCalibration:
    def _gui(self, site):
        from acq4.devices.InteractionSite import InteractionSiteDeviceGui
        site.dm.listInterfaces.return_value = ['pip1']
        site.dm.getDevice.return_value = _pip()
        return InteractionSiteDeviceGui(site, MagicMock())

    def test_gui_offers_one_calibrate_button(self, make_site, qt_app):
        gui = self._gui(make_site())
        assert gui.calibrateBtn.isEnabled()
        assert not hasattr(gui, 'saveApproachBtn')
        assert not hasattr(gui, 'saveInteractBtn')

    def test_starting_calibration_opens_the_3d_viewer(self, make_site, qt_app):
        site = make_site()
        gui = self._gui(site)
        gui._startCalibration()
        site.dm.getOrLoadModule.assert_called_with("Visualize3D")
        gui._calibFlow.reject()

    def test_accepted_calibration_centers_viewer_on_site(self, make_site, qt_app):
        import numpy as np
        from acq4.util import Qt
        site = make_site()
        gui = self._gui(site)
        gui._startCalibration()
        site.saveCalibration(_pip(), np.array([2e-3, 0, 5e-3]), np.array([2e-3, 0, 0]))
        gui._onCalibrationFinished(Qt.QDialog.Accepted)
        window = site.dm.getOrLoadModule.return_value.window.return_value
        args, _ = window.centerOnPosition.call_args
        np.testing.assert_allclose(args[0], [2e-3, 0, 5e-3], atol=1e-12)
        window.focus.assert_called()
        assert gui._validatePrompt is not None
        gui._validatePrompt.close()

    def test_cancelled_calibration_does_not_prompt(self, make_site, qt_app):
        from acq4.util import Qt
        site = make_site()
        gui = self._gui(site)
        gui._startCalibration()
        site.dm.getOrLoadModule.reset_mock()
        gui._onCalibrationFinished(Qt.QDialog.Rejected)
        window = site.dm.getOrLoadModule.return_value.window.return_value
        window.centerOnPosition.assert_not_called()
        assert gui._validatePrompt is None
