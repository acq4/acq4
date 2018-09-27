# -*- coding: utf-8 -*-
from __future__ import print_function
import os, sys
from acq4.util.Mutex import Mutex

# singleton MMCorePy instance
_mmc = None

# default location to search for micromanager
microManagerPath = 'C:\\Program Files\\Micro-Manager-1.4'


def getMMCorePy(path=None):
    """Return a singleton MMCorePy instance that is shared by all devices for accessing micromanager.
    """
    global _mmc
    if _mmc is None:
        try:
            global MMCorePy
            import MMCorePy
        except ImportError:
            if sys.platform != 'win32':
                raise
            # MM does not install itself to standard path. User should take care of this,
            # but we can make a guess..
            if path is None:
                path = microManagerPath
            sys.path.append(path)
            os.environ['PATH'] = os.environ['PATH'] + ';' + path
            try:
                import MMCorePy
            finally:
                sys.path.pop()

        _mmc = MMCorePy.CMMCore()

    return _mmc
