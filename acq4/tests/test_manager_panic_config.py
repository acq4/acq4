"""How the ``panicHotkey`` option is read, and what happens to one that is not.

Covers the two ways the config can leave the rig with no panic trigger while the
operator's file says otherwise -- the option arriving after the devices it is
supposed to cover, and a misspelling nothing reports -- plus what the operator is
told about which triggers are live.
"""

from __future__ import annotations

import pytest

from acq4.Manager import CONFIG_KEYS_READ_ELSEWHERE, Manager
from acq4.panic import GlobalHalt


class _RecordingManager:
    """The slice of Manager that ``_loadConfig`` touches, with the order recorded.

    Manager.__init__ builds a whole application -- singleton guard, log window,
    devices -- so bypass it and populate only what the config chain reads, the way
    tests/test_manager_modules.py does.
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
    """Device construction takes physical action; it must not happen unguarded.

    Several devices move hardware as they are built -- a light source's
    initialState switches a lamp on, a microscope's initialPreset drives the
    objective turret -- and the Esc QShortcut does not exist until showGUI(),
    after the whole config has been read. If the panic key is armed in key order
    it lands after every device in the shipped example layout, where it sits
    under ``misc:``.
    """

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
        """``misc:`` is where the example config invites new options, and it is
        declared after ``devices:`` there."""
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
        """These are valid; something other than _loadConfig reads them."""
        man._loadConfig({key: {}})

        assert not [r for r in caplog.records if key in r.message], \
            f"{key} is read elsewhere but was reported as unknown"

    def test_a_handled_option_does_not_warn(self, man, caplog):
        man._loadConfig({'devices': devicesConfig('Lamp'), 'panicHotkey': False})

        assert caplog.records == []


class TestStartingTheHotkey:
    """_startPanicHotkey's own contract: a bad option must not take startup down.

    It is off by default and fires wherever the key is pressed, so there is no
    value in which a problem with it is worth aborting the whole configuration
    for -- which is what raising would do under ``exitOnError``.
    """

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
        """ctypes.WinDLL('user32') raises OSError, not ValueError."""
        def unreachable(*args, **kwds):
            raise OSError("could not load user32")

        monkeypatch.setattr('acq4.Manager.GlobalPanicHotkey', unreachable)

        bareMan._startPanicHotkey('Ctrl+Alt+Esc')

        assert bareMan.panicHotkey is None
        assert any('panic key disabled' in record.message for record in caplog.records)

    def test_reconfiguring_stops_the_key_already_running(self, bareMan):
        """stop() is one-way, so a new binding means a new object and the old one
        has to be told to go."""
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
