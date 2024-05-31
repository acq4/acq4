from acq4.util import Qt
from acq4.devices.Device import Device


class Keyboard(Device):
    sigStateChanged = Qt.Signal(object, object)  # self, changes

    def __init__(self, man, config, name):
        super().__init__(man, config, name)
        self._callbacks = {}
        # use queued signal here to ensure events are processed in GUI thread
        self.sigStateChanged.connect(self._handleCallbacks, Qt.Qt.QueuedConnection)

    def _handleCallbacks(self, dev, changes):
        # check for key press callbacks
        keych = changes.get('keys', [])
        for pos, state in keych:
            if state is False:
                continue
            for cb, args in self._callbacks.get(pos, []):
                cb(dev, changes, *args)

    def addKeyCallback(self, key, callback, args=()):
        self._callbacks.setdefault(key, []).append((callback, args))

    def setBacklights(self, state, **kwds):
        raise NotImplementedError()

    def getBacklights(self):
        raise NotImplementedError()

    def setBacklight(self, key, blue=None, red=None):
        raise NotImplementedError()

    def getState(self):
        raise NotImplementedError()

    def capabilities(self):
        raise NotImplementedError()

    def quit(self):
        raise NotImplementedError()
