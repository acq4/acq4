from typing import Optional

import numpy as np

from acq4.util.imaging import ImagingCtrl
from pyqtgraph import Transform3D, TextItem
from pyqtgraph.Qt import QtCore


def detect_neurons(frame: np.ndarray, transform: Transform3D, model: Optional[str] = None) -> list[QtCore.QRectF]:
    """Use a neural network to detect neurons in a frame."""
    # TODO: Implement this
    boxes_in_px = [QtCore.QRectF(0, 0, 20, 20), QtCore.QRectF(100, 200, 20, 25)]
    return [transform.mapRect(box) for box in boxes_in_px]


def draw_bounding_boxes(
    boxes: list[QtCore.QRectF],
    img_ctrl: ImagingCtrl,
    label: Optional[str] = None,
    color=None,
    decay=0.1,
    delete_overlapping=False,
) -> None:
    # TODO decay and delete_overwrapping both need a persistent state
    view = img_ctrl.frameDisplay.imageItem().getViewBox()
    if color is None:
        color = QtCore.Qt.white
    for box in boxes:
        box.setBrush(color)
        if label:
            text = TextItem(label)
            text.setParentItem(box)
        view.addItem(box)
