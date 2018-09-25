from __future__ import print_function
from ..Pipette import Pipette
from acq4.util import Qt
from ...Manager import getManager


class PatchPipette(Pipette):
    """Represents a single patch pipette, manipulator, and headstage.

    This class extends from the Pipette device class to provide automation and visual feedback
    on the status of the patch:

        * Whether a cell is currently patched
        * Input resistance, access resistance, and holding levels

    This is also a good place to implement pressure control, autopatching, slow voltage clamp, etc.
    """
    sigStateChanged = Qt.Signal(object)

    def __init__(self, deviceManager, config, name):
        self.pressures = {
            'out': 'atmosphere',
            'bath': 0.5,
            'approach': 0.5,
            'seal': 'user',
        }

        self._clampName = config.pop('clampDevice', None)
        self._clampDevice = None

        Pipette.__init__(self, deviceManager, config, name)
        self.state = "out"
        self.active = False

        self.pressureDevice = None
        if 'pressureDevice' in config:
            self.pressureDevice = PressureControl(config['pressureDevice'])

    def getPatchStatus(self):
        """Return a dict describing the status of the patched cell.

        Includes keys:
        * state ('bath', 'sealing', 'on-cell', 'whole-cell', etc..)
        * resting potential
        * resting current
        * input resistance
        * access resistance
        * capacitance
        * clamp mode ('ic' or 'vc')
        * timestamp of last measurement

        """
        # maybe 'state' should be available via a different method?

    def getPressure(self):
        pass

    def setPressure(self, pressure):
        if self.pressureDevice is None:
            return
        self.pressureDevice.setPressure(pressure)        

    def setSelected(self):
        pass

    def approach(self):
        """Prepare pipette to enter tissue and patch a cell.

        - Move pipette to diagonal approach position
        - Auto-correct pipette offset
        - May increase pressure
        - Automatically hide tip/target markers when the tip is near the target
        """


    def seal(self):
        """Attempt to seal onto a cell.

        * switches to VC holding after passing 100 MOhm
        * increase suction if seal does not form
        """

    def setState(self, state):
        """out, bath, approach, seal, attached, breakin, wholecell
        """
        if self.pressureDevice is not None and state in self.pressures:
            p = self.pressures[state]
            if isinstance(p, str):
                self.pressureDevice.setSource(p)
                self.pressureDevice.setPressure(0)
            else:
                self.pressureDevice.setPressure(p)
                self.pressureDevice.setSource('regulator')

        self.state = state
        self.sigStateChanged.emit(self)

    def getState(self):
        return self.state

    def breakIn(self):
        """Rupture the cell membrane using negative current pulses.

        * -2 psi for 3 sec or until rupture
        * -4, -6, -8 psi if needed
        * longer wait time if needed
        """

    def setActive(self, active):
        self.active = active

    def clampDevice(self):
        if self._clampDevice is None:
            if self._clampName is None:
                return None
            self._clampDevice = getManager().getDevice(self._clampName)
        return self._clampDevice

    def autoPipetteOffset(self):
        clamp = self.clampDevice()
        if clamp is not None:
            clamp.autoPipetteOffset()


class PressureControl(Qt.QObject):
    def __init__(self, deviceName):
        Qt.QObject.__init__(self)
        man = getManager()
        self.device = man.getDevice(deviceName)

    def setPressure(self, p):
        """Set the regulated output pressure to the pipette.

        Note: this does _not_ change the configuration of any values.
        """
        self.device.setChanHolding('pressure_out', p)

    def setSource(self, mode):
        """Configure valves for the specified pressure source: "atmosphere", "user", or "regulator"
        """
        if mode == 'atmosphere':
            self.device.setChanHolding('user_valve', 0)
            self.device.setChanHolding('regulator_valve', 0)
        elif mode == 'user':
            self.device.setChanHolding('user_valve', 1)
            self.device.setChanHolding('regulator_valve', 0)
        elif mode == 'regulator':
            self.device.setChanHolding('regulator_valve', 1)
        else:
            raise ValueError("Unknown pressure source %r" % mode)
