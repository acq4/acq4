# -*- coding: utf-8 -*-
from __future__ import print_function
import os

def listModels():
    d = os.path.split(__file__)[0]
    files = []
    for f in os.listdir(d):
        if os.path.isdir(os.path.join(d, f)):
            files.append(f)
        elif f[-3:] == '.py' and f != '__init__.py':
            files.append(f[:-3])
    return files
    
#def getModelClass(modName):
    #mod = __import__('acq4.analysis.dataModels.'+modName, fromlist=['*'])
    #cls = getattr(mod, 'DataModel')
    #return cls

def loadModel(modName):
    #cls = getModelClass(modName)
    #return cls()
    return __import__('acq4.analysis.dataModels.'+modName, fromlist=['*'])