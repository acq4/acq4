"""Given a z-stack MetaArray, find the surface of the sample."""
import sys

import numpy as np

from acq4.devices.Camera.frame import Frame
from acq4.util.DataManager import getFileHandle
from acq4.util.surface import find_surface


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f'Usage: {sys.argv[0]} ZSTACK_FILENAME.MA')
        sys.exit(1)
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
        surface_idx = find_surface(z_stack)
        if surface_idx is not None:
            print(f"Depth of surface {z_stack[surface_idx].info()['Depth']}")
    else:  # not a true z-stack
        info = fh.info().deepcopy()
        info['region'] = [0, 0, stack_arr.shape[0], stack_arr.shape[1]]
        info['binning'] = [1, 1]
        info['deviceTransform'] = None
        for f in stack_arr:
            frame = Frame(f, info)
            z_stack.append(frame)
        surface_idx = find_surface(z_stack)
    print(f'Surface at {surface_idx}')
