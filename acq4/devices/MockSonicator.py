import threading

import numpy as np
import pyaudio

import pyqtgraph as pg
from acq4.devices.Sonicator import Sonicator
from acq4.util.future import future_wrap
from pyqtgraph import siFormat


def map_frequency(source_freq, source_min=40e3, source_max=170e3):
    """Map ultrasonic frequency (40-170kHz) to audible range (100-2000Hz)"""
    # Linear mapping from ultrasonic to audible range
    min_audible, max_audible = 100, 2000

    # Normalize and map
    normalized = (source_freq - source_min) / (source_max - source_min)
    return min_audible + normalized * (max_audible - min_audible)


class MockSonicator(Sonicator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.sample_rate = 44100
        self.audible_freq = 0.0
        self.audio_thread = None
        self.stop_audio = threading.Event()

    def audio_callback(self, in_data, frame_count, time_info, status):
        if self.stop_audio.is_set():
            return np.zeros(frame_count, dtype=np.float32), pyaudio.paComplete

        # Generate sine wave at mapped frequency
        t = np.arange(frame_count) / self.sample_rate
        data = 0.5 * np.sin(2 * np.pi * self.audible_freq * t).astype(np.float32)
        return data, pyaudio.paContinue

    def play_sound(self, frequency, duration):
        """Play sound in a separate thread"""
        self.audible_freq = map_frequency(frequency)

        # Reset stop flag
        self.stop_audio.clear()

        # Open audio stream
        self.stream = self.audio.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=self.sample_rate,
            output=True,
            stream_callback=self.audio_callback
        )

        # Start the stream
        self.stream.start_stream()

        # Create a timer to stop the sound after duration
        def stop_sound():
            pg.QtCore.QThread.msleep(int(duration * 1000))
            self.stop_audio.set()
            if self.stream and self.stream.is_active():
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None

        self.audio_thread = threading.Thread(target=stop_sound)
        self.audio_thread.start()

    @future_wrap
    def sonicate(self, frequency, duration, lock=True, _future=None):
        if lock:
            self.actionLock.acquire()
        try:
            self.sigSonicationChanged.emit(frequency)
            print(
                f"Sonicating at {siFormat(frequency, suffix='Hz')} (audible: "
                f"{map_frequency(frequency):.1f}Hz) for {duration} seconds"
            )

            # Play sound
            self.play_sound(frequency, duration)

            # Wait for duration
            _future.sleep(duration)

            self.sigSonicationChanged.emit(0.0)
        finally:
            if lock:
                self.actionLock.release()

    def quit(self):
        if self.stream:
            self.stop_audio.set()
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        if self.audio:
            self.audio.terminate()
            self.audio = None

        super().quit()


if __name__ == "__main__":
    import sys
    from unittest.mock import MagicMock
    from acq4.util import Qt

    class TestWindow(Qt.QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Sonicator Test")
            self.resize(600, 500)

            # Create a mock sonicator device
            mock_manager = MagicMock()
            self.sonicator = MockSonicator(mock_manager, dict(), "test_sonicator")

            # Create and set the GUI as central widget
            self.gui = self.sonicator.deviceInterface(self)
            self.setCentralWidget(self.gui)

    app = Qt.QtWidgets.QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec_())
