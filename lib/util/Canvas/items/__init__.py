# -*- coding: utf-8 -*-
import os, inspect
from CanvasItem import CanvasItem

def listMods():
    d = os.path.split(__file__)[0]
    files = []
    for f in os.listdir(d):
        if os.path.isdir(os.path.join(d, f)):
            files.append(f)
        elif f[-3:] == '.py' and f != '__init__.py':
            files.append(f[:-3])
    return files

_ITEMLIST_ = []
for i in listMods():
    mod = __import__(i, globals(), locals())
    for k in dir(mod):
        o = getattr(mod, k)
        if inspect.isclass(o) and issubclass(o, CanvasItem):
            locals()[k] = o
            _ITEMLIST_.append(o)
            
def listItems():
    return _ITEMLIST_[:]
    