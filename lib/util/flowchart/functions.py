# -*- coding: utf-8 -*-
from Node import *

class AddNode(Node):
    nodeName = 'Add'
    desc = 'Returns A + B. Does not check input types.'
    
    def __init__(self):
        Node.__init__(self, "Add", terminals={
            'A': ('in',),
            'B': ('in',),
            'Sum': ('out',)
        })
        
    def process(self, **args):
        return args['A'] + args['B']
        
NODE_LIST = []
for o in locals().values():
    if type(o) is type(AddNode) and issubclass(o, Node) and o is not Node:
        NODE_LIST.append((o.nodeName, o))
NODE_LIST.sort(lambda a,b: cmp(a[0], b[0]))
