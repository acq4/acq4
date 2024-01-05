import time

import numpy as np
from threading import Thread

from pyacq import InputStream


class BaseCameraStreamHandler(object):
    def __init__(self, name: str, config: dict):
        self._name = name
        self._config = config
        self._input = InputStream(name=name, spec=config.get('spec'))
        self._poller = Thread(target=self._poll, daemon=True)

    def _poll(self):
        poll_interval = self._config.get('pollInterval', 0.1)
        only_latest = self._config.get('onlyHandleLatestFrame', False)
        while True:
            start = time.time()
            idx = None
            while self._input.poll(0):
                idx, _ = self._input.recv(return_data=False)
                if not only_latest:
                    break
            if idx is not None:
                self.handle_frame(self._input[idx:idx+1], idx)
            time.sleep(max(0.0, poll_interval - (time.time() - start)))

    def connect(self, output):
        self._input.connect(output)
        self._input.set_buffer(
            size=self._config.get('buffer_size'),
            axisorder=self._config.get('axisorder'),
            double=self._config.get('double'),
            fill=self._config.get('fill'),
        )
        if not self._poller.is_alive():
            self._poller.start()

    def close(self):
        self._input.close()

    def handle_frame(self, frame: np.ndarray, index: int):
        raise NotImplementedError()


class NoopCameraStreamHandler(BaseCameraStreamHandler):
    def __init__(self, **kwds):
        super().__init__(**kwds)
        self._fh = open('noop_log.txt', 'w')

    def handle_frame(self, frame: np.ndarray, index=None):
        self._fh.write(f'NoopCameraStreamHandler.handle_data(...{frame.size}, index={index}\n')
        self._fh.flush()

    def close(self):
        super().close()
        self._fh.close()
