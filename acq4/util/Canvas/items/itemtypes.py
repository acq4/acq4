from collections import OrderedDict

_itemTypes = OrderedDict()

def registerItemType(typ):
    global _itemTypes
    _itemTypes[typ.__name__] = typ

def listItems():
    global _itemTypes
    return list(_itemTypes.values())

def getItemType(typ):
    global _itemTypes
    return _itemTypes[typ]
