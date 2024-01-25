import threading, socket, time

import numpy as np
from acq4.drivers.NewScale import NewScaleMPM as NewScaleMPM_driver
from .Stage import Stage, MoveFuture


class NewScaleMPM(Stage):

    devices = {}

    def __init__(self, man, config: dict, name):
        self.dev = NewScaleMPM_driver(config['ipAddress'])
        self._lastPos = None
        self._interval = 0.1
        Stage.__init__(self, man, config, name)
        man.sigAbortAll.connect(self.stop)

        self.monitorThread = threading.Thread(target=self.monitor, daemon=True)
        self.monitorThread.start()

    def axes(self):
        return ("x", "y", "z")

    def capabilities(self):
        """Return a structure describing the capabilities of this device"""
        if "capabilities" in self.config:
            return self.config["capabilities"]
        else:
            return {
                "getPos": (True, True, True),
                "setPos": (True, True, True),
                "limits": (False, False, False),
            }

    def stop(self):
        """Stop the manipulator immediately.
        """
        with self.lock:
            self.dev.halt()

    @property
    def positionUpdatesPerSecond(self):
        return 1 / self._interval

    def _getPosition(self):
        # Called by superclass when user requests position refresh
        with self.lock:
            # using timeout=0 forces read from cache (the monitor thread ensures
            # these values are up to date)
            pos = np.array(self.dev.getPosition_abs(), dtype=float)
            if self._lastPos is not None:
                dif = np.linalg.norm(pos - self._lastPos)

            # do not report changes < 100 nm
            if self._lastPos is None or dif > 0.1:
                self._lastPos = pos
                emit = True
            else:
                emit = False

        if emit:
            # don't emit signal while locked
            self.posChanged(pos)

        return pos

    def quit(self):
        Stage.quit(self)
        self.dev.close()

    def _move(self, pos, speed, linear):
        with self.lock:
            speed = self._interpretSpeed(speed)
            self._lastMove = NewScaleMoveFuture(self, pos, speed, linear)
            return self._lastMove

    def monitor(self):
        while True:
            try:
                self._getPosition()
            except socket.timeout:
                print("timeout in newscale monitor thread")
                pass
            time.sleep(self._interval)


class NewScaleMoveFuture(MoveFuture):
    def __init__(self, dev, pos, speed, linear):
        MoveFuture.__init__(self, dev, pos, speed)

        self._linear = linear
        self._interrupted = False
        self._errorMsg = None
        self._checked = False

        self.dev.dev.selectAxis('x')
        self.dev.dev.moveToTarget(pos[0])
        self.dev.dev.selectAxis('y')
        self.dev.dev.moveToTarget(pos[1])
        self.dev.dev.selectAxis('z')
        self.dev.dev.moveToTarget(pos[2])
        
