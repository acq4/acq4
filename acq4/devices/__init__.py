from collections import OrderedDict
from importlib import import_module
import os

DEVICE_CLASSES = OrderedDict()


def createDevice(devClassName, *args, **kwds):
    # could use this function to handle factory/configurator classes vs device classes
    return getDeviceClass(devClassName, *args, **kwds)


def getDeviceClass(name):
    """Return a registered device class given its name.
    """
    try:
        return DEVICE_CLASSES[name]
    except KeyError:
        raise KeyError('No registered device class named "%s"' % name)


def registerDeviceClass(devclass, name):
    """Register a device class.

    This makes it possible for the ACQ4 Manager to instantiate devices by name.

    Parameters
    ----------
    devclass : Device subclass
        The new device type to register.
    name : str
        The name of the device class.
    """
    global DEVICE_CLASSES
    if name in DEVICE_CLASSES:
        raise KeyError('Device class named "%s" is already registered' % name)
    DEVICE_CLASSES[name] = devclass


class DeferredClassLoader(object):
    """Used to wrap another class that has not been imported yet.

    Ideally, all device classes would be inexpensive to import -- they should do no work
    (especially further imports) until a device is instantiated. Until then, we need
    this wrapper.
    """
    def __init__(self, modname, clsname):
        self.modname = modname
        self.clsname = clsname
        self._cls = None

    def __call__(self, *args, **kwds):
        return self.cls(*args, **kwds)

    @property
    def cls(self):
        if self._cls is None:
            mod = import_module(self.modname)
            self._cls = getattr(mod, self.clsname)
        return self._cls


_builtin_registered = False
def registerBuiltinClasses():
    """Register all builtin device classes by searching the acq4/devices directory.

    This is called by the Manager when it is initialized (but otherwise, it is not called
    in order to avoid expensive import work)
    """
    global _builtin_registered
    if _builtin_registered:
        return
    _builtin_registered = True

    # Automatically register deferred-import wrappers for all devices defined within acq4/devices/.
    # Eventually this automation might go away if we can ensure that all device imports are quick
    # and error-free (by deferring driver imports instead).
    path = os.path.dirname(__file__)
    for f in os.listdir(path):
        ff = os.path.join(path, f)
        if not (os.path.isdir(ff) or ff.endswith('.py')):
            continue
        # skip a few known files
        if f in ['__init__.py', 'Device.py', 'OptomechDevice.py', '__pycache__']:
            continue
        if f[-3:] == '.py':
            f = f[:-3]
        wrapper = DeferredClassLoader(modname='acq4.devices.'+f, clsname=f)
        registerDeviceClass(wrapper, f)
