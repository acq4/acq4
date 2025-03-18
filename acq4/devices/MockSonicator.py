from acq4.devices.Sonicator import Sonicator
from acq4.util.future import future_wrap
from pyqtgraph import siFormat


class MockSonicator(Sonicator):
    @future_wrap
    def sonicate(self, frequency, duration, lock=True, _future=None):
        if lock:
            self.actionLock.acquire()
        try:
            self.sigSonicationChanged.emit(frequency)
            print(f"Sonicating at {siFormat(frequency, suffix='Hz')} for {duration} seconds")
            _future.sleep(duration)
            self.sigSonicationChanged.emit(0.0)
        finally:
            if lock:
                self.actionLock.release()
