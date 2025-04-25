import threading
from ..Stage import Stage, MoveFuture
from acq4.drivers.dovermotion.motionsynergy_client import get_client


class DoverStage(Stage):
    """
    A DoverMotion stage device.
    """

    def __init__(self, man, config: dict, name):
        self.msapi = get_client(dll_path=config["dllPath"])
        self.dev = self.msapi['smartstage']
        self.dev.enable()
        self._lastMove = None
        Stage.__init__(self, man, config, name)

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
        """Stop the stage immediately.
        """
        return self.dev.stop()

    def _getPosition(self):
        return self.dev.pos()

    def quit(self):
        Stage.quit(self)
        self.dev.disable()

    def _move(self, pos, speed, linear, **kwds):
        speed = self._interpretSpeed(speed)
        self._lastMove = DoverMoveFuture(self, pos, speed, linear)
        return self._lastMove

    def targetPosition(self):
        """Return the target position of the last move command.
        """
        if self._lastMove is not None:
            return self._lastMove.target
        else:
            return None

    # def deviceInterface(self, win):
    #     return DoverStageInterface(self, win)


class DoverMoveFuture(MoveFuture):
    """Provides access to a move-in-progress on a Dover stage.
    """
    def __init__(self, dev, pos, speed, linear):
        MoveFuture.__init__(self, dev, pos, speed)
        self.dev = dev
        self.target = pos
        self._future = self.dev.dev.move(pos, self.speed * 1e6)
        self._future.set_callback(self._future_finished)

    def _future_finished(self):
        self._taskDone(
            interrupted=self._future.error is not None,
            error=self._future.error,
            excInfo=self._future.exc_info,
        )