import os
from AnalysisModule import *
mdir = os.path.split(__file__)[0]
MODULES = filter(lambda d: os.path.isdir(os.path.join(mdir, d)), os.listdir(mdir))
try:
    MODULES.remove('.svn')
except:
    pass
del mdir

def createAnalysisModule(name, runner):
    if name not in MODULES:
        raise Exception('No analysis module named %s' % name)
    mod = __import__('lib.modules.ProtocolRunner.analysisModules.' + name + 'Module', fromlist=['*'])
    cls = getattr(mod, name)
    return cls(runner)