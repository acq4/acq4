# -*- coding: utf-8 -*-
"""
advancedTypes.py - Basic data structures not included with python 
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.

Includes:
    - CaselessDict - Case-insensitive dict
    - ProtectedDict/List/Tuple - Deeply read-only versions of these builtins
"""
from __future__ import print_function

import copy
from collections.abc import Sequence


## Template methods
def wrapMethod(methodName):
    return lambda self, *a, **k: getattr(self._data_, methodName)(*a, **k)


def protectMethod(methodName):
    return lambda self, *a, **k: protect(getattr(self._data_, methodName)(*a, **k))


class ProtectedDict(dict):
    """
    A class allowing read-only 'view' of a dict. 
    The object can be treated like a normal dict, but will never modify the original dict it points to.
    Any values accessed from the dict will also be read-only.
    """

    def __init__(self, data):
        self._data_ = data

    ## List of methods to directly wrap from _data_
    wrapMethods = ['__contains__', '__eq__', '__format__', '__ge__', '__gt__', '__le__', '__len__', '__lt__',
                   '__ne__', '__reduce__', '__reduce_ex__', '__repr__', '__str__', 'count', 'has_key', 'iterkeys',
                   'keys', ]

    ## List of methods which wrap from _data_ but return protected results
    protectMethods = ['__getitem__', '__iter__', 'get', 'items', 'values']

    ## List of methods to disable
    disableMethods = ['__delitem__', '__setitem__', 'clear', 'pop', 'popitem', 'setdefault', 'update']

    def error(self, *args, **kargs):
        raise Exception("Can not modify read-only list.")

    ## Directly (and explicitly) wrap some methods from _data_
    ## Many of these methods can not be intercepted using __getattribute__, so they
    ## must be implemented explicitly
    for methodName in wrapMethods:
        locals()[methodName] = wrapMethod(methodName)

    ## Wrap some methods from _data_ with the results converted to protected objects
    for methodName in protectMethods:
        locals()[methodName] = protectMethod(methodName)

    ## Disable any methods that could change data in the list
    for methodName in disableMethods:
        locals()[methodName] = error

    ## Add a few extra methods.
    def copy(self):
        raise Exception("It is not safe to copy protected dicts! (instead try deepcopy, but be careful.)")

    def itervalues(self):
        for v in self._data_.values():
            yield protect(v)

    def iteritems(self):
        for k, v in self._data_.items():
            yield (k, protect(v))

    def deepcopy(self):
        return copy.deepcopy(self._data_)

    def __deepcopy__(self, memo):
        return copy.deepcopy(self._data_, memo)


class ProtectedList(Sequence):
    """
    A class allowing read-only 'view' of a list or dict. 
    The object can be treated like a normal list, but will never modify the original list it points to.
    Any values accessed from the list will also be read-only.
    
    Note: It would be nice if we could inherit from list or tuple so that isinstance checks would work.
          However, doing this causes tuple(obj) to return unprotected results (importantly, this means
          unpacking into function arguments will also fail)
    """

    def __init__(self, data):
        self._data_ = data
        # self.__mro__ = (ProtectedList, object)

    ## List of methods to directly wrap from _data_
    wrapMethods = ['__contains__', '__eq__', '__format__', '__ge__', '__gt__', '__le__', '__len__', '__lt__', '__ne__',
                   '__reduce__', '__reduce_ex__', '__repr__', '__str__', 'count', 'index']

    ## List of methods which wrap from _data_ but return protected results
    protectMethods = ['__getitem__', '__getslice__', '__mul__', '__reversed__', '__rmul__']

    ## List of methods to disable
    disableMethods = ['__delitem__', '__delslice__', '__iadd__', '__imul__', '__setitem__', '__setslice__', 'append',
                      'extend', 'insert', 'pop', 'remove', 'reverse', 'sort']

    def error(self, *args, **kargs):
        raise Exception("Can not modify read-only list.")

    ## Directly (and explicitly) wrap some methods from _data_
    ## Many of these methods can not be intercepted using __getattribute__, so they
    ## must be implemented explicitly
    for methodName in wrapMethods:
        locals()[methodName] = wrapMethod(methodName)

    ## Wrap some methods from _data_ with the results converted to protected objects
    for methodName in protectMethods:
        locals()[methodName] = protectMethod(methodName)

    ## Disable any methods that could change data in the list
    for methodName in disableMethods:
        locals()[methodName] = error

    ## Add a few extra methods.
    def __iter__(self):
        for item in self._data_:
            yield protect(item)

    def __add__(self, op):
        if isinstance(op, ProtectedList):
            return protect(self._data_.__add__(op._data_))
        elif isinstance(op, list):
            return protect(self._data_.__add__(op))
        else:
            raise TypeError("Argument must be a list.")

    def __radd__(self, op):
        if isinstance(op, ProtectedList):
            return protect(op._data_.__add__(self._data_))
        elif isinstance(op, list):
            return protect(op.__add__(self._data_))
        else:
            raise TypeError("Argument must be a list.")

    def deepcopy(self):
        return copy.deepcopy(self._data_)

    def __deepcopy__(self, memo):
        return copy.deepcopy(self._data_, memo)

    def poop(self):
        raise Exception("This is a list. It does not poop.")


class ProtectedTuple(Sequence):
    """
    A class allowing read-only 'view' of a tuple.
    The object can be treated like a normal tuple, but its contents will be returned as protected objects.
    
    Note: It would be nice if we could inherit from list or tuple so that isinstance checks would work.
          However, doing this causes tuple(obj) to return unprotected results (importantly, this means
          unpacking into function arguments will also fail)
    """

    def __init__(self, data):
        self._data_ = data

    ## List of methods to directly wrap from _data_
    wrapMethods = ['__contains__', '__eq__', '__format__', '__ge__', '__getnewargs__', '__gt__', '__hash__', '__le__',
                   '__len__', '__lt__', '__ne__', '__reduce__', '__reduce_ex__', '__repr__', '__str__', 'count',
                   'index']

    ## List of methods which wrap from _data_ but return protected results
    protectMethods = ['__getitem__', '__getslice__', '__iter__', '__add__', '__mul__', '__reversed__', '__rmul__']

    ## Directly (and explicitly) wrap some methods from _data_
    ## Many of these methods can not be intercepted using __getattribute__, so they
    ## must be implemented explicitly
    for methodName in wrapMethods:
        locals()[methodName] = wrapMethod(methodName)

    ## Wrap some methods from _data_ with the results converted to protected objects
    for methodName in protectMethods:
        locals()[methodName] = protectMethod(methodName)

    ## Add a few extra methods.
    def deepcopy(self):
        return copy.deepcopy(self._data_)

    def __deepcopy__(self, memo):
        return copy.deepcopy(self._data_, memo)


def protect(obj):
    if isinstance(obj, dict):
        return ProtectedDict(obj)
    elif isinstance(obj, list):
        return ProtectedList(obj)
    elif isinstance(obj, tuple):
        return ProtectedTuple(obj)
    else:
        return obj


if __name__ == '__main__':
    d = {'x': 1, 'y': [1, 2], 'z': ({'a': 2, 'b': [3, 4], 'c': (5, 6)}, 1, 2)}
    dp = protect(d)

    l = [1, 'x', ['a', 'b'], ('c', 'd'), {'x': 1, 'y': 2}]
    lp = protect(l)

    t = (1, 'x', ['a', 'b'], ('c', 'd'), {'x': 1, 'y': 2})
    tp = protect(t)
