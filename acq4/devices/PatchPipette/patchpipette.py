from ..Pipette import Pipette


class PatchPipette(Pipette):
    """Represents a single patch pipette, manipulator, and headstage.

    This class extends from the Pipette device class to provide automation and visual feedback
    on the status of the patch:

        * Whether a cell is currently patched
        * Input resistance, access resistance, and holding levels

    This is also a good place to implement pressure control, autopatching, slow voltage clamp, etc.
    """
    def __init__(self, deviceManager, config, name):
        self.clamp = config.pop('clampDevice')

        Pipette.__init__(self, deviceManager, config, name)

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
        ...

    def setPressure(self):
        # accepts waveforms as well?
        ...

    def seal(self):
        """Attempt to seal onto a cell by releasing pressure

        * switches to VC holding after passing 100 MOhm
        * increase suction if seal does not form
        """
