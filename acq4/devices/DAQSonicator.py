from __future__ import annotations

import json

import numpy as np

from acq4.devices.DAQGeneric import DAQGeneric
from acq4.devices.Sonicator import Sonicator
from acq4.util.future import future_wrap
from neuroanalysis.stimuli import load_stimulus
from pyqtgraph.units import nF, A


def calculate_slew_rate(wave: np.ndarray, dt: float):
    """
    Calculate the slew rate of a waveform.

    Args:
        wave: Waveform data
        dt: Time step in seconds

    Returns:
        slew_rate: Slew rate in V/s
    """
    return np.max(np.abs(np.diff(wave))) / dt


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
    command : dict
        The config of the analog output channel in charge of the voltage output to the sonicator.
    disable : dict (optional)
        The config of the output channel on which a 5V signal will disable the sonicator.
    overload : dict (optional)
        The config of the input channel on which a 5V signal will indicate and overload.
    protocols : dict
        Each protocol is a dictionary, in line with the output of Stimulus.save(), for example::
            clean:
                type: "Sine"
                args:
                    start_time: 0
                    duration: 5
                    frequency: 150000
                    amplitude: 1
            quick cleanse:
                type: "Chirp"
                args:
                    start_time: 0
                    duration: 5
                    start_frequency: 134000
                    end_frequency: 154000
                    amplitude: 3
            expel:
                type: "Stimulus"
                items: [{"type": "Chirp", "args": {"start_time": 0, "description": "frequency chirp", "units": null, "duration": 10, "start_frequency": 135000, "end_frequency": 154000, "amplitude": 1, "phase": 0, "offset": 0}, "items": []}, {"type": "Chirp", "args": {"start_time": 10, "duration": 10, "start_frequency": 154000, "end_frequency": 135000, "amplitude": 1}}]}

    """

    def __init__(self, deviceManager, config: dict, name: str):
        super().__init__(deviceManager, config, name)
        self._capacitance = config.get("capacitance", 65 * nF)
        self._maxCurrent = config.get("max current", 0.255 * A)
        self._maxSlewRate = config.get("max slew rate", self._maxCurrent / self._capacitance)
        if "scale" not in config["command"]:
            raise ValueError(
                "Command config must specify 'scale' (daq V / piezo V) to convert to account for driver gain"
            )
        daq_conf = {
            "channels": {
                "command": config["command"],
            },
        }
        if "disable" in config:
            config["disable"]["holding"] = 1
            daq_conf["channels"]["disable"] = config["disable"]
        if "overload" in config:
            daq_conf["channels"]["overload"] = config["overload"]
        self._daq = DAQGeneric(
            deviceManager,
            config=daq_conf,
            name=f"__sonicator{self.name()}DAQ",
        )

    @future_wrap
    def _doProtocol(self, protocol: str | dict, _future):
        if isinstance(protocol, str):
            protocol = load_stimulus(json.loads(protocol))
        else:
            protocol = load_stimulus(protocol)
        # daq: NiDAQ = self.dm.getDevice(daq_name)
        # sample_rate = daq.n.GetDevAIMaxSingleChanRate(self._daq...)  # this doesn't work
        sample_rate = 1_000_000
        duration = protocol.total_global_end_time
        wave = protocol.eval(n_pts=duration * sample_rate, sample_rate=sample_rate).data
        slew_rate = calculate_slew_rate(wave, 1 / sample_rate)
        if slew_rate > self._maxSlewRate:
            raise ValueError(f"Waveform slew rate {slew_rate} V/s exceeds max slew rate {self._maxSlewRate} V/s")
        numPts = len(wave)
        daq_name = self._daq.getDAQName("command")
        cmd = {
            "protocol": {"duration": duration},
            daq_name: {
                "rate": sample_rate,
                "numPts": numPts,
            },
            self._daq.name(): {
                "command": {"command": wave},
            },
        }
        task = self.dm.createTask(cmd)
        task.reserveDevices()
        try:
            if "disable" in self.config:
                self._daq.setChannelValue("disable", 0)
            if "overload" in self.config and self._daq.getChannelValue("overload"):
                raise RuntimeError("Overload detected. Please check the sonicator device.")
            task.execute(block=False, processEvents=False)
            while not task.isDone():
                _future.sleep(0.1)
            if "overload" in self.config and self._daq.getChannelValue("overload"):
                raise RuntimeError("Overload detected. Command likely required too much power.")
        except Exception:
            if task.stopped:
                task.abort()
            raise
        finally:
            task.stop()
            if "disable" in self.config:
                self._daq.setChannelValue("disable", 1)

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
