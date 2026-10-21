"""Tests for how Manager._loadConfig handles ``panicHotkey`` and unknown options.

Checks that the hotkey is armed before devices are built, that unknown keys log a
warning, and what Manager.panicKeyStatus reports.
"""

from __future__ import annotations

import pytest

from acq4.Manager import CONFIG_KEYS_READ_ELSEWHERE, Manager
from acq4.panic import GlobalHalt


class _RecordingManager:
    """The Manager attributes that ``_loadConfig`` uses, recording call order.

    Stands in for Manager.__init__, which builds the whole application.
    """

    def __init__(self):
        self.events = []
        self.exitOnError = False
        self.disableAllDevs = False
        self.disableDevs = []
        self.definedModules = {}
        self.globalHalt = GlobalHalt()
        self.panicHotkey = None

    def loadDevice(self, driverName, conf, name):
        self.events.append(('device', name))

    def _startPanicHotkey(self, spec):
        self.events.append(('panicHotkey', spec))


@pytest.fixture
def man():
    man = Manager.__new__(Manager)
    recorder = _RecordingManager()
    for attr, value in vars(recorder).items():
        setattr(man, attr, value)
    man.loadDevice = recorder.loadDevice
    man._startPanicHotkey = recorder._startPanicHotkey
    man.events = recorder.events
    return man


def devicesConfig(*names):
    return {name: {'driver': 'MockLightSource'} for name in names}


class TestThePanicKeyIsArmedBeforeAnyDevice:
    """``panicHotkey`` is armed before any device is constructed, wherever it appears."""

    def test_a_top_level_option_after_devices_is_still_armed_first(self, man):
        man._loadConfig({
            'devices': devicesConfig('Lamp', 'Scope'),
            'panicHotkey': 'Ctrl+Alt+Esc',
        })

        assert man.events[0] == ('panicHotkey', 'Ctrl+Alt+Esc')
        assert [e for e in man.events if e[0] == 'device'] == [
            ('device', 'Lamp'), ('device', 'Scope')]

    def test_the_option_is_armed_exactly_once(self, man):
        man._loadConfig({'panicHotkey': True, 'devices': devicesConfig('Lamp')})

        assert [e for e in man.events if e[0] == 'panicHotkey'] == [('panicHotkey', True)]

    def test_the_option_nested_under_misc_is_armed_before_top_level_devices(self, man):
        """A ``panicHotkey`` under ``misc:``, declared after ``devices:``, is armed first."""
        man._loadConfig({
            'devices': devicesConfig('Lamp'),
            'misc': {'panicHotkey': 'Ctrl+Alt+Esc'},
        })

        armed = [i for i, e in enumerate(man.events) if e[0] == 'panicHotkey']
        built = [i for i, e in enumerate(man.events) if e[0] == 'device']
        assert armed, "panicHotkey under misc: never reached _startPanicHotkey"
        assert min(armed) < min(built), "devices were built before the panic key was armed"


class TestAnUnknownOptionIsReported:
    def test_a_misspelled_panic_option_warns(self, man, caplog):
        man._loadConfig({'panicHotKey': 'Ctrl+Alt+Esc'})

        assert man.events == [], "a misspelling must not arm anything"
        assert any('panicHotKey' in r.message for r in caplog.records), \
            "a misspelled option was accepted in silence"

    def test_an_option_nobody_reads_warns(self, man, caplog):
        man._loadConfig({'storgeDir': '/tmp/data'})

        assert any('storgeDir' in r.message for r in caplog.records)

    @pytest.mark.parametrize('key', sorted(CONFIG_KEYS_READ_ELSEWHERE - {'imports'}))
    def test_an_option_read_elsewhere_does_not_warn(self, man, caplog, key):
        """Keys in CONFIG_KEYS_READ_ELSEWHERE do not log an unknown-option warning."""
        man._loadConfig({key: {}})

        assert not [r for r in caplog.records if key in r.message], \
            f"{key} is read elsewhere but was reported as unknown"

    def test_a_handled_option_does_not_warn(self, man, caplog):
        man._loadConfig({'devices': devicesConfig('Lamp'), 'panicHotkey': False})

        assert caplog.records == []


class TestStartingTheHotkey:
    """Manager._startPanicHotkey logs a bad ``panicHotkey`` value instead of raising."""

    @pytest.fixture
    def bareMan(self):
        man = Manager.__new__(Manager)
        man.globalHalt = GlobalHalt()
        man.panicHotkey = None
        return man

    def test_a_spec_that_will_not_parse_is_logged_and_leaves_the_key_off(
        self, bareMan, caplog
    ):
        bareMan._startPanicHotkey('Hyper+Esc')

        assert bareMan.panicHotkey is None
        assert any('panicHotkey' in record.message for record in caplog.records)

    def test_an_oserror_reaching_the_keyboard_api_is_caught_too(
        self, bareMan, caplog, monkeypatch
    ):
        """An OSError from GlobalPanicHotkey (ctypes failing to load user32) is logged."""
        def unreachable(*args, **kwds):
            raise OSError("could not load user32")

        monkeypatch.setattr('acq4.Manager.GlobalPanicHotkey', unreachable)

        bareMan._startPanicHotkey('Ctrl+Alt+Esc')

        assert bareMan.panicHotkey is None
        assert any('panic key disabled' in record.message for record in caplog.records)

    def test_reconfiguring_stops_the_key_already_running(self, bareMan):
        """Reconfiguring calls stop() on the previously running GlobalPanicHotkey."""
        stopped = []

        class _Running:
            spec = 'Esc'

            def stop(self):
                stopped.append(True)

        bareMan.panicHotkey = _Running()

        bareMan._startPanicHotkey(False)

        assert stopped == [True], "the previous panic key was left polling"
        assert bareMan.panicHotkey is None


class TestWhatTheOperatorIsTold:
    def test_an_unarmed_key_says_focus_is_required(self, man):
        man.panicHotkey = None

        status = man.panicKeyStatus()

        assert 'Esc' in status
        assert 'focus' in status

    def test_an_armed_key_names_the_binding(self, man):
        class _Armed:
            spec = 'Ctrl+Alt+Esc'

        man.panicHotkey = _Armed()

        status = man.panicKeyStatus()

        assert 'Ctrl+Alt+Esc' in status
        assert 'anywhere' in status

    def test_a_bare_true_binding_is_reported_as_the_key_it_means(self):
        from acq4.panic import GlobalPanicHotkey

        assert GlobalPanicHotkey(GlobalHalt(), True, keyReader=lambda vk: 0).spec == 'Esc'
