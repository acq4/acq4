"""RS-485-4W configuration against an in-memory stand-in for winreg.

The registry is a nested dict of key name -> node; ``_values`` holds a node's values and
``_denied`` marks a key a standard user cannot read, as parts of the Enum tree are.
"""
import sys

import pytest

from acq4.drivers.pmdmotion import serial_ports
from acq4.drivers.pmdmotion.protocol import CommunicationError
from acq4.drivers.pmdmotion.serial_ports import RS485_4W, device_instance_id, ensure_rs485_4w, set_rs485_4w

ENUM = serial_ports.ENUM_PATH


def params(port, **values):
    return {'Device Parameters': {'_values': {'PortName': port, **values}}}


def tree(**enumerators):
    node = {'SYSTEM': {'CurrentControlSet': {'Enum': enumerators}}}
    return node


class FakeKey:
    def __init__(self, reg, path, node):
        self.reg, self.path, self.node = reg, path, node

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.reg.closed.append(self.path)
        return False

    def __repr__(self):
        return f'<FakeKey {self.path}>'


class FakeWinreg:
    """Enough of winreg to drive :func:`device_instance_id` and :func:`set_rs485_4w`."""

    HKEY_LOCAL_MACHINE = 'HKLM'
    KEY_READ = 0x20019

    def __init__(self, root):
        self.root = root
        self.closed = []

    def _node(self, key, sub):
        node = self.root if key == self.HKEY_LOCAL_MACHINE else key.node
        path = '' if key == self.HKEY_LOCAL_MACHINE else key.path
        for part in sub.split('\\'):
            if part not in node:
                raise FileNotFoundError(2, 'The system cannot find the file specified', sub)
            node = node[part]
            path = f'{path}\\{part}' if path else part
            if node.get('_denied'):
                raise PermissionError(5, 'Access is denied', path)
        return path, node

    def OpenKey(self, key, sub, reserved=0, access=0):
        return FakeKey(self, *self._node(key, sub))

    def EnumKey(self, key, index):
        names = [n for n in key.node if not n.startswith('_')]
        if index >= len(names):
            raise OSError(22, 'No more data is available')
        return names[index]

    def QueryValueEx(self, key, name):
        values = key.node.get('_values', {})
        if name not in values:
            raise FileNotFoundError(2, 'The system cannot find the file specified', name)
        return values[name], 4


@pytest.fixture
def elevated(monkeypatch):
    """Record elevated ``reg`` invocations; ``writes`` makes one apply to the tree."""
    state = {'calls': [], 'writes': None}

    def check_call(args):
        state['calls'].append(args)
        if state['writes'] is not None:
            state['writes']()

    monkeypatch.setattr(serial_ports.subprocess, 'check_call', check_call)
    return state


# ---- finding the device instance ----

def test_device_instance_id_finds_the_device_serving_the_port():
    reg = FakeWinreg(tree(
        PCI={'VEN_8086': {'3&11583659&0&FA': {}}},
        USB={
            'VID_0403&PID_6010&MI_00': {'6&1d2b3c4d&0&0000': params('COM3')},
            'VID_0403&PID_6010&MI_01': {'6&1d2b3c4d&0&0001': params('COM4')},
        },
    ))
    assert device_instance_id(reg, 'COM4') == 'USB\\VID_0403&PID_6010&MI_01\\6&1d2b3c4d&0&0001'
    assert device_instance_id(reg, 'COM3') == 'USB\\VID_0403&PID_6010&MI_00\\6&1d2b3c4d&0&0000'
    assert device_instance_id(reg, 'COM9') is None
    assert reg.closed  # every key opened during the walk is closed again


def test_device_instance_id_walks_past_keys_it_cannot_read():
    reg = FakeWinreg(tree(
        HID={'_denied': True, 'VID_045E': {}},
        SWD={'PRINTENUM': {'_denied': True}},
        USB={'VID_110A&PID_1250': {'5&2f1a&0&1': params('COM7')}},
    ))
    assert device_instance_id(reg, 'COM7') == 'USB\\VID_110A&PID_1250\\5&2f1a&0&1'


def test_device_instance_id_ignores_devices_with_no_port_name():
    reg = FakeWinreg(tree(USB={
        'VID_0403&PID_6010': {'A': {'Device Parameters': {'_values': {'SerInterface': 0}}},
                              'B': {},
                              'C': params('COM5')},
    }))
    assert device_instance_id(reg, 'COM5') == 'USB\\VID_0403&PID_6010\\C'


# ---- setting the interface ----

def _moxa(port, ser_interface):
    values = {} if ser_interface is None else {'SerInterface': ser_interface}
    return FakeWinreg(tree(USB={'VID_110A&PID_1250': {'5&2f1a&0&1': params(port, **values)}}))


def test_already_4w_changes_nothing(elevated):
    set_rs485_4w(_moxa('COM7', RS485_4W), 'COM7')
    assert elevated['calls'] == []


def test_2w_is_raised_to_4w_elevated(elevated):
    reg = _moxa('COM7', 0)
    node = reg.root['SYSTEM']['CurrentControlSet']['Enum']['USB']['VID_110A&PID_1250']['5&2f1a&0&1']
    elevated['writes'] = lambda: node['Device Parameters']['_values'].update(SerInterface=RS485_4W)
    set_rs485_4w(reg, 'COM7')
    assert len(elevated['calls']) == 1
    command = ' '.join(elevated['calls'][0])
    assert f'{ENUM}\\USB\\VID_110A&PID_1250\\5&2f1a&0&1\\Device Parameters' in command
    assert f'/d {RS485_4W}' in command and 'RunAs' in command and '-Wait' in command


def test_an_elevated_write_that_did_not_take_is_an_error(elevated):
    # the UAC prompt can be declined, or the value can be written somewhere that has no effect
    with pytest.raises(CommunicationError, match='still 0'):
        set_rs485_4w(_moxa('COM7', 0), 'COM7')
    assert len(elevated['calls']) == 1


def test_a_port_with_no_registry_entry_is_an_error(elevated):
    # pyserial reports a USB port's hwid as 'USB VID:PID=...', which is no registry path;
    # building one from it silently found nothing at all
    with pytest.raises(CommunicationError, match='COM9'):
        set_rs485_4w(_moxa('COM7', 0), 'COM9')
    assert elevated['calls'] == []


def test_a_driver_without_a_serinterface_setting_is_an_error(elevated):
    with pytest.raises(CommunicationError, match='no SerInterface'):
        set_rs485_4w(_moxa('COM7', None), 'COM7')
    assert elevated['calls'] == []


def test_ensure_rs485_4w_is_a_noop_off_windows(monkeypatch, elevated):
    monkeypatch.setattr(serial_ports.sys, 'platform', 'linux')
    ensure_rs485_4w('COM7')
    assert elevated['calls'] == []


@pytest.mark.skipif(sys.platform == 'win32', reason='winreg is importable on Windows')
def test_ensure_rs485_4w_on_windows_needs_winreg(monkeypatch):
    monkeypatch.setattr(serial_ports.sys, 'platform', 'win32')
    with pytest.raises(ModuleNotFoundError):
        ensure_rs485_4w('COM7')
