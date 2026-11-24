import importlib

import pytest


class FakeSocket:
    def __init__(self):
        self.commands = []

    def connect(self, address):
        pass

    def settimeout(self, timeout):
        pass

    def sendall(self, command):
        self.commands.append(command)

    def recv(self, size):
        return b'<OK>\r'

    def close(self):
        pass


@pytest.fixture
def driver(monkeypatch):
    module = importlib.import_module('acq4.drivers.NewScale.NewScaleMPM')
    connection = FakeSocket()
    monkeypatch.setattr(module.socket, 'socket', lambda *args, **kwargs: connection)
    driver = module.NewScaleMPM('127.0.0.1')
    connection.commands.clear()
    yield driver
    driver.close()


@pytest.mark.parametrize(
    'mode, interval, expected',
    [
        ('closed', None, b'<20 1 >\r'),
        ('open', 0, b'<20 0 0000>\r'),
        ('query', 42, b'<20 R 002a>\r'),
        ('closed', 0xABCD, b'<20 1 abcd>\r'),
    ],
)
def test_drive_mode_interval(driver, mode, interval, expected):
    driver.setOrQueryDriveMode(mode, interval=interval)
    assert driver.sock.commands == [expected]


@pytest.mark.parametrize(
    'direction, incremental, automatic, offset, expected',
    [
        ('forward', False, True, None, b'<87 5 >\r'),
        ('backward', True, False, None, b'<87 2 >\r'),
        ('forward', True, True, 10, b'<87 7 0a>\r'),
        ('backward', False, False, 0, b'<87 0 00>\r'),
    ],
)
def test_frequency_calibration_offset(driver, direction, incremental, automatic, offset, expected):
    driver.runFrequencyCalibration(
        direction, incremental=incremental, automatic=automatic, frequncy_offset=offset
    )
    assert driver.sock.commands == [expected]
