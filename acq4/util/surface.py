from typing import Union, Tuple

import numpy as np
import scipy

from acq4.util.imaging import Frame


def center_area(img: np.ndarray) -> Tuple[slice, slice]:
    """Return a slice that selects the center of the image."""
    minimum = 50
    center_w = img.shape[0] // 2
    start_w = max(min(int(img.shape[0] * 0.4), center_w - minimum), 0)
    end_w = max(min(int(img.shape[0] * 0.6), center_w + minimum), img.shape[0])
    center_h = img.shape[1] // 2
    start_h = max(min(int(img.shape[1] * 0.4), center_h - minimum), 0)
    end_h = max(min(int(img.shape[1] * 0.6), center_h + minimum), img.shape[1])
    return slice(start_w, end_w), slice(start_h, end_h)


def downsample(arr, n):
    new_shape = n * (np.array(arr.shape[1:]) / n).astype(int)
    clipped = arr[:, :new_shape[0], :new_shape[1]]
    mean1 = clipped.reshape(clipped.shape[0], clipped.shape[1], clipped.shape[2] // n, n).mean(axis=3)
    return mean1.reshape(mean1.shape[0], mean1.shape[1] // n, n, mean1.shape[2]).mean(axis=2)


def calculate_focus_score(image):
    # image += np.random.normal(size=image.shape, scale=100)
    image = scipy.ndimage.laplace(image) / np.mean(image)
    return image.var()


def find_surface(z_stack: list[Frame]) -> Union[int, None]:
    scored = score_frames(z_stack)
    # surface = np.argmax(scored > 0.005)  # is a threshold needed?
    surface = np.argmax(scored)
    if surface == 0:
        return

    return surface


def score_frames(z_stack: list[Frame]) -> np.ndarray:
    filtered = downsample(np.array([f.data() for f in z_stack]), 5)
    centers = filtered[(..., *center_area(filtered[0]))]
    return np.array([calculate_focus_score(img) for img in centers])
