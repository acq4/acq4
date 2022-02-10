from __future__ import print_function

from collections import OrderedDict
from importlib import import_module

from . import Device


def getDeviceClass(name):
    """Return a device class given its name.

    The *name* argument can be one of:
    - The name of a Device subclass that has already been imported
    - The name of a built-in Device subclass
      (for example name='Pipette' would return the Pipette class defined in acq4.devices.Pipette)
    - The name of an importable module that defines a Device subclass
      (for example name='mymodule.MyDevice' would attempt to import MyDevice from mymodule.MyDevice)
    """
    devClasses = getDeviceClasses()

    # If we don't recognize the class name, try importing from builtin devices
    # Note: eventually it would be nice if all device classes can be safely/cheaply
    # imported at startup, rather than dynamically importing them.
    if name not in devClasses:
        namesToCheck = [name, 'acq4.devices.' + name]
        for name in namesToCheck:
            try:
                import_module(name)
                break
            except ModuleNotFoundError as exc:
                if exc.name not in name:
                    raise  # some other missing module is a legitimate problem
                if name == namesToCheck[-1]:
                    raise Exception(f"No module found from names: {namesToCheck}")
                continue

    devClasses = getDeviceClasses()

    try:
        clsName = name.split(".")[-1]
        return devClasses[clsName]
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
