"""Given a z-stack MetaArray, find the surface of the sample."""
import sys
from typing import Tuple
import numpy as np
import scipy.ndimage
import cv2 as cv
import matplotlib.pyplot as mpl
from MetaArray import MetaArray

from acq4.devices.Camera.frame import Frame
from acq4.util.DataManager import getFileHandle
from acq4.util.surface import find_surface

# def find_surface(z_stack: np.ndarray) -> [int, None]:
#     """Find the surface of the sample based on how focused the images are."""
#
#     def center_area(img: np.ndarray) -> Tuple[slice, slice]:
#         """Return a slice that selects the center of the image."""
#         minimum = 50
#         center_w = img.shape[0] // 2
#         start_w = max(min(int(img.shape[0] * 0.4), center_w - minimum), 0)
#         end_w = max(min(int(img.shape[0] * 0.6), center_w + minimum), img.shape[0])
#         center_h = img.shape[1] // 2
#         start_h = max(min(int(img.shape[1] * 0.4), center_h - minimum), 0)
#         end_h = max(min(int(img.shape[1] * 0.6), center_h + minimum), img.shape[1])
#         return (slice(start_w, end_w), slice(start_h, end_h))
#
#     def downsample(arr, n):
#         new_shape = n * (np.array(arr.shape[1:]) / n).astype(int)
#         clipped = arr[:, :new_shape[0], :new_shape[1]]
#         mean1 = clipped.reshape(clipped.shape[0], clipped.shape[1], clipped.shape[2]//n, n).mean(axis=3)
#         mean2 = mean1.reshape(mean1.shape[0], mean1.shape[1]//n, n, mean1.shape[2]).mean(axis=2)
#         return mean2
#
#     def calculate_focus_score(image):
#         """Denoise the image and calculate the focus score."""
#         # image += np.random.normal(size=image.shape, scale=100)
#         image = scipy.ndimage.laplace(image) / np.mean(image)
#         return image.var()
#
#     # normalized = (255 * (z_stack - np.min(z_stack, axis=0)) / np.max(z_stack, axis=0)).astype(np.uint8)
#     filtered = downsample(z_stack, 5)
#     centers = filtered[(..., *center_area(filtered[0]))]
#     scored = np.array([calculate_focus_score(img) for img in centers])
#     # mpl.plot(scored)
#     # mpl.show()
#     surface = np.argmax(scored > 0.005)
#     if surface == 0:
#         return None
#     return surface

# def calculate_focus_score(image):
#    """Denoise the image and calculate the focus score."""
# #    image_filtered = cv.medianBlur(image, 9)
#    image_filtered = cv.GaussianBlur(image, (5, 5), 0)
#    laplacian = cv.Laplacian(image_filtered, cv.CV_64F)
#    focus_score = laplacian.var()
#    return focus_score


# def find_surface(z_stack: np.ndarray) -> int:
#     """Find the surface of the sample based on how focused the images are."""
#     normalized = (255 * (z_stack - np.min(z_stack, axis=0)) / np.max(z_stack, axis=0)).astype(np.uint8)
#     scored = [calculate_focus_score(img) for img in normalized]
#     mpl.plot(scored)
#     mpl.show()
#     # laplacian = np.abs(np.gradient(normalized, axis=0))
#     surface = np.argmax(scored)
#     return surface


if __name__ == '__main__':
    filename = sys.argv[1]
    fh = getFileHandle(filename)
    stack_arr = fh.read()
    z_stack = []
    if "Depth" in stack_arr.listColumns():
        for i, depth in enumerate(stack_arr.xvals("Depth")):
            info = fh.info().deepcopy()
            info['Depth'] = depth
            frame = Frame(stack_arr["Depth": i], info)
            tr = frame.globalTransform()
            current_depth = tr.map(np.array([0, 0, 0]))[2]
            tr.translate(0, 0, current_depth - depth)
            frame._info['transform'] = tr
            z_stack.append(frame)
    else:  # not a true z-stack
        info = fh.info().deepcopy()
        info['region'] = [0, 0, stack_arr.shape[0], stack_arr.shape[1]]
        info['binning'] = [1, 1]
        info['deviceTransform'] = None
        for f in stack_arr:
            frame = Frame(f, info)
            z_stack.append(frame)
    surface_idx = find_surface(z_stack)
    print(f'Surface found at {surface_idx}')
    # if surface_idx is not None:
    #     cv.imshow('Surface', z_stack[surface_idx].data())
