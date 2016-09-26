# -*- coding: utf-8 -*-
from numpy import ndarray, bool_
from ..metaarray import MetaArray

def eq(a, b):
    """The great missing equivalence function: Guaranteed evaluation to a single bool value.

    Array arguments are only considered equivalent to objects that have the same type and shape, and where
    the elementwise comparison returns true for all elements. If both arguments are arrays, then
    they must have the same shape and dtype to be considered equivalent.
    """
    if a is b:
        return True

    # Avoid comparing large arrays against scalars; this is expensive and we know it should return False.
    aIsArr = isinstance(a, (ndarray, MetaArray))
    bIsArr = isinstance(b, (ndarray, MetaArray))
    if (aIsArr or bIsArr) and type(a) != type(b):
        return False

    # If both inputs are arrays, we can speeed up comparison if shapes / dtypes don't match
    # NOTE: arrays of dissimilar type should be considered unequal even if they are numerically
    # equal because they may behave differently when computed on.
    if aIsArr and bIsArr and (a.shape != b.shape or a.dtype != b.dtype):
        return False

    # Test for equivalence. 
    # If the test raises a recognized exception, then return Falase
    try:
        e = a==b
    except ValueError:
        return False
    except AttributeError: 
        return False
    except:
        print("a:", str(type(a)), str(a))
        print("b:", str(type(b)), str(b))
        raise
    
    t = type(e)
    if t is bool:
        return e
    elif t is bool_:
        return bool(e)
    elif isinstance(e, ndarray) or (hasattr(e, 'implements') and e.implements('MetaArray')):
        try:   ## disaster: if a is an empty array and b is not, then e.all() is True
            if a.shape != b.shape:
                return False
        except:
            return False
        if (hasattr(e, 'implements') and e.implements('MetaArray')):
            return e.asarray().all()
        else:
            return e.all()
    else:
        raise Exception("== operator returned type %s" % str(type(e)))
            