# -*- coding: utf-8 -*-
from advancedTypes import OrderedDict
import os, types
from debug import printExc
from ..Node import Node
dn = os.path.dirname(os.path.abspath(__file__))


def isNodeClass(cls):
    try:
        if not issubclass(cls, Node):
            return False
    except:
        return False
    return hasattr(cls, 'nodeName')

def loadLibrary(reloadLibs=False):
    global NODE_LIST, NODE_TREE
    NODE_LIST = []
    NODE_TREE = OrderedDict()
        
    for f in os.listdir(dn):
        name, ext = os.path.splitext(f)
        if ext != '.py':
            continue
        try:
            mod = __import__(name, globals(), locals())
            if reloadLibs:
                reload(mod)
        except:
            printExc("Error loading flowchart library %s:" % name)
            continue
        nodes = []
        for n in dir(mod):
            o = getattr(mod, n)
            if isNodeClass(o):
                nodes.append((o.nodeName, o))
        if len(nodes) > 0:
            NODE_TREE[name] = OrderedDict(nodes)
            NODE_LIST.extend(nodes)
    NODE_LIST = OrderedDict(NODE_LIST)
    
def reloadLibrary():
    loadLibrary(reloadLibs=True)
    
loadLibrary()
#NODE_LIST = []
#for o in locals().values():
    #if type(o) is type(AddNode) and issubclass(o, Node) and o is not Node and hasattr(o, 'nodeName'):
            #NODE_LIST.append((o.nodeName, o))
#NODE_LIST.sort(lambda a,b: cmp(a[0], b[0]))
#NODE_LIST = OrderedDict(NODE_LIST)