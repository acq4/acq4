from acq4.modules.Module import Module
from acq4.util import Qt


class CCFViewer(Module):
    """Displays data from Allen Institute Common Coordinate Framework (CCF).

    Requires aiccf, which is available at github.com/AllenInstitute/ccfviewer

    This is mainly used for looking at virtual slices of the mouse brain
    to determine optimal slicing angles, and for estimating the anatomical
    location of a slice from images. 
    """
    moduleDisplayName = "CCF Viewer"
    moduleCategory = "Utilities"

    def __init__(self, manager, name, config):
        from aiccf.data import CCFAtlasData
        from aiccf.viewer import AtlasViewer

        Module.__init__(self, manager, name, config) 
        self.man = manager
        self.win = AtlasViewer()
        self.win.show()
        self.win.setWindowTitle(name)

        resolution = config.get('resolution', None)
        self.atlas_data = CCFAtlasData(resolution=resolution)
        
        self.win.set_data(self.atlas_data)
