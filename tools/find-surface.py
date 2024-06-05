"""Given a z-stack MetaArray, find the surface of the sample."""
import sys

import click
import numpy as np

import pyqtgraph as pg
from acq4.util.DataManager import getFileHandle
from acq4.util.imaging import Frame
from acq4.util.surface import find_surface, score_frames


@click.command()
@click.argument('zstack_filename')
@click.option('--graph', is_flag=True, help='Display the graph of calculated scores')
def find_surface_in_stack(zstack_filename: str, graph=False):
    fh = getFileHandle(zstack_filename)
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

    if graph:
        scores = score_frames(z_stack)
        pg.plot(scores)
        pg.exec()
    else:
        surface_idx = find_surface(z_stack)
        print(f'Surface at {surface_idx}')


if __name__ == '__main__':
    find_surface_in_stack()
