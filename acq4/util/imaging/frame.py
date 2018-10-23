from __future__ import print_function
from acq4.pyqtgraph import Vector, SRTTransform3D


class Frame(object):
    """A single frame of imaging data including meta information.

    Expects *info* to be a dictionary with some minimal information:

    * 'frameTransform' maps from the image coordinates (0,0 at top-left) to
      the coordinate system of the imaging device.
    * 'deviceTransform' maps from the coordiante system of the imaging device to
      global coordinates.
    """

    def __init__(self, data, info):
        object.__init__(self)
        self._data = data
        self._info = info        
        ## Complete transform maps from image coordinates to global.
        if 'transform' not in info:
            info['transform'] = SRTTransform3D(self.deviceTransform() * self.frameTransform())
        
    def data(self):
        """Return raw imaging data.
        """
        return self._data
    
    def info(self):
        """Return the meta info dict for this frame.
        """
        return self._info
    
    def getImage(self):
        """Return processed image data.

        By default, this method just returns self.data().
        """
        return self._data

    def deviceTransform(self):
        """Return the transform that maps from imager device coordinates to global."""
        return SRTTransform3D(self._info['deviceTransform'])
    
    def frameTransform(self):
        """Return the transform that maps from this frame's image coordinates
        to its imager device coordinates. This transform takes into account
        the camera's region and binning settings.
        """
        return SRTTransform3D(self._info['frameTransform'])
        
    def globalTransform(self):
        """Return the transform that maps this frame's image coordinates
        to global coordinates. This is equivalent to (deviceTransform * frameTransform).
        """
        return SRTTransform3D(self._info['transform'])
        
    def mapFromFrameToGlobal(self, obj):
        """Map *obj* from the frame's data coordinates to global coordinates.
        """
        return self.globalTransform().map(obj)
    
