# -*- coding: utf-8 -*-
import os

def listAtlases():
    d = os.path.split(__file__)[0]
    files = []
    for f in os.listdir(d):
        if os.path.isdir(os.path.join(d, f)):
            files.append(f)
        elif f[-3:] == '.py' and f != '__init__.py':
            files.append(f[:-3])
    return files
    
def getAtlasClass(modName):
    mod = __import__('lib.analysis.atlas.'+modName, fromlist=['*'])
    cls = getattr(mod, modName)
    #print id(cls)
    return cls

def load(modName, host):
    cls = getModuleClass(modName)
    return cls(host)
