# Tests for Pipette runtime site assignment: getSiteFor / setSiteFor.
# Verifies backward-compat config migration, duck-typed array delegation, and persistence.

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest


def _make_pipette(config=None, saved_sites=None, devices=None):
    """Create a minimal stub that exercises site-assignment code from the real Pipette class.

    Pipette inherits from Qt.QObject and requires full hardware init; this helper
    borrows just the methods under test (getSiteFor, setSiteFor, _loadSiteAssignments)
    onto a plain Python stub that provides the Device infrastructure they depend on.
    """
    import os
    from acq4.devices.Pipette.pipette import Pipette

    storage = {}
    if saved_sites:
        storage["devices/TestPip_config/saved_sites"] = saved_sites.copy()

    dm = MagicMock()
    dm.readConfigFile.side_effect = lambda path: storage.get(path, {})
    dm.writeConfigFile.side_effect = lambda data, path: storage.update({path: data.copy()})
    dm.getDevice.side_effect = lambda name: (devices or {}).get(name)

    base_config = {}
    if config:
        base_config.update(config)

    class _StubPipette:
        """Minimal Device-like infrastructure for site assignment unit tests."""

        def name(self_):
            return 'TestPip'

        def configPath(self_):
            return os.path.join('devices', f'{self_.name()}_config')

        def readConfigFile(self_, filename):
            return self_.dm.readConfigFile(os.path.join(self_.configPath(), filename))

        def writeConfigFile(self_, data, filename):
            self_.dm.writeConfigFile(data, os.path.join(self_.configPath(), filename))

    # Attach the actual Pipette methods under test.
    _StubPipette._loadSiteAssignments = Pipette._loadSiteAssignments
    _StubPipette.getSiteFor = Pipette.getSiteFor
    _StubPipette.setSiteFor = Pipette.setSiteFor
    _StubPipette.getCleaningWell = Pipette.getCleaningWell
    _StubPipette.getNucleusDepositionWell = Pipette.getNucleusDepositionWell
    _StubPipette.getElectrodeSolutionWell = Pipette.getElectrodeSolutionWell

    pip = _StubPipette()
    pip.dm = dm
    pip.config = base_config
    pip._site_assignments = {}
    pip._loadSiteAssignments()
    return pip, dm, storage


@pytest.fixture(scope="module")
def qt_app():
    from acq4.util import Qt
    app = Qt.QApplication.instance()
    if app is None:
        app = Qt.QApplication(sys.argv)
    return app


class TestGetSiteForDefaults:
    def test_returns_none_with_no_config_and_no_saved_state(self, qt_app):
        pip, _, _ = _make_pipette()
        assert pip.getSiteFor('clean') is None

    def test_returns_none_for_unknown_role(self, qt_app):
        pip, _, _ = _make_pipette()
        assert pip.getSiteFor('nucleus') is None


class TestBackwardCompatMigration:
    def test_cleaningWell_config_migrates_to_clean_role(self, qt_app):
        mock_well = MagicMock(spec=['name'])
        mock_well.name.return_value = 'CleaningWell1'
        pip, _, _ = _make_pipette(
            config={'cleaningWell': 'CleaningWell1'},
            devices={'CleaningWell1': mock_well},
        )
        assert pip.getSiteFor('clean') is mock_well

    def test_nucleusExpulsionWell_config_migrates_to_nucleus_role(self, qt_app):
        mock_well = MagicMock(spec=['name'])
        mock_well.name.return_value = 'NucleusWell1'
        pip, _, _ = _make_pipette(
            config={'nucleusExpulsionWell': 'NucleusWell1'},
            devices={'NucleusWell1': mock_well},
        )
        assert pip.getSiteFor('nucleus') is mock_well

    def test_electrodeSolutionWell_config_migrates_to_refill_role(self, qt_app):
        mock_well = MagicMock(spec=['name'])
        mock_well.name.return_value = 'ElecWell1'
        pip, _, _ = _make_pipette(
            config={'electrodeSolutionWell': 'ElecWell1'},
            devices={'ElecWell1': mock_well},
        )
        assert pip.getSiteFor('refill') is mock_well

    def test_saved_state_takes_precedence_over_config_migration(self, qt_app):
        runtime_well = MagicMock(spec=['name'])
        runtime_well.name.return_value = 'RuntimeWell'
        pip, _, _ = _make_pipette(
            config={'cleaningWell': 'OldWell'},
            saved_sites={'clean': 'RuntimeWell'},
            devices={'RuntimeWell': runtime_well},
        )
        assert pip.getSiteFor('clean') is runtime_well


