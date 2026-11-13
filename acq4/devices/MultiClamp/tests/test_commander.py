"""Automatic start of MultiClamp 700B Commander: channelID parsing, grouping of devices by
amplifier, executable discovery, and launch / wait behavior."""
import pytest

from acq4.devices.MultiClamp import commander

CHAN1 = 'model:MC700B,sn:00832774,chan:1'
CHAN2 = 'model:MC700B,sn:00832774,chan:2'
OTHER = 'model:MC700B,sn:00111111,chan:1'


def _cfg(channel_id, **extra):
    return {'driver': 'MultiClamp', 'channelID': channel_id, **extra}


def test_serial_from_channel_id():
    assert commander.serial_from_channel_id(CHAN1) == '00832774'
    assert commander.serial_from_channel_id('model:MC700A,com:3,dev:0,chan:1') is None
    assert commander.serial_from_channel_id('') is None


def test_build_command_pads_serial_and_sets_title():
    assert commander.build_command('MC700B.exe', '832774', 'A, B') == ['MC700B.exe', '/S00832774', '/TA, B']
    assert commander.build_command('MC700B.exe', '00832774', 'A')[1] == '/S00832774'


def test_targets_group_channels_by_serial_and_skip_others():
    targets = commander.commander_targets({
        'Clamp1': _cfg(CHAN1, commanderPath='C:/mcc/MC700B.exe'),
        'Clamp2': _cfg(CHAN2),
        'Clamp3': _cfg(OTHER),
        'Old': _cfg('model:MC700A,com:3,dev:0,chan:1'),
        'DAQ': {'driver': 'NiDAQ'},
        'Nested': {'driver': 'MultiClamp', 'config': {'channelID': OTHER}},
    })
    assert targets == {
        '00832774': {'names': ['Clamp1', 'Clamp2'], 'path': 'C:/mcc/MC700B.exe'},
        '00111111': {'names': ['Clamp3', 'Nested'], 'path': None},
    }


def test_find_commander_prefers_configured_path(tmp_path):
    exe = tmp_path / 'MC700B.exe'
    exe.write_text('')
    assert commander.find_commander(str(exe)) == str(exe)
    with pytest.raises(FileNotFoundError, match='commanderPath'):
        commander.find_commander(str(tmp_path / 'missing.exe'))


def test_find_commander_searches_standard_locations(tmp_path, monkeypatch):
    for var in commander.PROGRAM_FILES_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('ProgramFiles', str(tmp_path))
    with pytest.raises(FileNotFoundError, match='MC700B.exe was not found'):
        commander.find_commander()

    exe = tmp_path / commander.COMMANDER_LOCATIONS[1]
    exe.parent.mkdir(parents=True)
    exe.write_text('')
    assert commander.find_commander() == str(exe)


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
    """List of FakeProc for every Commander launch; time is fake and advances 1s per call."""
    procs = []

    def popen(cmd, **kw):
        procs.append(FakeProc(cmd))
        return procs[-1]

    clock = [0.0]
    monkeypatch.setattr(commander.subprocess, 'Popen', popen)
    monkeypatch.setattr(commander, 'find_commander', lambda path=None: path or 'C:/mcc/MC700B.exe')
    monkeypatch.setattr(commander.time, 'sleep', lambda s: clock.__setitem__(0, clock[0] + s))
    monkeypatch.setattr(commander.time, 'monotonic', lambda: clock[0])
    return procs


def test_starts_one_commander_per_missing_amplifier(launched):
    configs = {'Clamp1': _cfg(CHAN1), 'Clamp2': _cfg(CHAN2), 'Clamp3': _cfg(OTHER)}
    # A Commander "appears" as soon as it has been launched.
    commander.start_commanders(configs, lambda: [p.cmd[1][2:] for p in launched])

    assert sorted(p.cmd for p in launched) == [
        ['C:/mcc/MC700B.exe', '/S00111111', '/TClamp3'],
        ['C:/mcc/MC700B.exe', '/S00832774', '/TClamp1, Clamp2'],
    ]
    assert not any(p.killed for p in launched)


def test_does_not_start_running_amplifier(launched):
    # Commander may report the serial with or without leading zeros.
    commander.start_commanders({'Clamp1': _cfg(CHAN1)}, lambda: ['832774'])
    assert launched == []


def test_kills_and_restarts_commander_that_never_finds_amplifier(launched):
    # The first Commander gets stuck at its Select Device dialog; the second one works.
    commander.start_commanders({'Clamp1': _cfg(CHAN1)}, lambda: ['00832774'] if len(launched) == 2 else [])

    assert len(launched) == 2
    assert [p.killed for p in launched] == [True, False]
    assert launched[0].cmd == launched[1].cmd


def test_gives_up_after_all_attempts(launched):
    with pytest.raises(TimeoutError, match='00832774'):
        commander.start_commanders({'Clamp1': _cfg(CHAN1)}, lambda: [], attempts=3)
    assert len(launched) == 3
    assert all(p.killed for p in launched)


def test_only_restarts_the_amplifier_that_is_missing(launched):
    configs = {'Clamp1': _cfg(CHAN1), 'Clamp3': _cfg(OTHER)}

    def running():
        # 00111111 starts at once; 00832774 only on its second launch.
        serials = [p.cmd[1][2:] for p in launched if p.cmd[1] == '/S00111111']
        if sum(p.cmd[1] == '/S00832774' for p in launched) >= 2:
            serials.append('00832774')
        return serials

    commander.start_commanders(configs, running)

    assert [(p.cmd[1], p.killed) for p in launched] == [
        ('/S00832774', True), ('/S00111111', False), ('/S00832774', False),
    ]
