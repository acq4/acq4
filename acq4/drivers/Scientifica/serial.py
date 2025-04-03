import contextlib
import threading

import serial

from acq4.drivers.SerialDevice import SerialDevice


class ScientificaSerial:
    """Handle low-level interaction with the serial port
    - baudrate negotiation
    - verification of hardware
    - send/receive with error checking
    - thread safe
    """
    def __init__(self, port, baudrate=None):
        self.lock = threading.RLock()

        # try both baudrates, regardless of the requested rate
        # (but try the requested rate first)
        baudrate = 9600 if baudrate is None else int(baudrate)
        if baudrate == 9600:
            baudrates = [9600, 38400]
        elif baudrate == 38400:
            baudrates = [38400, 9600]
        else:
            raise ValueError(f'invalid baudrate {baudrate}')

        connected = False
        for baudrate in baudrates:
            with contextlib.suppress(TimeoutError):                
                self.serial = SerialDevice(port=port, baudrate=baudrate)
                try:
                    try:
                        sci = self.send('scientifica', timeout=0.2)
                    except RuntimeError:
                        # try again because prior communication at a different baud rate may have garbled serial communication.
                        sci = self.send('scientifica', timeout=1.0)

                    if sci != b'Y519':
                        # Device responded, not scientifica.
                        raise ValueError(
                            f"Received unexpected response from device at {port}. (Is this a scientifica device?)"
                        )
                    connected = True
                    break
                except Exception:
                    self.serial.close()
                    raise 
        
        if not connected:
            raise RuntimeError(
                f"No response received from Scientifica device at {port}. (tried baud rates: {', '.join(map(str, baudrates))})"
            )

    def send(self, msg, timeout=5.0):
        """Send a command and receive a response.

        This is the standard protocol for communication with scientifica devices.
        """
        if isinstance(msg, str):
            msg = msg.encode()
        with self.lock:
            self.serial.write(msg + b'\r')
            try:
                result = self.serial.readUntil(b'\r', timeout=timeout)[:-1]
                self.flush() # should be nothing left in the buffer at this point
            except TimeoutError:
                self.flush()
                raise
            if result.startswith(b'E,'):
                errno = int(result.strip()[2:])
                exc = RuntimeError(f"Received error {errno:d} from Scientifica controller (request: {msg!r})")
                exc.errno = errno
                raise exc
            return result

    def flush(self):
        return self.serial.readAll()

    def setBaudrate(self, baudrate):
        """Set the baud rate of the device.
        May be either 9600 or 38400.
        """
        baudkey = {9600: '96', 38400: '38'}[baudrate]
        with self.lock:
            self.serial.write('BAUD %s\r' % baudkey)
            self.serial.close()
            self.serial.open(baudrate=baudrate)

    def getBaudrate(self):
        return self.serial.getBaudrate()

    def clear(self):
        """Clear and return any pending serial data
        """
        return self.flush()

    def getDescription(self):
        """Return this device's description string.
        """
        return self.send('desc')

    def close(self):
        with self.lock:
            self.serial.close()
