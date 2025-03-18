from acq4.devices.Sonicator import Sonicator
from acq4.util.future import Future, future_wrap


class DAQSonicator(Sonicator):
    """Sonicator controlled by a DAQ device.
    Config
    ------
    capacitance : float
        The capacitance of the piezoelectric transducer in Farads. This is used to calculate the voltage required to hit
        a given frequency, as well as the limits of the voltage output.
    A0 : str
        The name of the analog output channel connected to the sonicator.
    D0 : str
        The name of the digital output channel connected to the sonicator.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @future_wrap
    def sonicate(self, frequency: float, duration: float, _future: Future):
        pass  # TODO
