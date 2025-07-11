import weakref

class Weakref:
    """Weak reference to an object or None.
    
    If the reference is dead, return *default* instead."""
    def __init__(self, obj, default=None):
        self.default = default
        if obj is None:
            self._ref = None
        else:
            self._ref = weakref.ref(obj)

    def __call__(self):
        if self._ref is None:
            return None
        else:
            obj = self._ref()
            if obj is None:
                return self.default
            else:
                return obj
