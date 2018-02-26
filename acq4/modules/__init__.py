from collections import OrderedDict
from importlib import import_module
import os


MODULE_CLASSES = OrderedDict()


def getModuleClass(name):
    """Return a registered module class given its name.
    """
    try:
        return MODULE_CLASSES[name]
    except KeyError:
        raise KeyError('No registered module class named "%s"' % name)


def registerModuleClass(modclass, name):
    """Register a module class.

    This makes it possible for the ACQ4 Manager to instantiate modules by name.

    Parameters
    ----------
    modclass : Module subclass
        The new module type to register.
    name : str
        The name of the module class.
    """
    global MODULE_CLASSES
    if name in MODULE_CLASSES:
        raise KeyError('Module class named "%s" is already registered' % name)
    MODULE_CLASSES[name] = modclass


_builtin_registered = False
def registerBuiltinClasses():
    """Load and register all builtin module classes.
    """
    global _builtin_registered
    if _builtin_registered:
        return
    _builtin_registered = True

    path = os.path.dirname(__file__)
    for f in os.listdir(path):
        ff = os.path.join(path, f)
        if not (os.path.isdir(ff) or ff.endswith('.py')):
            continue
        # skip a few known files
        if f in ['__init__.py', 'Module.py', '__pycache__']:
            continue
        if f[-3:] == '.py':
            f = f[:-3]
        mod = import_module('acq4.modules.' + f)
        cls = getattr(mod, f)
        registerModuleClass(cls, f)
