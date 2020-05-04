from __future__ import print_function
import scipy.optimize, scipy.ndimage
import numpy as np
from acq4.util.image_registration import iterativeImageTemplateMatch
import pyqtgraph as pg


class PipetteDetector(object):
    def __init__(self, reference):
        self.reference = reference
        self._filtered_ref = None
        
    @property
    def filtered_ref(self):
        """The reference image data passed through the preprocessing filter.
        """
        if self._filtered_ref is None:
            self._filtered_ref = [self.filterImage(f) for f in self.reference['frames']]
        return self._filtered_ref

    def findPipette(self, frame, minImgPos, maxImgPos, expectedPos, bg_frame=None):
        """Detect the pipette tip in *frame* and return the physical location.

        The *frame* is an instance of util.imaging.Frame that carries a transform mapping
        from image pixels to the physical coordinate system.

        *minImgPos* and *maxImgPos* provide a suggested image cropping region that may
        be used to reduce the search area.

        *expectedPos* is the _expected_ position of the pipette tip.

        An optional *bg_frame* may be provided that shows the same field of view with no pipette.

        Returns an (x,y,z) tuple giving the physical coordinate location of the pipette tip
        and a measure of the detection performance that can be used to determine whether the detection
        failed.
        """
        reference = self.reference
        img = frame.data()

        # if a background frame was provided, subtract it out
        if bg_frame is not None:
            img = img.astype(int) - bg_frame.data()
        
        # crop out a small region around the pipette tip
        if img.ndim == 3:
            img = img[0]
        img = img[minImgPos[0]:maxImgPos[0], minImgPos[1]:maxImgPos[1]]

        # filter the image
        img = self.filterImage(img)

        # resample acquired image to match template pixel size
        pxr = frame.info()['pixelSize'][0] / reference['pixelSize'][0]
        if pxr != 1.0:
            img = scipy.ndimage.zoom(img, pxr)

        # measure image pixel offset and z error to pipette tip
        xyOffset, zErr, performance = self.estimateOffset(img)

        # map pixel offsets back to physical coordinates
        tipImgPos = (
            minImgPos[0] + (xyOffset[0] + reference['centerPos'][0]) / pxr, 
            minImgPos[1] + (xyOffset[1] + reference['centerPos'][1]) / pxr
        )
        tipPos = frame.mapFromFrameToGlobal(pg.Vector(tipImgPos))

        return (tipPos.x(), tipPos.y(), tipPos.z() + zErr), performance

    def estimateOffset(self, img):
        """Given an image containing a pipette, return the most likely tip position
        and a measure of the performance of the algorithm.

        Returns
        -------
        xyOffset : (int, int)
            The pixel offset relative to image origin where the pipette tip was detected
        zOffset : float
            Estimate of the pipette tip distance from the image focal plane (in meters)
        performance : float
            Relative measure of detection performance
        """
        raise NotImplementedError()

    def filterImage(self, img):
        """Preprocess *img* and return the result.
        """
        raise NotImplementedError()


class TemplateMatchPipetteDetector(PipetteDetector):
    def __init__(self, reference):
        PipetteDetector.__init__(self, reference)

    def estimateOffset(self, img, show=False):
        reference = self.reference

        # run template match against all template frames
        match = [iterativeImageTemplateMatch(img, t) for t in self.filtered_ref]

        if show:
            pg.plot([m[0][0] for m in match], title='x match vs z')
            pg.plot([m[0][1] for m in match], title='y match vs z')
            pg.plot([m[1] for m in match], title='match correlation vs z')

        # find frame with best match
        maxInd = np.argmax([m[1] for m in match])

        # estimate z error in meters from focal plane
        zErr = (maxInd - reference['centerInd']) * reference['zStep']

        # xy offset in pixels from image origin
        xyOffset = match[maxInd][0]

        return xyOffset, zErr, match[maxInd][1]

    def filterImage(self, img):
        # Sobel should reduce background artifacts, but it also seems to increase the noise in the signal
        # itself--two images with slightly different focus can have a very bad match.
        # import skimage.feature
        # return skimage.filter.sobel(img)
        img = scipy.ndimage.morphological_gradient(img, size=(3, 3))
        return img
