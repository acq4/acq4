from __future__ import print_function
import time, atexit
import pygame.joystick
from .Device import Device
from acq4.util.Thread import Thread
from acq4.util.Mutex import Mutex
from pyqtgraph import QtCore
from six.moves import range

pygame.init()
pygame.joystick.init()


class Joystick(Device):
    sigStateChanged = QtCore.Signal(object, object)  # self, change

    def __init__(self, manager, config, name):
        Device.__init__(self, manager, config, name)
        self.config = config
        eventThread = PygameEventThread.get()
        if 'index' in config:
            jsid = config['index']
        elif 'name' in config:
            jsid = eventThread.joystickId(config['name'])
        else:
            raise TypeError('Joystick config requires either an "index" or "name" parameter.')

        self._state = None
        self._stateLock = Mutex()
        self.js = eventThread.initJoystick(jsid, self.joystickEvent)

    def state(self):
        with self._stateLock:
            return self._state.copy()

    def joystickEvent(self, event):
        with self._stateLock:
            if self._state is None:
                state = {'axes': [], 'buttons': []}
                for i in range(self.js.get_numaxes()):
                    state['axes'].append(self.js.get_axis(i))
                for i in range(self.js.get_numbuttons()):
                    state['buttons'].append(bool(self.js.get_button(i)))
                self._state = state

            if event.type == pygame.JOYAXISMOTION:
                self._state['axes'][event.axis] = event.value
                ev = {'axis': event.axis, 'value': event.value}
            else:
                value = event.type == pygame.JOYBUTTONDOWN
                self._state['buttons'][event.button] = value
                ev = {'button': event.button, 'value': value}

        self.sigStateChanged.emit(self, ev)
        if self.config.get('printEvents', False):
            print("Joystick event: %s %s" % (self.name(), ev))


class PygameEventThread(Thread):
    SINGLE = None

    @classmethod
    def get(cls):
        if cls.SINGLE is None:
            cls.SINGLE = cls()
            cls.SINGLE.start()
        return cls.SINGLE

    def __init__(self):
        self.joys = {i:pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())}
        self.jsnames = {js.get_name():js for js in self.joys.values()}
        self.callbacks = {}
        self.stop = False
        atexit.register(self.quit)
        Thread.__init__(self)

    def joystickId(self, name):
        try:
            return self.jsnames[name]
        except KeyError:
            raise KeyError('Joystick named "%s" not found; options are: %s' % (name, list(self.jsnames.keys())))

    def initJoystick(self, id, callback):
        js = self.joys[id]
        js.init()
        self.callbacks[id] = callback
        return js

    def run(self):
        joyEvents = (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP, pygame.JOYAXISMOTION)
        while not self.stop:
            for event in pygame.event.get():
                if event.type not in joyEvents:
                    continue
                cb = self.callbacks.get(event.joy, None)
                if cb is None:
                    continue
                cb(event)
                
            time.sleep(0.02)

    def quit(self):
        self.stop = True
        pygame.quit()
