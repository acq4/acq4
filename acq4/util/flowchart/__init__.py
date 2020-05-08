from __future__ import print_function

import os
from importlib import import_module

from pyqtgraph import reload
## Extend pyqtgraph.flowchart by adding several specialized nodes
from pyqtgraph.flowchart import *
from pyqtgraph.flowchart.library import isNodeClass
from acq4.util.debug import printExc


def loadLibrary(reloadLibs=False):
    global NODE_LIST, NODE_TREE

    libPath = os.path.dirname(os.path.abspath(__file__))

    if reloadLibs:
        reload.reloadAll(libPath)

    for f in os.listdir(libPath):
        pathName, ext = os.path.splitext(f)
        if ext != '.py' or '__init__' in pathName or '__main__' in pathName:
            continue
        try:
            mod = import_module(".{}".format(pathName), package="acq4.util.flowchart")
            # mod = __import__('.' + pathName, globals(), locals())
        except:
            printExc("Error loading flowchart library %s:" % pathName)
            continue

        for n in dir(mod):
            o = getattr(mod, n)
            if isNodeClass(o):
                registerNodeType(o, [(pathName,)], override=reloadLibs)


loadLibrary()
