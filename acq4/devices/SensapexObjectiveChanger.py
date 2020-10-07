import threading

from acq4.drivers.sensapex import UMP

import acq4.util.Qt as Qt
from acq4.devices.Device import Device
from acq4.util.future import Future


class SensapexObjectiveChanger(Device):
    sigSwitchChanged = Qt.Signal(object, object)

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)

        self.devid = config.get('deviceId')       
        if dm.config.get("drivers", {}).get("sensapex", {}).get("driverPath", None) is not None:
            UMP.set_library_path(dm.config["drivers"]["sensapex"]["driverPath"])
        address = config.pop('address', None)
        group = config.pop('group', None)
        ump = UMP.get_ump(address=address, group=group)
        self.dev = ump.get_device(self.devid)

        self._lastPos = None

    def setLensPosition(self, pos):
        return ObjectiveChangeFuture(self, pos)

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


class ObjectiveChangeFuture(Future):
    def __init__(self, dev, pos):
        Future.__init__(self)
        self.dev = dev
        self.target = pos
        self.dev.dev.set_lens_position(pos)
        self.pollThread = threading.Thread(target=self.poll)
        self.pollThread.daemon = True
        self.pollThread.start()

    def poll(self):
        target = self.target
        dev = self.dev
        while True:
            pos = dev.getLensPosition()
            if pos == target:
                self._taskDone()
                break
            try:
                self._checkStop(delay=0.2)
            except self.StopRequested:
                self._taskDone(interrupted=True, error="Stop requested bfore operation finished.")
                break

    def stop(self):
        self.dev.stop()
        Future.stop(self)

    def percentDone(self):
        return 100 if self.isDone() else 0

