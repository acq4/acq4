# -*- coding: utf-8 -*-
from Node import *
from advancedTypes import OrderedDict

class UniOpNode(Node):
    """Generic node for performing any operation like Out = In.fn()"""
    def __init__(self, name, fn):
        self.fn = fn
        Node.__init__(self, name, terminals={
            'In': ('in',),
            'Out': ('out',)
        })
        
    def process(self, **args):
        return {'Out': getattr(args['In'], self.fn)()}

class BinOpNode(Node):
    """Generic node for performing any operation like A.fn(B)"""
    def __init__(self, name, fn):
        self.fn = fn
        Node.__init__(self, name, terminals={
            'A': ('in',),
            'B': ('in',),
            'Out': ('out',)
        })
        
    def process(self, **args):
        return {'Out': getattr(args['A'], self.fn)(args['B'])}

class AbsNode(UniOpNode):
    nodeName = 'Abs'
    desc = 'Returns abs(Inp). Does not check input types.'
    def __init__(self, name):
        UniOpNode.__init__(self, name, '__abs__')

class AddNode(BinOpNode):
    nodeName = 'Add'
    desc = 'Returns A + B. Does not check input types.'
    def __init__(self, name):
        BinOpNode.__init__(self, name, '__add__')

class SubtractNode(BinOpNode):
    nodeName = 'Subtract'
    desc = 'Returns A - B. Does not check input types.'
    def __init__(self, name):
        BinOpNode.__init__(self, name, '__sub__')

class MultiplyNode(BinOpNode):
    nodeName = 'Multiply'
    desc = 'Returns A * B. Does not check input types.'
    def __init__(self, name):
        BinOpNode.__init__(self, name, '__mul__')

class DivideNode(BinOpNode):
    nodeName = 'Divide'
    desc = 'Returns A / B. Does not check input types.'
    def __init__(self, name):
        BinOpNode.__init__(self, name, '__div__')










NODE_LIST = []
for o in locals().values():
    if type(o) is type(AddNode) and issubclass(o, Node) and o is not Node and hasattr(o, 'nodeName'):
            NODE_LIST.append((o.nodeName, o))
NODE_LIST.sort(lambda a,b: cmp(a[0], b[0]))
NODE_LIST = OrderedDict(NODE_LIST)