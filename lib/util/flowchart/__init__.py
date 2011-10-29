from pyqtgraph.flowchart import *
from pyqtgraph.flowchart.library import loadLibrary
import os

def loadLibrary(reloadLibs=False, libPath=None):
    import traceback
    traceback.print_stack()

    global NODE_LIST, NODE_TREE
    if libPath is None:
        libPath = os.path.dirname(os.path.abspath(__file__))
    print "loadLibrary", libPath
    
    if reloadLibs:
        reload.reloadAll(libPath)
    
    for f in os.listdir(libPath):
        pathName, ext = os.path.splitext(f)
        if ext != '.py' or '__init__' in pathName:
            continue
        try:
            print "importing from", f
            mod = __import__(pathName, globals(), locals())
        except:
            printExc("Error loading flowchart library %s:" % pathName)
            continue
        
        nodes = []
        for n in dir(mod):
            o = getattr(mod, n)
            if isNodeClass(o):
                print "  ", str(o)
                registerNodeType(o, [(pathName,)], override=reloadLibs)
                #nodes.append((o.nodeName, o))
        #if len(nodes) > 0:
            #NODE_TREE[name] = OrderedDict(nodes)
            #NODE_LIST.extend(nodes)
    #NODE_LIST = OrderedDict(NODE_LIST)
