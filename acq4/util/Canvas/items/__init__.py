# -*- coding: utf-8 -*-
import os, inspect
from .CanvasItem import CanvasItem
#import acq4.pyqtgraph.canvas.items as items

def listMods():
    d = os.path.split(__file__)[0]
    files = []
    for f in os.listdir(d):
        if os.path.isdir(os.path.join(d, f)):
            files.append(f)
        elif f[-3:] == '.py' and f != '__init__.py':
            files.append(f[:-3])
    return files

#_ITEMLIST_ = items.listItems()  ## get original list of items from acq4.pyqtgraph.canvas
_ITEMLIST_ = []

## add our custom items to the list
for i in listMods():
    mod = __import__(i, globals(), locals())
    for k in dir(mod):
        o = getattr(mod, k)
        if inspect.isclass(o) and issubclass(o, CanvasItem) and o not in _ITEMLIST_:
            locals()[k] = o
            _ITEMLIST_.append(o)

def listItems():
    return _ITEMLIST_[:]
