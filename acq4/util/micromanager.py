# -*- coding: utf-8 -*-
from __future__ import print_function
import os, sys
from acq4.util.Mutex import Mutex

# singleton MMCorePy instance
_mmc = None

# default location to search for micromanager
microManagerPath = 'C:\\Program Files\\Micro-Manager-1.4'
microManagerPath = 'C:\\Program Files\\Micro-Manager-2.0gamma'


USES_PYMMCORE = False
USES_MMCOREPY = False


def getMMCorePy(path=None):
    """Return a singleton MMCorePy instance that is shared by all devices for accessing micromanager.
    """
    global _mmc, USES_MMCOREPY, USES_PYMMCORE
    if _mmc is None:
        try:
            import pymmcore
            USES_PYMMCORE = True
            _mmc = pymmcore.CMMCore()
            _mmc.setDeviceAdapterSearchPaths([microManagerPath])
        except ImportError:

            try:
                import MMCorePy
                USES_MMCOREPY = True
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
                    USES_MMCOREPY = True
                finally:
                    sys.path.pop()

            _mmc = MMCorePy.CMMCore()

    return _mmc