class TestSetSiteFor:
    def test_set_then_get_returns_device(self, qt_app):
        mock_well = MagicMock(spec=['name'])
        mock_well.name.return_value = 'Well1'
        pip, dm, _ = _make_pipette(devices={'Well1': mock_well})
        pip.setSiteFor('clean', mock_well)
        assert pip.getSiteFor('clean') is mock_well

    def test_set_none_clears_assignment(self, qt_app):
        mock_well = MagicMock(spec=['name'])
        mock_well.name.return_value = 'Well1'
        pip, _, _ = _make_pipette(devices={'Well1': mock_well})
        pip.setSiteFor('clean', mock_well)
        pip.setSiteFor('clean', None)
        assert pip.getSiteFor('clean') is None

    def test_set_persists_to_config_file(self, qt_app):
        mock_well = MagicMock(spec=['name'])
        mock_well.name.return_value = 'Well1'
        pip, dm, storage = _make_pipette(devices={'Well1': mock_well})
        pip.setSiteFor('clean', mock_well)
        saved = storage.get('devices/TestPip_config/saved_sites', {})
        assert saved.get('clean') == 'Well1'

    def test_set_accepts_string_name(self, qt_app):
        mock_well = MagicMock(spec=['name'])
        mock_well.name.return_value = 'Well1'
        pip, _, _ = _make_pipette(devices={'Well1': mock_well})
        pip.setSiteFor('clean', 'Well1')
        assert pip.getSiteFor('clean') is mock_well


class TestArrayDelegation:
    def test_getSiteFor_calls_getFirstAvailableSite_on_array(self, qt_app):
        mock_site = MagicMock()
        mock_site.name.return_value = 'ActualSite'
        mock_array = MagicMock()
        mock_array.name.return_value = 'Array1'
        mock_array.getFirstAvailableSite.return_value = mock_site

        pip, _, _ = _make_pipette(devices={'Array1': mock_array})
        pip.setSiteFor('nucleus', mock_array)
        result = pip.getSiteFor('nucleus')

        mock_array.getFirstAvailableSite.assert_called_once_with('nucleus')
        assert result is mock_site

    def test_getSiteFor_returns_none_when_array_has_no_available_site(self, qt_app):
        mock_array = MagicMock()
        mock_array.name.return_value = 'Array1'
        mock_array.getFirstAvailableSite.return_value = None

        pip, _, _ = _make_pipette(devices={'Array1': mock_array})
        pip.setSiteFor('nucleus', mock_array)
        assert pip.getSiteFor('nucleus') is None


class TestRobustness:
    def test_getSiteFor_returns_none_when_device_name_no_longer_exists(self, qt_app):
        pip, _, _ = _make_pipette(saved_sites={'clean': 'GoneWell'})
        # dm.getDevice returns None for unknown names (no devices dict provided)
        assert pip.getSiteFor('clean') is None


class TestBackwardCompatAliases:
    def test_getCleaningWell_delegates_to_getSiteFor_clean(self, qt_app):
        mock_well = MagicMock(spec=['name'])
        mock_well.name.return_value = 'Well1'
        pip, _, _ = _make_pipette(devices={'Well1': mock_well})
        pip.setSiteFor('clean', mock_well)
        assert pip.getCleaningWell() is mock_well

    def test_getNucleusDepositionWell_delegates_to_getSiteFor_nucleus(self, qt_app):
        mock_well = MagicMock(spec=['name'])
        mock_well.name.return_value = 'Well1'
        pip, _, _ = _make_pipette(devices={'Well1': mock_well})
        pip.setSiteFor('nucleus', mock_well)
        assert pip.getNucleusDepositionWell() is mock_well

    def test_getElectrodeSolutionWell_delegates_to_getSiteFor_refill(self, qt_app):
        mock_well = MagicMock(spec=['name'])
        mock_well.name.return_value = 'Well1'
        pip, _, _ = _make_pipette(devices={'Well1': mock_well})
        pip.setSiteFor('refill', mock_well)
        assert pip.getElectrodeSolutionWell() is mock_well
