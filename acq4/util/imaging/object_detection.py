from acq4.devices.Camera import Frame
from acq4.util import Qt
from acq4.util.future import Future


@Future.wrap
def detect_neurons(frame: Frame, _future: Future):
    boxes = [(0, 0, 20, 20), (120, 180, 20, 20)]

    def map_box_to_global(box: tuple):
        start = Qt.QPointF(box[0], box[1])
        start = frame.mapFromFrameToGlobal(start)
        end = Qt.QPointF(box[0] + box[2], box[1] + box[3])
        end = frame.mapFromFrameToGlobal(end)
        size = end - start
        return Qt.QRectF(start, size)
    return [map_box_to_global(box) for box in boxes]
