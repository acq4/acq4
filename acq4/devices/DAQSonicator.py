import numpy as np

from acq4.devices.DAQGeneric import DAQGeneric
from acq4.devices.NiDAQ import NiDAQ
from acq4.devices.Sonicator import Sonicator
from acq4.util.future import Future, future_wrap
from neuroanalysis.stimuli import Sine
from pyqtgraph.units import nF, V, µs


class DAQSonicator(Sonicator):
    """Sonicator controlled by a DAQ device.
    Config
    ------
    capacitance : float
        The capacitance of the piezoelectric transducer in Farads. This is used to calculate the voltage required to hit
        a given frequency, as well as the limits of the voltage output.
    max slew rate : float
        The maximum safe slew rate of the piezoelectric transducer in V/μs. This is used to calculate the voltage
        output (default 3.9 V/μs).
    analog : dict
        The config of the analog output channel. This controls the voltage output to the sonicator.
    digital : dict (optional)
        The config of the digital output channel. This controls the power to the sonicator.
    """

    def __init__(self, deviceManager, config: dict, name: str):
        super().__init__(deviceManager, config, name)
        self.config = config
        self._capacitance = config.get("capacitance", 65 * nF)
        self._maxSlewRate = config.get("max slew rate", 3.9 * V / µs)
        daq_conf = {
            "channels": {
                "analog": config["analog"],
            },
        }
        if "digital" in config:
            daq_conf["channels"]["digital"] = config["digital"]
        self._daq = DAQGeneric(
            deviceManager,
            config=daq_conf,
            name=f"__sonicator{self.name()}DAQ",
        )

    @future_wrap
    def sonicate(self, frequency: float, duration: float, lock: bool = True, _future: Future = None):
        if lock:
            self.actionLock.acquire()
        try:
            # Calculate the voltage required to hit the desired frequency
            daq_name = self._daq.getDAQName("analog")
            daq: NiDAQ = self.dm.getDevice(daq_name)
            # sample_rate = daq.n.GetDevAIMaxSingleChanRate()
            sample_rate = 1_000_000
            voltage = self.calcVoltage(frequency)
            wave = Sine(0, duration, frequency, voltage).eval(sample_rate=sample_rate).data
            numPts = len(wave)
            cmd = {
                "protocol": {"duration": duration},
                daq_name: {
                    "rate": sample_rate,
                    "numPts": numPts,
                },
                self._daq.name(): {
                    "analog": {"command": wave},
                },
            }
            if self._daq.hasChannel("digital"):
                cmd[self._daq.name()]["digital"] = {"command": np.ones(numPts)}
            task = self.dm.createTask(cmd)
            _future.checkStop()
            task.execute()
        finally:
            if lock:
                self.actionLock.release()

    def calcVoltage(self, frequency: float) -> float:
        """
        Calculate a safe voltage amplitude for the PA3CKW piezo chip at any frequency.

        Args:
            frequency: Frequency in Hz

        Returns:
            peak_voltage: Safe peak voltage (half of Vpp)
        """
        # Calculate safe peak voltage based on max slew rate
        # SR = V * f * 2π → V = SR / (f * 2π)
        return self._maxSlewRate / (frequency * 2 * 3.14159)
