from __future__ import print_function
import os
from .AnalysisModule import *

mdir = os.path.split(__file__)[0]
MODULES = []

for f in os.listdir(mdir):
    if os.path.isdir(os.path.join(mdir, f)):
        MODULES.append(f)
    elif f.endswith('.py'):
        f = os.path.splitext(f)[0]
        if f not in ['__init__', 'AnalysisModule']:
            print(f)
            MODULES.append(f)

def createAnalysisModule(name, runner):
    """
    Create a new instance of an analysis module.
    
    *name* must be the name of an importable python module in the 
    `modules/TaskRunner/analysisModules` directory, and must define one 
    subclass of AnalysisModule.
    
    *runner* must be a TaskRunner instance to which the new module should be
    attached.
    """
    if name not in MODULES:
        raise Exception('No analysis module named %s' % name)
    mod = __import__('acq4.modules.TaskRunner.analysisModules.' + name, fromlist=['*'])
    
    # Look for Modname+Module first, for backward compatibility
    cls = getattr(mod, name + 'Module', None)
    
    # Then look for the first object that is a subclass of AnalysisModule
    if cls is None:
        for obj in mod.__dict__.values():
            try:
                if obj is not AnalysisModule and issubclass(obj, AnalysisModule):
                    cls = obj
                    break
            except Exception:
                pass
    
    return cls(runner)

