from typing import Callable, Optional

import numpy as np
from MetaArray import MetaArray

import pyqtgraph as pg
from acq4.util.imaging.background import remove_background_from_image
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

    @classmethod
    def ensureTransform(cls, frame):
        # Complete transform maps from image coordinates to global.
        if 'transform' not in frame.info():
            frame.addInfo(transform=SRTTransform3D(frame.deviceTransform() * frame.frameTransform()))

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

    def addInfo(self, info: "dict|None" = None, **kwargs):
        if info is not None:
            self._info.update(info)
        self._info.update(kwargs)

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

    @property
    def time(self):
        return self._info['time']

    @property
    def depth(self):
        return self.mapFromFrameToGlobal(pg.Vector(0, 0, 0)).z()

    def saveImage(self, dh, filename=None, appendTo=None, appendAxis=None, autoIncrement=True):
        """Save this frame data to *filename* inside DirHandle *dh*.

        The file name must end with ".ma" (for MetaArray) or any supported image file extension.

        If *appendTo* is not None, the file will be appended to *appendTo* along the *appendAxis*, which
        value we will supply from this object (e.g. "Depth" goes to `self.depth`).
        """
        data = self.getImage()
        info = self.info()
        if callable(info.get('backgroundInfo')):
            info['backgroundInfo'] = info['backgroundInfo'](dh)
        if filename and not filename.endswith('.ma'):
            return dh.writeFile(data, filename, info, fileType="ImageFile", autoIncrement=autoIncrement)

        if appendAxis:
            array_info = [
                {'name': appendAxis, 'values': [getattr(self, appendAxis.lower())]},
                {'name': 'X'},
                {'name': 'Y'},
            ]
            data = MetaArray(data[np.newaxis, ...], info=array_info)

            if appendTo:
                data.write(appendTo.name(), appendAxis=appendAxis)
                return appendTo

        return dh.writeFile(
            data, filename, info, fileType="MetaArray", autoIncrement=autoIncrement, appendAxis=appendAxis
        )

    def loadLinkedFiles(self, dh):
        """Load linked files from the same directory as the main file."""
        bg_removal = self.info().get("backgroundInfo", None)
        if bg_removal is not None:
            self._bg_removal = dh[bg_removal]

    def imageItem(self) -> ImageItem:
        """
        Return an ImageItem suitable for pinning. This can apply background removal and contrast control if those
        were saved with the frame (see loadLinkedFiles).
        """
        data = self.getImage()
        if self._bg_removal is not None:
            bg_info = self._bg_removal.info()
            data = remove_background_from_image(
                data,
                self._bg_removal.read(),
                subtract=bg_info.get("subtract"),
                divide=bg_info.get("divide"),
            )
        levels = None
        lut = None
        contrast = self.info().get("contrastInfo", None)
        if contrast is not None and not isinstance(contrast, str):  # str was old format
            levels = contrast["levels"]
            gradient = pg.GradientEditorItem()
            gradient.restoreState(contrast["gradient"])
            lut = gradient.getLookupTable(256 if data.dtype == np.uint8 else 512)
        item = ImageItem(data, levels=levels, lut=lut, removable=True)
        item.setTransform(self.globalTransform().as2D())
        return item
