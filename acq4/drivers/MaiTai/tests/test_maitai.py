import pytest

pytest.importorskip("serial")

from acq4.drivers.MaiTai import maitai
from acq4.drivers.MaiTai.maitai import MaiTai, MaiTaiError


class FakeSerial:
    """Responds to Mai Tai queries from a dict; records every command written."""

    def __init__(self, responses, **kwds):
        self.responses = responses
        self.written = []
        self._out = b''

    def write(self, data):
        cmd = data.decode().rstrip('\r')
        self.written.append(cmd)
        if cmd.endswith('?'):
            self._out += self.responses[cmd].encode() + b'\n'

    def inWaiting(self):
        return len(self._out)

    def read(self, n):
        data, self._out = self._out[:n], self._out[n:]
        return data

    def close(self):
        pass


@pytest.fixture
def laser(monkeypatch):
    responses = {
        'READ:WAVelength?': '800nm',
        'WAVelength:MIN?': '690nm',
        'WAVelength:MAX?': '1040nm',
        'READ:POWer?': '1.25W',
        '*STB?': '3',
        'MODE?': 'PPOW',
        'SHUTter?': '0',
        'READ:AHISTory?': '431 405',
        'PLASer:AHISTory?': '999',
        'READ:PDITher?': '443',
        'READ:HUM?': '2.5%',
        'BAD?': 'Error: bad command',
    }
    monkeypatch.setattr(maitai.serial, 'Serial', lambda **kwds: FakeSerial(responses, **kwds))
    return MaiTai('/dev/fake')


def test_queries(laser):
    assert laser.getWavelength() == 800.0
    assert laser.getWavelengthRange() == (690.0, 1040.0)
    assert laser.getPower() == 1.25
    assert laser.getRelativeHumidity() == 2.5
    assert laser.isLaserOn() and laser.isPulsing()
    assert laser.getPumpMode() == 'Green Power'
    assert laser.getShutter() is False
    assert laser.getStatus() == 'wavelength is stable, all motors stopped'
    assert laser.getPumpLaserStatus() == 'Unknown pump laser status code 999'
    assert laser.getP2Status() is True


def test_commands(laser):
    laser.setWavelength(920)
    laser.setPumpMode('IR Power')
    assert laser.serial.written[-1] == 'MODE POW'
    assert 'WAVelength 920' in laser.serial.written


def test_errors(laser):
    with pytest.raises(ValueError):
        laser.setWavelength(1200)
    with pytest.raises(MaiTaiError):
        laser.query('BAD?')
    with pytest.raises(MaiTaiError):
        laser.setShutter(True)  # fake shutter never opens
