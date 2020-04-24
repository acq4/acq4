from __future__ import print_function
import serial, time, sys
import logging

import six


class TimeoutError(Exception):
    """Raised when a serial communication times out.

    *data* attribute contains any data received so far.
    """
    def __init__(self, msg, data):
        self.data = data
        Exception.__init__(self, msg)


class DataError(Exception):
    """Raised when a serial communication is corrupt.

    *data* attribute contains the corrupt packet.
    *extra* attribute contains any data left in the serial buffer 
    past the end of the packet.
    """
    def __init__(self, msg, data, extra):
        self.data = data
        self.extra = extra
        Exception.__init__(self, msg)


class SerialDevice(object):
    """
    Class used for standardizing access to serial devices. 

    Provides some commonly used functions for reading and writing 
    serial packets.
    """
    def __init__(self, **kwds):
        """
        All keyword arguments define the default arguments to use when 
        opening the serial port (see pyserial Serial.__init__).

        If both 'port' and 'baudrate' are provided here, then 
        self.open() is called automatically.
        """
        self.serial = None
        self.__serialOpts = {
            'bytesize': serial.EIGHTBITS, 
            'timeout': 0, # no timeout. See SerialDevice._readWithTimeout()
        }
        self.__serialOpts.update(kwds)

        if 'port' in kwds and 'baudrate' in self.__serialOpts:
            self.open()

    @classmethod
    def normalizePortName(cls, port):
        """
        Return a 'normalized' port name that is always the same for a particular serial port.
        On windows, this means 'com1', 'COM1', and 0 will all normalize to 0. On unix,
        the port name is unchanged.
        """
        if sys.platform.startswith('win'):
            if isinstance(port, int):
                port = 'com%d' % (port+1)
            elif isinstance(port, six.string_types) and port.lower()[:3] == 'com':
                port = port.lower()
        return port

    def open(self, port=None, baudrate=None, **kwds):
        """ Open a serial port. If this port was previously closed, then calling 
        open() with no arguments will re-open the original port with the same settings.
        All keyword arguments are sent to the pyserial Serial.__init__() method.
        """
        if port is None:
            port = self.__serialOpts['port']
        if baudrate is None:
            baudrate = self.__serialOpts['baudrate']

        port = SerialDevice.normalizePortName(port)

        self.__serialOpts.update({
            'port': port,
            'baudrate': baudrate,
            })
        self.__serialOpts.update(kwds)
        self.serial = serial.Serial(**self.__serialOpts)
        logging.info('Opened serial port: %s', self.__serialOpts)

    def close(self):
        """Close the serial port."""
        self.serial.close()
        self.serial = None
        logging.info('Closed serial port: %s', self.__serialOpts['port'])

    def readAll(self):
        """Read all bytes waiting in buffer; non-blocking."""
        n = self.serial.inWaiting()
        if n > 0:
            d = self.serial.read(n)
            logging.info('Serial port %s readAll: %r', self.__serialOpts['port'], d)
            return d
        return ''
    
    def write(self, data):
        """Write *data* to the serial port"""
        if sys.version > '3' and isinstance(data, str):
            data = data.encode()
        logging.info('Serial port %s write: %r', self.__serialOpts['port'], data)
        self.serial.write(data)

    def read(self, length, timeout=5, term=None):
        """
        Read *length* bytes or raise TimeoutError after *timeout* has elapsed.

        If *term* is given, check that the packet is terminated with *term* and 
        return the packet excluding *term*. If the packet is not terminated 
        with *term*, then DataError is raised.
        """
        #self.serial.setTimeout(timeout) #broken!
        packet = self._readWithTimeout(length, timeout)
        if len(packet) < length:
            raise TimeoutError("Timed out waiting for serial data (received so far: %s)" % repr(packet), packet)
        if term is not None:
            if packet[-len(term):] != term:
                time.sleep(0.01)
                extra = self.readAll()
                err = DataError("Packet corrupt: %s (len=%d)" % (repr(packet), len(packet)), packet, extra)
                raise err
            logging.info('Serial port %s read: %r', self.__serialOpts['port'], packet)
            return packet[:-len(term)]
        logging.info('Serial port %s read: %r', self.__serialOpts['port'], packet)
        return packet
        
    def _readWithTimeout(self, nBytes, timeout):
        # Note: pyserial's timeout mechanism is broken (specifically, calling setTimeout can cause 
        # serial data to be lost) so we implement our own in readWithTimeout().
        start = time.time()
        packet = b''
        # Interval between serial port checks is adaptive:
        #   * start with very short interval for low-latency reads
        #   * iteratively increase interval duration to reduce CPU usage on long reads
        sleep = 100e-6  # initial sleep is 100 us
        while time.time()-start < timeout:
            waiting = self.serial.inWaiting()
            if waiting > 0:
                readBytes = min(waiting, nBytes-len(packet))
                packet += self.serial.read(readBytes)
                sleep = 100e-6  # every time we read data, reset sleep time
            if len(packet) >= nBytes:
                break
            time.sleep(sleep)
            sleep = min(0.05, 2*sleep) # wait a bit longer next time
        return packet

    def readUntil(self, term, minBytes=0, timeout=5):
        """Read from the serial port until *term* is received, or *timeout* has elapsed.

        If *minBytes* is given, then this number of bytes will be read without checking for *term*.
        Returns the entire packet including *term*.
        """
        if isinstance(term, str):
            term = term.encode()

        start = time.time()

        if minBytes > 0:
            packet = self.read(minBytes, timeout=timeout)
        else:
            packet = b''

        while True:
            elapsed = time.time()-start
            if elapsed >= timeout:
                err = TimeoutError("Timed out while reading serial packet. Data so far: '%r'" % packet, packet)
                raise err
            try:
                packet += self.read(1, timeout=timeout-elapsed)
            except TimeoutError:
                raise TimeoutError("Timed out while reading serial packet. Data so far: '%r'" % packet, packet)

            if len(packet) > minBytes and packet[-len(term):] == term:
                return packet

    def clearBuffer(self):
        ## not recommended..
        d = self.readAll()
        time.sleep(0.1)
        d += self.readAll()
        if len(d) > 0:
            print(self, "Warning: discarded serial data ", repr(d))
        return d

    def getPort(self):
        """Return the serial port that was last connected.
        """
        return self.__serialOpts['port']

    def getBaudrate(self):
        """Return the configured baud rate.
        """
        return self.__serialOpts['baudrate']


if __name__ == '__main__':
    import sys, os
    try:
        port, baud = sys.argv[1:3]
    except:
        print("Usage: python -i SerialDevice port baudrate")
        os._exit(1)

    sd = SerialDevice(port=port, baudrate=baud)
    print("")
    print("Serial port opened and available as 'sd'.")
    print("Try using sd.write(...), sd.readAll(), and sd.read(length, term, timeout)")
