import logging
import os
import serial as Serial
from serial import SerialException


COMMANDS = {
    "set_brightness": "BP {} {}",
    "get_brightness": "BP? {}",
    "set_led_channel_state": "O {} {}",
    "led_on": "O {} 1",
    "led_off": "O {} 0",
    "return_on_off": "O? {}",
    "lock_led": "A {} {}",
    "register_status": "R?",
    "serial_number": "S?",  
    "firmware": "V?",
    "manufacturer": "H?",
    "error_status": "E?"
    }

class ThorlabsDC4100:
    def __init__(self,port,baudrate,timeout):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.dev = None
        self.escape = '\n\n'
        self.read_buffer = []
        self.channel_state = [ 0, 0, 0, 0]
    
    def connect_device(self):
        try:
            print('Mock ThorlabsDC4100')
            print('Connected port={}, baudrate={}, timeout={} '.format(self.port, self.baudrate, self.timeout ) )
            self.dev = 1
        except SerialException:
            logging.error("Device connection could not be established")
            
    def set_led_channel_state(self, channel, state):
        print('Setting LED channel {} to state {}'.format( channel, state ))
        self._write_to_LED(COMMANDS["set_led_channel_state"].format(channel, state))

    def led_on(self, channel):
        print('Turning on LED channel {}'.format( channel ))
        self._write_to_LED(COMMANDS["led_on"].format(channel))
    
    def led_off(self,channel):
        self._write_to_LED(COMMANDS["led_off"].format(channel))
    
    def set_brightness(self,channel, brightness):
        self._write_to_LED(COMMANDS["set_brightness"].format(channel,brightness))
    
    def get_brightness(self,channel):
        self._write_to_LED(COMMANDS["get_brightness"].format(channel))
        return self._read_from_LED()
    
    def check_if_on(self, channel):
        self._write_to_LED(COMMANDS["return_on_off"].format(channel))
        return self._read_from_LED()
    
    @property
    def serial_number(self):
        self._write_to_LED(COMMANDS["serial_number"])
        return self._read_from_LED()

    @property
    def firmware(self):
        self._write_to_LED(COMMANDS["firmware"])
        return self._read_from_LED()

    @property
    def manufacturer(self):
        self._write_to_LED(COMMANDS["manufacturer"])
        return self._read_from_LED()

    def _write_to_LED(self, command):
        # parse string into action, channel, value
        split_string = command.split(' ')
        if split_string[0] == 'O':
            None  # do something here

    def _read_from_LED(self):
        print('Result: {}'.format( self.read_buffer) )
        self.read_buffer = []


def main():
    led = ThorlabsDC4100(port='com12',baudrate=115200,timeout=0.5)

if __name__ == "__main__":
    main()
