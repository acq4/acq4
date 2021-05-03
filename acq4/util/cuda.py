from functools import lru_cache

from acq4 import getManager
import pyqtgraph as pg

try:
    import cupy
    cupyLibraryAvailable = True
except ImportError:
    cupy = None
    cupyLibraryAvailable = False


@lru_cache()
def shouldUseCuda():
    useCuda = cupyLibraryAvailable and getManager().config.get("cudaImageProcessing", False)
    if useCuda:
        pg.setConfigOption("useCupy", True)
    return useCuda
