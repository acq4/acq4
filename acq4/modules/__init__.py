from __future__ import print_function
from collections import OrderedDict
from importlib import import_module
import os
from ..util.debug import printExc


MODULE_CLASSES = OrderedDict()


def getModuleClass(name):
    """Return a registered module class given its name.
    """
    try:
        return MODULE_CLASSES[name]
    except KeyError:
        raise KeyError('No registered module class named "%s"' % name)


def registerModuleClass(modclass):
    """Register a module class.

    This makes it possible for the ACQ4 Manager to instantiate modules by name,
    and also causes the module to be displayed in the manager window's list of
    loadable modules.
    """
    global MODULE_CLASSES
    name = modclass.__name__
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
        try:
            mod = import_module('acq4.modules.' + f)
            cls = getattr(mod, f)
            registerModuleClass(cls)
        except Exception:
            printExc('Error while registering builtin module class from %s' % ff)
