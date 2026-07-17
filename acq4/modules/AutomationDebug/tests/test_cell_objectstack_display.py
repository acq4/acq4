"""Tests for detected cells' ObjectStacks and their cell-queue display.

Cover that a detected cell can be seeded with a tracking reference from the
detection z-stack, that the cell table reads that stack back, and that the image
view defaults to the stack's center frame.
"""

import numpy as np
import coorx
from acq4.util.imaging import Frame
from acq4_automation.feature_tracking.cell import Cell

from acq4.modules.AutomationDebug.AutomationDebug import AutomationDebugWindow


def _make_stack(n_frames=30, nrows=80, ncols=80, xy_px=1e-6, z_step=1e-6):
    frames = []
    for i in range(n_frames):
        data = np.zeros((nrows, ncols), dtype=np.float32)
        m = np.eye(4)
        m[0, 0] = xy_px
        m[1, 1] = xy_px
        m[2, 2] = z_step
        m[2, 3] = i * z_step
        xform = coorx.AffineTransform.from_matrix(
            m, from_cs=f"frame_{i}.xyz", to_cs="global"
        )
        frames.append(Frame(data, {"transform": xform, "pixelSize": (xy_px, xy_px)}))
    return frames


def test_initializeTrackerFromStack_populates_objectstack():
    cell = Cell(coorx.Point((40e-6, 40e-6, 15e-6), "global"))
    cell.initializeTrackerFromStack(None, _make_stack())

    stack = cell._tracker.motion_estimator.original_object_stack.data
    assert stack.shape == (20, 40, 40)


def test_cellInitialStack_returns_stack_for_detected_cell():
    cell = Cell(coorx.Point((40e-6, 40e-6, 15e-6), "global"))
    cell.initializeTrackerFromStack(None, _make_stack())

    stack = AutomationDebugWindow._cellInitialStack(cell)
    assert stack is not None
    assert stack.shape == (20, 40, 40)


def test_cellInitialStack_none_for_uninitialized_cell():
    cell = Cell(coorx.Point((40e-6, 40e-6, 15e-6), "global"))
    assert AutomationDebugWindow._cellInitialStack(cell) is None


def test_center_frame_index_is_middle_of_stack():
    stack = np.zeros((20, 40, 40), dtype=np.float32)
    assert AutomationDebugWindow._centerFrameIndex(stack) == 10


def test_center_frame_index_none_for_single_frame():
    assert AutomationDebugWindow._centerFrameIndex(np.zeros((1, 40, 40))) is None
    assert AutomationDebugWindow._centerFrameIndex(np.zeros((40, 40))) is None
