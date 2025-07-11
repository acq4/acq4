import threading
from time import sleep

import acq4.util.Qt as Qt
from acq4.devices.Device import Device
from acq4.drivers.sensapex import UMP
from acq4.util import ptime
from acq4.util.Thread import Thread
from acq4.util.future import Future


class SensapexObjectiveChanger(Device):
    """
    Sensapex motorized objective changer device.
    
    Controls objective lens positioning on Sensapex microscope systems
    with automatic position monitoring and switch interface compatibility.
    
    Configuration options:
    
    * **deviceId** (int, required): Sensapex device ID for objective changer
    
    * **address** (str, optional): Network address for TCP connection
      (uses global 'drivers/sensapex' config section if not specified)
    
    * **group** (int, optional): Device group number for shared connection
      (uses global 'drivers/sensapex' config section if not specified)
    
    * **pollInterval** (float, optional): Position polling interval in seconds
      (default: 2.0)
    
    Emits sigSwitchChanged(self, {'lens_position': position}) when position changes.
    
    Provides switch interface methods for integration with Microscope devices:
    - setSwitch('lens_position', value)
    - getSwitch('lens_position')
    
    Example configuration::
    
        ObjectiveChanger:
            driver: 'SensapexObjectiveChanger'
            deviceId: 40
            pollInterval: 1.0
    """
    sigSwitchChanged = Qt.Signal(object, object)

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)

        address = config.pop('address', None)
        group = config.pop('group', None)
        ump = UMP.get_ump(address=address, group=group, handle_atexit=False)
        self.dev = ump.get_device(config.get('deviceId'))

        self._lastPos = None
        self._lensChangeFuture = None
        self.getLensPosition()
        self._pos_poller = _PositionPollThread(self, config.get("pollInterval", 2))
        self._pos_poller.start()

    def setLensPosition(self, pos):
        if self._lensChangeFuture is None or self._lensChangeFuture.isDone():
            self._lensChangeFuture = ObjectiveChangeFuture(self, pos)
        return self._lensChangeFuture

    def getLensPosition(self):
        pos = self.dev.get_lens_position()
        if pos != self._lastPos:
            self._lastPos = pos
            self.sigSwitchChanged.emit(self, {'lens_position': pos})

        return pos

    # Switch methods allow this device to be used wherever a switch interface is accepted
    def setSwitch(self, name, value):
        assert name == 'lens_position'
        self.setLensPosition(value)

    def getSwitch(self, name):
        assert name == 'lens_position'
        return self.getLensPosition()


class _PositionPollThread(Thread):
    def __init__(self, dev, poll_interval):
        Thread.__init__(self)
        self._dev = dev
        self._poll_interval = poll_interval

    def run(self):
        while True:
            self._dev.getLensPosition()
            sleep(self._poll_interval)


class ObjectiveChangeFuture(Future):
    def __init__(self, dev: SensapexObjectiveChanger, pos):
        Future.__init__(self)
        self.dev = dev
        self.target = pos
        self._start = ptime.time()
        self._retried = False
        self.pollThread = threading.Thread(target=self.poll)
        self.pollThread.daemon = True

        if dev.getLensPosition() == pos:
            self._taskDone()
        else:
            dev.dev.set_lens_position(pos)
            self.pollThread.start()

    def poll(self):
        target = self.target
        dev = self.dev
        while True:
            pos = dev.getLensPosition()
            if pos == target:
                self._taskDone()
                break
            elif ptime.time() > self._start + 15:
                if self._retried:
                    self._taskDone(interrupted=True, error="Timed out waiting for objective changer to move (retried once)")
                    break
                else:
                    self._retried = True
                    self._start = ptime.time()
                    dev.dev.set_lens_position(target)
            try:
                self.sleep(0.2)
            except self.StopRequested:
                self._taskDone(interrupted=True, error="Stop requested before operation finished.")
                break

    def stop(self, **kwargs):
        self.dev.stop()
        Future.stop(self)

    def percentDone(self):
        return 100 if self.isDone() else 0
