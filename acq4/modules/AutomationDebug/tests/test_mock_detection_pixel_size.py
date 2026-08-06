"""Tests for mock detection's pixel size: it comes from the loaded z-stack.

Cover that _mock_pixel_size reads the XY pixel size off the loaded mock detection
stack rather than the live camera, and rejects a classification stack that
disagrees with it.
"""

import numpy as np
import pytest
from pyqtgraph.units import µm

import coorx
from acq4.util.imaging import Frame

from acq4.modules.AutomationDebug.detection import _mock_pixel_size


def _make_stack(xy_px, n_frames=3, nrows=8, ncols=8, z_step=1e-6):
    """A z-stack of Frames carrying `xy_px` as their pixel size, as a loaded mock
    stack does."""
    frames = []
    for i in range(n_frames):
        m = np.eye(4)
        m[0, 0] = xy_px
        m[1, 1] = xy_px
        m[2, 2] = z_step
        m[2, 3] = i * z_step
        xform = coorx.AffineTransform.from_matrix(m, from_cs=f"frame_{i}.xyz", to_cs="global")
        info = {"transform": xform, "pixelSize": (xy_px, xy_px)}
        frames.append(Frame(np.zeros((nrows, ncols), dtype=np.float32), info))
    return frames


def test_pixel_size_comes_from_the_detection_stack():
    """The mock stack was acquired on some other rig, so its pixel size is the only
    one that describes it; the live camera's is unrelated."""
    assert _mock_pixel_size(_make_stack(0.5 * µm), None) == 0.5 * µm


def test_matching_classification_stack_is_accepted():
    detection = _make_stack(0.5 * µm)
    classification = _make_stack(0.5 * µm)
    assert _mock_pixel_size(detection, classification) == 0.5 * µm


def test_disagreeing_classification_stack_is_rejected():
    """Two channels of the same field must share a pixel size; if they don't, one of
    them is the wrong file and silently scaling by the detection stack's would put
    the classification channel's cells in the wrong place."""
    detection = _make_stack(0.5 * µm)
    classification = _make_stack(0.25 * µm)
    with pytest.raises(ValueError, match="does not match"):
        _mock_pixel_size(detection, classification)


def test_rejection_message_names_both_sizes_in_micrometres():
    detection = _make_stack(0.5 * µm)
    classification = _make_stack(0.25 * µm)
    with pytest.raises(ValueError) as excinfo:
        _mock_pixel_size(detection, classification)
    assert "0.5000" in str(excinfo.value)
    assert "0.2500" in str(excinfo.value)
