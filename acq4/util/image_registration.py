import numpy as np
import scipy.ndimage
import pyqtgraph as pg


def imageTemplateMatch(img, template, unsharp=3):
    """Use skimage.feature.match_template to find the offset between *img* and *template* that yields the best registration.

    Returns
    -------
    pos : tuple
        The offset with best registration
    val : float
        Measure of template match performance at *pos*; may be used to compare multiple results
    cc : array
        The image showing template match values across all tested offsets
    """
    import skimage.feature
    if img.shape[0] < template.shape[0] or img.shape[1] < template.shape[1]:
        raise ValueError("Image must be larger than template.  %s %s" % (img.shape, template.shape))
    cc = skimage.feature.match_template(img, template)
    # high-pass filter; we're looking for a fairly sharp peak.
    if unsharp is not False:
        cc_filt = cc - scipy.ndimage.gaussian_filter(cc, (unsharp, unsharp))
    else:
        cc_filt = cc

    ind = np.argmax(cc_filt)
    pos = np.unravel_index(ind, cc.shape)
    val = cc[pos[0], pos[1]]
    return pos, val, cc


def iterativeImageTemplateMatch(img, template, dsVals=(4, 2, 1), matchFn=imageTemplateMatch):
    """Match a template to image data iteratively using successively higher resolutions.

    Return the (x, y) pixel offset of the template and a value indicating the strength of the match.

    For efficiency, the input images are downsampled and matched at low resolution before
    iteratively re-matching at higher resolutions. The *dsVals* argument lists the downsampling values
    that will be used, in order. Each value in this list must be an integer multiple of
    the value that follows it.
    """
    imgDs = [pg.downsample(pg.downsample(img, n, axis=0), n, axis=1) for n in dsVals]
    tmpDs = [pg.downsample(pg.downsample(template, n, axis=0), n, axis=1) for n in dsVals]
    offset = np.array([0, 0])
    for i, ds in enumerate(dsVals):
        pos, val, cc = matchFn(imgDs[i], tmpDs[i])
        pos = np.array(pos)
        if i == len(dsVals) - 1:
            offset += pos
            return offset, val
        else:
            scale = ds // dsVals[i+1]
            assert scale == ds / dsVals[i+1], "dsVals must satisfy constraint: dsVals[i] == dsVals[i+1] * int(x)"
            offset *= scale
            offset += np.clip(((pos-1) * scale), 0, imgDs[i+1].shape)
            end = offset + np.array(tmpDs[i+1].shape) + 3
            end = np.clip(end, 0, imgDs[i+1].shape)
            imgDs[i+1] = imgDs[i+1][offset[0]:end[0], offset[1]:end[1]]
