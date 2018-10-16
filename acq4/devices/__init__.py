from __future__ import print_function
from collections import OrderedDict
from importlib import import_module
from . import Device


def getDeviceClass(name):
    """Return a device class given its name.

    The class must have been defined already, or it must be importable from ``acq4.devices.name``.
    """
    devClasses = getDeviceClasses()

    # If we don't recognize the class name, try importing from builtin devices
    # Note: eventually it would be nice if all device classes can be safely/cheaply
    # imported at startup, rather than dynamically importing them.
    if name not in devClasses:
        try:
            import_module('acq4.devices.' + name)
            devClasses = getDeviceClasses()
        except ImportError as exc:
            print("Warning: error importing device class %s: %s" % (name, str(exc)))

    try:
        return devClasses[name]
    except KeyError:
        raise KeyError('No registered device class named "%s"' % name)


def getDeviceClasses():
    """Return a dict containing name:class pairs for all defined Device subclasses.
    """
    devClasses = OrderedDict()

    # recursively find all imported Device subclasses
    subclasses = [Device.Device]
    for cls in subclasses:
        subclasses.extend(cls.__subclasses__())
        if cls is Device.Device:
            continue
        devClasses[cls.__name__] = cls
    
    return devClasses
