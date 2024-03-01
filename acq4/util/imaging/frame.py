from typing import Callable

import numpy as np

from acq4.util.imaging.bg_subtract_ctrl import remove_background_from_image
import pyqtgraph as pg
from pyqtgraph import SRTTransform3D, ImageItem


class Frame(object):
    """One or more frames of imaging data, including meta information.

    Expects *info* to be a dictionary with some minimal information:

    * 'frameTransform' maps from the image coordinates (0,0 at top-left) to
      the coordinate system of the imaging device.
    * 'deviceTransform' maps from the coordinate system of the imaging device to
      global coordinates.
    """

    def __init__(self, data, info):
        object.__init__(self)
        self._data = data
        self._info = info
        self._bg_removal = None
        # Complete transform maps from image coordinates to global.
        if 'transform' not in info:
            info['transform'] = SRTTransform3D(self.deviceTransform() * self.frameTransform())

    def asarray(self):
        """Assuming this frame object represents multiple frames, return an array with one Frame per frame
        """
        return [Frame(frame, self.info().copy()) for frame in self.data()]

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
    
    def saveImage(self, dh, filename, backgroundControl: Callable = None, contrastControl=None):
        """Save this frame data to *filename* inside DirHandle *dh*.

        The file name must end with ".ma" (for MetaArray) or any supported image file extension.
        """
        data = self.getImage()
        info = self.info()
        if backgroundControl is not None:
            bg = backgroundControl(dh)
            if bg is not None:
                info['backgroundControl'] = bg
        if contrastControl is not None:
            info['contrastControl'] = contrastControl

        if filename.endswith('.ma'):
            return dh.writeFile(data, filename, info, fileType="MetaArray", autoIncrement=True)
        else:
            return dh.writeFile(data, filename, info, fileType="ImageFile", autoIncrement=True)

    def loadLinkedFiles(self, dh):
        """Load linked files from the same directory as the main file."""
        bg_removal = self.info().get("backgroundControl", None)
        if bg_removal is not None:
            self._bg_removal = dh[bg_removal]

    def imageItem(self) -> ImageItem:
        """
        Return an ImageItem suitable for pinning.
        """
        data = self.getImage()
        if self._bg_removal is not None:
            bg_info = self._bg_removal.info()
            data = remove_background_from_image(
                data,
                self._bg_removal.read(),
                subtract=bg_info.get("subtract"),
                divide=bg_info.get("divide"),
                blur=bg_info.get("blur"),
            )
        levels = None
        lut = None
        contrast = self.info().get("contrastControl", None)
        if contrast is not None and not isinstance(contrast, str):  # str was old format
            levels = contrast["levels"]
            gradient = pg.GradientEditorItem()
            gradient.restoreState(contrast["gradient"])
            lut = gradient.getLookupTable(256 if data.dtype == np.uint8 else 512)
        item = ImageItem(data, levels=levels, lut=lut, removable=True)
        item.setTransform(self.globalTransform().as2D())
        return item
