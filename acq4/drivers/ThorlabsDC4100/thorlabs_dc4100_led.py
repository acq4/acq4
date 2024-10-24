import serial as s
import serial.tools.list_ports


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
    "error_status": "E?"
    }

class ThorlabsDC4100:
    def __init__(self,port=None,baudrate=115200,timeout=0.5):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.dev = None
        self.escape = '\n\n'
        self.read_buffer = []
        self.availableDevices = []

        if self.port is None:
            self.list_devices()
            try:
                self.port=self.availableDevices[0]
                # print( 'Found Thorlabs DC4100 at port {}'.format(self.port) )
            except:
                raise Exception("No Thorlabs LED devices detected.")
    
        self.dev = s.Serial(port=self.port, baudrate=self.baudrate, timeout=self.timeout)

    def list_devices(self):
        coms = serial.tools.list_ports.comports()
        for com, name, ident in coms:
            # several different ways this can appear:
            #  VID_1313+PID_8066
            #  VID_1313&PID_8066
            #  VID:PID=1313:8066
            if ('VID_1313' not in ident or 'PID_8066' not in ident) and '1313:8066' not in ident:
                continue
            # else, add the device to the list
            self.availableDevices.append( com )

    def set_led_channel_state(self, channel, led_on):
        # print('Setting LED channel {} to state {}'.format( channel, state ))
        self._write_to_LED(COMMANDS["set_led_channel_state"].format(channel, 1 if led_on else 0))

    def set_brightness(self,channel, brightness):
        if not (0 <= brightness <= 100):
            raise ValueError(f"Brightness must be between 0 and 100 (got {brightness})")
        self._write_to_LED(COMMANDS["set_brightness"].format(channel,brightness))
    
    def get_brightness(self,channel):
        self._write_to_LED(COMMANDS["get_brightness"].format(channel))
        return float(self._read_from_LED().strip())
    
    def get_led_channel_state(self, channel):
        self._write_to_LED(COMMANDS["return_on_off"].format(channel))
        return self._read_from_LED().strip() == '1'
    
    def get_wavelength(self, channel):
        self._write_to_LED(COMMANDS["get_wavelength"].format(channel))
        return float(self._read_from_LED().strip()) * 1e-9

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
        self.dev.write((command + self.escape).encode())
    
    def _read_from_LED(self):
        while self.dev.is_open:
            output = self.dev.read().decode()
            if len(self.read_buffer) == 0 and output == '\r':
                self.dev.flush()
                continue
            if output == "\n":
                ret_value = "".join(self.read_buffer)
                self.dev.flush()
                self.read_buffer = []
                return ret_value
            else:
                self.read_buffer.append(output)
    
def main():
    led = ThorlabsDC4100()

if __name__ == "__main__":
    main()
