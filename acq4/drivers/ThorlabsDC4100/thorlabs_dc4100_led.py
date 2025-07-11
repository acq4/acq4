import threading
import time

import serial.tools.list_ports

from ..SerialDevice import SerialDevice

COMMANDS = {
    "set_brightness": "BP {} {}",
    "get_brightness": "BP? {}",
    "get_wavelength": "WL? {}",
    "set_led_channel_state": "O {} {}",
    "led_on": "O {} 1",
    "led_off": "O {} 0",
    "return_on_off": "O? {}",
    "lock_led": "A {} {}",
    "register_status": "R?",
    "serial_number": "S?",
    "firmware": "V?",
    "manufacturer": "H?",
    "error_status": "E?",
}


class ThorlabsDC4100:
    def __init__(self, port=None, baudrate=115200, timeout=0.5):
        self.lock = threading.RLock()
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.dev = None
        self.escape = "\n\n"
        self.read_buffer = []
        self.availableDevices = []

        if self.port is None:
            self.list_devices()
            try:
                self.port = self.availableDevices[0]
                # print( 'Found Thorlabs DC4100 at port {}'.format(self.port) )
            except:
                raise Exception("No Thorlabs LED devices detected.")

        self.dev = SerialDevice(port=self.port, baudrate=self.baudrate, timeout=self.timeout)

    def list_devices(self):
        coms = serial.tools.list_ports.comports()
        for com, name, ident in coms:
            # several different ways this can appear:
            #  VID_1313+PID_8066
            #  VID_1313&PID_8066
            #  VID:PID=1313:8066
            if ("VID_1313" not in ident or "PID_8066" not in ident) and "1313:8066" not in ident:
                continue
            # else, add the device to the list
            self.availableDevices.append(com)

    def set_led_channel_state(self, channel, led_on):
        # print('Setting LED channel {} to state {}'.format( channel, state ))
        return self._send(COMMANDS["set_led_channel_state"].format(channel, 1 if led_on else 0), expect_response=False)

    def set_brightness(self, channel, brightness):
        if not (0 <= brightness <= 100):
            raise ValueError(f"Brightness must be between 0 and 100 (got {brightness})")
        return self._send(COMMANDS["set_brightness"].format(channel, brightness))

    def get_brightness(self, channel):
        ret = self._send(COMMANDS["get_brightness"].format(channel))
        return float(ret)

    def get_led_channel_state(self, channel):
        return self._send(COMMANDS["return_on_off"].format(channel)) == "1"

    def get_wavelength(self, channel):
        ret = self._send(COMMANDS["get_wavelength"].format(channel))
        return float(ret) * 1e-9

    @property
    def serial_number(self):
        return self._send(COMMANDS["serial_number"])

    @property
    def firmware(self):
        return self._send(COMMANDS["firmware"])

    @property
    def manufacturer(self):
        return self._send(COMMANDS["manufacturer"])

    def _send(self, command, expect_response=True, retry=2):
        with self.lock:
            while True:
                self._write_to_LED(command)
                if not expect_response:
                    return
                ret_value = self._read_from_LED().strip()
                if ret_value.startswith("ERROR "):
                    if "10:Communication error" in ret_value and retry > 0:
                        retry -= 1
                        time.sleep(0.1)
                        continue
                    else:
                        _, _, err = ret_value.partition("ERROR ")
                        raise Exception(f"DC4100 error: {err}")
                return ret_value

    def _write_to_LED(self, command):
        self.dev.write((command + self.escape).encode())

    def _read_from_LED(self):
        while self.dev.serial.is_open:
            output = self.dev.read(1, timeout=2).decode()
            if len(self.read_buffer) == 0 and output == "\r":
                self.dev.clearBuffer()
                continue
            if output == "\n":
                ret_value = "".join(self.read_buffer)
                self.dev.clearBuffer()
                self.read_buffer = []
                return ret_value
            else:
                self.read_buffer.append(output)


def main():
    led = ThorlabsDC4100()


if __name__ == "__main__":
    main()
