from __future__ import print_function
from collections import OrderedDict
from importlib import import_module
import os
from ..util.debug import printExc
from . import Module


def getModuleClass(name):
    """Return a registered module class given its name.
    """
    modClasses = getModuleClasses()
    
    try:
        return modClasses[name]
    except KeyError:
        raise KeyError('No known module class named "%s"' % name)


def getModuleClasses():
    """Return a dict containing name:class pairs for all defined Module subclasses.
    """
    modClasses = OrderedDict()

    # recursively find all Module subclasses
    subclasses = [Module.Module]
    for cls in subclasses:
        subclasses.extend(cls.__subclasses__())
        if cls is Module.Module:
            continue
        modClasses[cls.__name__] = cls
    return modClasses


_builtin_imported = False
def importBuiltinClasses():
    """Import all builtin module classes under acq4/modules.
    """
    global _builtin_imported
    if _builtin_imported:
        return
    _builtin_imported = True

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
        except Exception:
            printExc('Error importing builtin module from %s' % ff)
