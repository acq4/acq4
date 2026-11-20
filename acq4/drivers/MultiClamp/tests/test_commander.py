"""Automatic start of MultiClamp 700B Commander: executable discovery, command line, and
launch / kill-and-retry behavior."""
import sys

import pytest

if sys.platform != 'win32':
    pytest.skip("MultiClamp driver is Windows-only", allow_module_level=True)

from acq4.drivers.MultiClamp import commander

SERIAL = '00832774'
OTHER = '00111111'


def _req(title, path=None):
    return {'title': title, 'path': path}


def test_build_command_pads_serial_and_sets_title():
    assert commander.buildCommand('MC700B.exe', '832774', 'A, B') == ['MC700B.exe', '/S00832774', '/TA, B']
    assert commander.buildCommand('MC700B.exe', SERIAL, 'A')[1] == '/S00832774'


def test_find_commander_prefers_configured_path(tmp_path):
    exe = tmp_path / 'MC700B.exe'
    exe.write_text('')
    assert commander.findCommander(str(exe)) == str(exe)
    with pytest.raises(FileNotFoundError, match='Configured'):
        commander.findCommander(str(tmp_path / 'missing.exe'))


def test_find_commander_searches_standard_locations(tmp_path, monkeypatch):
    for var in commander.PROGRAM_FILES_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('ProgramFiles', str(tmp_path))
    with pytest.raises(FileNotFoundError, match='MC700B.exe was not found'):
        commander.findCommander()

    exe = tmp_path / commander.COMMANDER_LOCATIONS[1]
    exe.parent.mkdir(parents=True)
    exe.write_text('')
    assert commander.findCommander() == str(exe)


class FakeProc:
    def __init__(self, cmd):
        self.cmd = cmd
        self.killed = False

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        pass


@pytest.fixture
def launched(monkeypatch):
    """List of FakeProc for every Commander launch; time is fake and only advances in sleep()."""
    procs = []

    def popen(cmd, **kw):
        procs.append(FakeProc(cmd))
        return procs[-1]

    clock = [0.0]
    monkeypatch.setattr(commander.subprocess, 'Popen', popen)
    monkeypatch.setattr(commander, 'findCommander', lambda path=None: path or 'C:/mcc/MC700B.exe')
    monkeypatch.setattr(commander.time, 'sleep', lambda s: clock.__setitem__(0, clock[0] + s))
    monkeypatch.setattr(commander.time, 'monotonic', lambda: clock[0])
    return procs


def test_starts_one_commander_per_missing_amplifier(launched):
    requests = {SERIAL: _req('Clamp1, Clamp2'), OTHER: _req('Clamp3')}
    # A Commander "appears" as soon as it has been launched.
    commander.startCommanders(requests, lambda: [p.cmd[1][2:] for p in launched])

    assert sorted(p.cmd for p in launched) == [
        ['C:/mcc/MC700B.exe', '/S00111111', '/TClamp3'],
        ['C:/mcc/MC700B.exe', '/S00832774', '/TClamp1, Clamp2'],
    ]
    assert not any(p.killed for p in launched)


def test_uses_configured_path(launched):
    commander.startCommanders({SERIAL: _req('Clamp1', 'D:/mcc/MC700B.exe')}, lambda: [p.cmd[1][2:] for p in launched])
    assert launched[0].cmd[0] == 'D:/mcc/MC700B.exe'


def test_does_not_start_running_amplifier(launched):
    # Commander may report the serial with or without leading zeros.
    commander.startCommanders({SERIAL: _req('Clamp1')}, lambda: ['832774'])
    assert launched == []


def test_nothing_requested_does_nothing(launched):
    commander.startCommanders({}, lambda: pytest.fail("should not enumerate amplifiers"))
    assert launched == []


def test_kills_and_restarts_commander_that_never_finds_amplifier(launched):
    # The first Commander gets stuck at its Select Device dialog; the second one works.
    commander.startCommanders({SERIAL: _req('Clamp1')}, lambda: [SERIAL] if len(launched) == 2 else [])

    assert len(launched) == 2
    assert [p.killed for p in launched] == [True, False]
    assert launched[0].cmd == launched[1].cmd


def test_gives_up_after_all_attempts(launched):
    with pytest.raises(TimeoutError, match=SERIAL):
        commander.startCommanders({SERIAL: _req('Clamp1')}, lambda: [], attempts=3)
    assert len(launched) == 3
    assert all(p.killed for p in launched)


def test_only_restarts_the_amplifier_that_is_missing(launched):
    requests = {SERIAL: _req('Clamp1'), OTHER: _req('Clamp3')}

    def running():
        # OTHER starts at once; SERIAL only on its second launch.
        serials = [OTHER] if any(p.cmd[1] == '/S' + OTHER for p in launched) else []
        if sum(p.cmd[1] == '/S' + SERIAL for p in launched) >= 2:
            serials.append(SERIAL)
        return serials

    commander.startCommanders(requests, running)

    assert [(p.cmd[1], p.killed) for p in launched] == [
        ('/S' + SERIAL, True), ('/S' + OTHER, False), ('/S' + SERIAL, False),
    ]
