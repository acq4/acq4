from __future__ import annotations

import ctypes
from ctypes import (
    byref,
    c_ubyte,
    c_ulong,
    CFUNCTYPE,
    c_uint32,
    POINTER,
    c_uint16,
    c_int64,
)
from ctypes.util import find_library
from time import sleep
from typing import Union, Iterable

from ... import getManager

# TODO: relay to <jhentges@accesio.com> when this is done
__all__ = ["UsbDIO96", "AccesError", "DEFAULT_SINGLE_DEVICE_ID"]
ADCCallbackType = CFUNCTYPE(c_uint32, POINTER(c_uint16), c_uint32, c_uint32, c_uint32)
DEFAULT_SINGLE_DEVICE_ID = -3
RETCODE_ERROR_DOCS = \
    "https://accesio.com/MANUALS/USB%20Software%20Reference%20Manual.html#About%20Error/Status%20Return%20Values"


class AccesError(Exception):
    pass


class UsbDIO96:
    """
    Wraps device using driver dll found at https://accesio.com/files/packages/USB-DIO-96%20Install.exe

    See https://accesio.com/MANUALS/USB%20Software%20Reference%20Manual.html for a detailed account of the
    functions herein wrapped.

    Usage::
    dev = UsbDIO96()
    print(f"Connected to DIO96 device with serial number 0x{dev.get_serial_number():x}")
    dev.configure(UsbDIO96.OUTPUT, [0, 1, 2])
    dev.write(0, 0xff)
    val = dev.read(11)
    """

    INPUT = 1
    OUTPUT = 0
    _lib_path = None
    _lib = None

    @classmethod
    def set_library_path(cls, path: str) -> None:
        cls._lib_path = path

    @classmethod
    def get_library(cls):
        if cls._lib is None:
            if cls._lib_path is None:
                cls._lib_path = find_library("AIOUSB")
            if cls._lib_path is None:
                cls._lib_path = "AIOUSB.dll"
            cls._lib = ctypes.windll.LoadLibrary(cls._lib_path)
        return cls._lib

    @classmethod
    def get_device_ids(cls) -> list[int]:
        bitmask = cls.get_library().GetDevices()
        ids = [i for i in range(32) if (1 << i) & bitmask]
        if len(ids) == 1:
            return [DEFAULT_SINGLE_DEVICE_ID]
        return ids

    def __init__(self, dev_id: int = DEFAULT_SINGLE_DEVICE_ID) -> None:
        if self._lib is None:
            self.get_library()
        self._id = dev_id
        self._chan_mask = (c_ubyte * 2)(0)  # bit mask of which ports are configured as OUTPUT
        self._port_io = (c_ubyte * 12)(0)  # data written to the ports whenever they're configured as OUTPUT

    def __str__(self) -> str:
        return f"<UsbDIO96 device {self._id}>"

    def call(self, fn_name: str, *args) -> None:
        fn = getattr(self._lib, fn_name)
        status = fn(self._id, *args)
        if status != 0:
            raise AccesError(
                f"Acces function call '{fn_name}({args})' returned error code {status}. See {RETCODE_ERROR_DOCS}"
                f" for details."
            )

    def get_serial_number(self) -> int:
        sn = c_int64(0)
        self.call("GetDeviceSerialNumber", byref(sn))
        return sn.value & 0xffff_ffff_ffff_ffff

    def configure_channels(self, in_or_out: Union[INPUT, OUTPUT], channels: Iterable[int]) -> None:
        """
        Set the specified channels to either INPUT or OUTPUT mode. Note: all channels are INPUT by default. An initial
        value of 0x01 will be written when in OUTPUT mode.
        """
        for ch in channels:
            ch_bit = 1 << ch
            if in_or_out == UsbDIO96.OUTPUT:
                self._chan_mask[0] |= (ch_bit & 0xff)
                self._chan_mask[1] |= ((ch_bit >> 8) & 0xf)
                self._port_io[ch] = 0x01
            else:
                self._chan_mask[0] &= (~ch_bit & 0xff)
                self._chan_mask[1] &= ((~ch_bit >> 8) & 0xf)
                self._port_io[ch] = 0x00

        self.call("DIO_Configure", True, self._chan_mask, self._port_io)

    def write(self, port: int, data: int):
        """
        Write to a single byte-worth of digital outputs on a device.

        Bytes written to any ports configured as “input” are ignored.
        """
        return self.call("DIO_Write8", c_ulong(port), c_ubyte(data))

    def read(self, port: int):
        """Read all digital bits on a device, including read-back of ports configured as “output”."""
        data_buff = c_ubyte(0)
        self.call("DIO_Read8", c_ulong(port), byref(data_buff))
        return data_buff.value & 0xff


def handle_config(params):
    UsbDIO96.set_library_path(params.get("usbDio96DriverPath"))


if __name__ == "__main__":
    device_ids = UsbDIO96.get_device_ids()
    devices = [UsbDIO96(i) for i in device_ids]
    print(f"{len(devices)} Acces USB DIO96 device{'s' if len(devices) != 1 else ''} found. Serial numbers:")
    for d in devices:
        print(*list(f"{d.get_serial_number():x}"))

    output_ports = [0, 1, 2, 3, 4, 5, 6, 7]
    for d in devices:
        d.configure_channels(UsbDIO96.OUTPUT, output_ports)
        for i in output_ports:
            d.write(i, 0)
    sleep(5)

    for d in devices:
        for i in output_ports:
            print(f"Turning on port {i} of {d} for 1 second.")
            d.write(i, 1)
            sleep(1)
            d.write(i, 0)
        d.write(0, 1)

else:
    handle_config(getManager().config.get("drivers", {}).get("acces", {}))
