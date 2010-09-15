# -*- coding: utf-8 -*-
from numpy import ndarray, bool_

def eq(a, b):
    """The great missing equivalence function: Guaranteed evaluation to a single bool value."""
    try:
        e = a==b
    except ValueError:
        return False
    t = type(e)
    if t is bool:
        return e
    elif t is bool_:
        return bool(e)
    elif isinstance(e, ndarray):
        return e.all()
    else:
        raise Exception("== operator returned type %s" % str(type(e)))
