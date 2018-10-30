from __future__ import print_function
from acq4.util import Qt
from acq4.util.Mutex import Mutex
from acq4.devices.Device import Device


class StageSwitch(Device):
    """Switch device that uses stage position to determine its output.

    This is used, for example, in the Scientifica SliceScope where one stage axis is used to
    switch between objectives.

    Example configuration::

        MOC:
            driver: 'StageSwitch'
            switches:
                # Emit a signal when MOC switches position (x axis crosses position thresholds)
                objective: 
                    device: 'Condenser'
                    0: ([None, 0.0445], None, None)  # x values < 0.0445 are position 0
                    1: ([0.045, None], None, None)   # x values > 0.045 are position 1

    The above example is a device with one switch called "objective" that monitors the x
    axis of the 'Condenser' device for position changes.
    """

    sigSwitchChanged = Qt.Signal(object, object)  # self, {switch_name: value, ...}

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = Mutex(Qt.QMutex.Recursive)

        # used to emit signal when position passes a threshold
        self.switches = {}
        self.switchThresholds = {}
        devs = set()
        for name, spec in config.get('switches', {}).items():
            spec = spec.copy()
            devName = spec.pop('device')
            dev = dm.getDevice(devName)
            dev.sigPositionChanged.connect(self.stagePosChanged)
            devs.add(dev)
            self.switches[name] = list(spec.keys())[0]  # pick first objective by default
            self.switchThresholds.setdefault(devName, {})[name] = spec

        for dev in devs:
            self.stagePosChanged(dev, dev.getPosition(), None)

    def stagePosChanged(self, dev, pos, old):
        devName = dev.name()
        switches = self.switchThresholds[devName]

        changes = {}
        # iterate over switches
        for switchName, spec in switches.items():
            # iterate over possible values for this switch
            for value, thresh in spec.items():
                # iterate over axis thresholds for this value
                match = False
                for ax, levels in enumerate(thresh):
                    if levels is None:
                        continue
                    minval, maxval = levels
                    match = (minval is None or pos[ax] > minval) and (maxval is None or pos[ax] < maxval)
                    if not match:
                        break

                if match is False:
                    continue

                if self.switches[switchName] != value:
                    changes[switchName] = value

        if len(changes) > 0:
            with self.lock:
                self.switches.update(changes)
            self.sigSwitchChanged.emit(self, changes)

    def getSwitch(self, name):
        with self.lock:
            return self.switches[name]



        
