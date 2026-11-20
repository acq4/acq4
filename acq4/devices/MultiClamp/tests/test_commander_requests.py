"""Which Commander windows the MultiClamp devices ask the driver to start: channelID parsing and
grouping of device channels by amplifier."""
from acq4.devices.MultiClamp.multiclamp import commanderRequests, serialFromChannelId

CHAN1 = 'model:MC700B,sn:00832774,chan:1'
CHAN2 = 'model:MC700B,sn:00832774,chan:2'
OTHER = 'model:MC700B,sn:00111111,chan:1'


def _cfg(channelId, **extra):
    return {'driver': 'MultiClamp', 'channelID': channelId, **extra}


def test_serial_from_channel_id():
    assert serialFromChannelId(CHAN1) == '00832774'
    assert serialFromChannelId('model:MC700A,com:3,dev:0,chan:1') is None
    assert serialFromChannelId('') is None


def test_channels_of_one_amplifier_share_a_titled_request():
    requests = commanderRequests({
        'Clamp1': _cfg(CHAN1, commanderPath='C:/mcc/MC700B.exe'),
        'Clamp2': _cfg(CHAN2),
        'Clamp3': _cfg(OTHER),
    })
    assert requests == {
        '00832774': {'title': 'Clamp1, Clamp2', 'path': 'C:/mcc/MC700B.exe'},
        '00111111': {'title': 'Clamp3', 'path': None},
    }


def test_first_configured_path_wins():
    requests = commanderRequests({'Clamp1': _cfg(CHAN1), 'Clamp2': _cfg(CHAN2, commanderPath='C:/mcc/MC700B.exe')})
    assert requests['00832774']['path'] == 'C:/mcc/MC700B.exe'


def test_ignores_other_devices_and_700a():
    requests = commanderRequests({
        'Old': _cfg('model:MC700A,com:3,dev:0,chan:1'),
        'DAQ': {'driver': 'NiDAQ'},
        'Nested': {'driver': 'MultiClamp', 'config': {'channelID': OTHER}},
    })
    assert requests == {'00111111': {'title': 'Nested', 'path': None}}
