from __future__ import print_function
from collections import OrderedDict

_itemTypes = OrderedDict()

def itemTypes():
    global _itemTypes
    return _itemTypes

def registerItemType(typ):
    global _itemTypes
    _itemTypes[typ.__name__] = typ

def listItemTypes():
    global _itemTypes
    return list(_itemTypes.values())

def getItemType(typ):
    global _itemTypes
    return _itemTypes[typ]
