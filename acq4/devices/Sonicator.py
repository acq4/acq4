from threading import RLock

from acq4.devices.Device import Device
from acq4.util import Qt
from acq4.util.future import future_wrap, Future


class Sonicator(Device):
    """Base class for any sonicator device."""

    sigSonicationChanged = Qt.pyqtSignal(float)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.actionLock = RLock()

    @future_wrap
    def doProtocol(self, mode: str, _future: Future = None, **kwargs) -> None:
        with self.actionLock:
            if mode in {"clean", "expel"}:
                duration = kwargs.get("duration", 5 if mode == "clean" else 1)
                frequency = kwargs.get("frequency", 150e3)
                _future.waitFor(self.sonicate(frequency, duration))
            elif mode == "quick cleanse":
                start = kwargs.get("start", 140e3)
                stop = kwargs.get("stop", 154e3)
                step = kwargs.get("step", 1e3)
                step_duration = kwargs.get("stepDuration", 100e-3)
                frequency = start
                while frequency < stop:
                    _future.waitFor(self.sonicate(frequency, step_duration))
                    frequency += step
                frequency -= step
                while frequency > start:
                    _future.waitFor(self.sonicate(frequency, step_duration))
                    frequency -= step
            else:
                raise ValueError(f"Unrecognized sonication protocol '{mode}'")

    def isBusy(self) -> bool:
        available = self.actionLock.acquire(blocking=False)
        if available:
            self.actionLock.release()
        return not available

    def sonicate(self, frequency: float, duration: float) -> Future:
        raise NotImplementedError()

    def deviceInterface(self, win):
        return SonicatorGUI(win, self)


class SonicatorGUI(Qt.QObject):
    pass  # todo
