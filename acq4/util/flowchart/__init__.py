from acq4.pyqtgraph.flowchart import *
from acq4.pyqtgraph.flowchart.library import registerNodeType, isNodeClass
import os

## Extend pyqtgraph.flowchart by adding several specialized nodes

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
            #print "importing from", f
            mod = __import__(pathName, globals(), locals())
        except:
            printExc("Error loading flowchart library %s:" % pathName)
            continue
        
        nodes = []
        for n in dir(mod):
            o = getattr(mod, n)
            if isNodeClass(o):
                #print "  ", str(o)
                registerNodeType(o, [(pathName,)], override=reloadLibs)

loadLibrary()