from typing import Optional

import numpy as np
import scipy.ndimage


def remove_background_from_image(
    image: np.ndarray, bg: Optional[np.ndarray], subtract: bool = True, divide: bool = False, blur: float = 0.0
):
    if bg is None:
        return image
    if blur > 0.0:
        bg = scipy.ndimage.gaussian_filter(bg, (blur, blur))
    if divide:
        return image / bg
    if subtract:
        return image - bg
    return image
