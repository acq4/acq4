"""USB and Bluetooth gamepad input, polled from pygame on a dedicated thread.

One :class:`PygameEventThread` serves every :class:`Joystick` device: it forwards pygame
events to each device, reports gamepad removal, and sends each attached device a
heartbeat once per poll.
"""
from __future__ import print_function
import time, atexit
import pygame.joystick
from .Device import Device
from acq4.util.Thread import Thread
from acq4.util.Mutex import Mutex
from pyqtgraph import QtCore


pygame.init()
pygame.joystick.init()


class Joystick(Device):
    """
    Device for interfacing with USB/Bluetooth joysticks and game controllers.
    
    Uses pygame to detect and monitor joystick input for controlling other devices.
    
    Configuration options:
    
    * **index** (int, optional): Joystick index number (0 for first joystick, etc.)
      Either index or name must be specified.
    
    * **name** (str, optional): Joystick name string for identification
      Either index or name must be specified.
    
    The device emits sigStateChanged(self, change) when buttons or axes change. It also
    emits ``{'removed': True}`` when the gamepad is unplugged, after resetting every axis
    and button to rest, and ``{'heartbeat': True}`` once per poll while the gamepad is
    attached, so a listener can tell a stick held still from a gamepad that is gone.
    
    Example configuration::
    
        Joystick1:
            driver: 'Joystick'
            index: 0
    
    or::
    
        Joystick1:
            driver: 'Joystick'
            name: 'Xbox Controller'
    """
    sigStateChanged = QtCore.Signal(object, object)  # self, change

    def __init__(self, manager, config, name):
        Device.__init__(self, manager, config, name)
        eventThread = PygameEventThread.get()
        if 'index' in config:
            jsid = config['index']
        elif 'name' in config:
            jsid = eventThread.joystickId(config['name'])
        else:
            raise TypeError('Joystick config requires either an "index" or "name" parameter.')

        self._state = None
        self._stateLock = Mutex()
        self._present = True
        self.js = eventThread.initJoystick(jsid, self)

    def state(self):
        with self._stateLock:
            return self._state.copy()

    def joystickRemoved(self):
        """Mark this gamepad unplugged: reset axes and buttons to rest and emit ``removed``.

        Called from :class:`PygameEventThread`; repeat calls do nothing.
        """
        with self._stateLock:
            if not self._present:
                return
            self._present = False
            if self._state is not None:
                self._state['axes'] = [0.0] * len(self._state['axes'])
                self._state['buttons'] = [False] * len(self._state['buttons'])
        self.sigStateChanged.emit(self, {'removed': True})

    def joystickHeartbeat(self):
        """Announce that this gamepad is still attached, with no reading to report."""
        self.sigStateChanged.emit(self, {'heartbeat': True})

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
        # Name -> index, not name -> Joystick: initJoystick() indexes into self.joys.
        self.jsnames = {js.get_name(): i for i, js in self.joys.items()}
        self.devices = {}  # joystick index -> the Joystick device reading it
        self.instanceIds = {}  # pygame instance id -> joystick index
        self.stop = False
        atexit.register(self.quit)
        Thread.__init__(self, name='PygameEventThread', daemon=True)

    def joystickId(self, name):
        """Return the index of the attached joystick called *name*."""
        try:
            return self.jsnames[name]
        except KeyError:
            raise KeyError('Joystick named "%s" not found; options are: %s' % (name, list(self.jsnames.keys())))

    def initJoystick(self, id, device):
        """Open joystick *id*, and route its events, removal and heartbeats to *device*."""
        js = self.joys[id]
        js.init()
        self.devices[id] = device
        self.instanceIds[js.get_instance_id()] = id
        return js

    def run(self):
        joyEvents = (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP, pygame.JOYAXISMOTION)
        while not self.stop:
            for event in pygame.event.get():
                if event.type == pygame.JOYDEVICEREMOVED:
                    self._deviceRemoved(event)
                    continue
                if event.type not in joyEvents:
                    continue
                dev = self.devices.get(event.joy, None)
                if dev is None:
                    continue
                dev.joystickEvent(event)

            self._heartbeat()
            time.sleep(0.02)

    def _deviceRemoved(self, event):
        """Notify the device reading the joystick named by JOYDEVICEREMOVED *event*.

        This is the only place a removal is seen: pygame.event.get() drains the queue.
        """
        id = self.instanceIds.pop(getattr(event, 'instance_id', event.joy), None)
        dev = self.devices.pop(id, None)
        if dev is not None:
            dev.joystickRemoved()

    def _heartbeat(self):
        """Send each attached gamepad's device a heartbeat.

        A stick held still, e.g. at full deflection, sends no events, so the heartbeat is
        the only sign the gamepad is still attached.
        """
        for dev in list(self.devices.values()):
            dev.joystickHeartbeat()

    def quit(self):
        self.stop = True
        pygame.quit()
