# Tests for InteractionSite role/used_up tracking and array-child UI suppression.
# Uses a real InteractionSite with a mock DeviceManager to avoid hardware dependencies.

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest


def _make_dm(saved_positions=None):
    """Create a mock device manager that simulates per-device config file storage."""
    storage = {}
    if saved_positions:
        # store under the canonical path prefix matching configPath()
        storage["devices/TestSite_config/saved_positions"] = saved_positions.copy()

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
