import pyqtgraph as pg

from acq4.devices.Camera.Camera import FrameAcquisitionFuture
from acq4.util import Qt


class FakeCamera(Qt.QObject):
    sigNewFrame = Qt.Signal(object)

    def name(self):
        return "fake"


def test_stop_keeps_frames_delivered_but_not_yet_collected():
    pg.mkQApp()
    cam = FakeCamera()
    fut = FrameAcquisitionFuture(cam, None)
    for _ in range(50):  # let the monitor connect and fall into its idle sleep
        if cam.receivers(cam.sigNewFrame) > 0:
            break
        Qt.QThread.msleep(10)
    Qt.QThread.msleep(20)
    for i in range(5):
        cam.sigNewFrame.emit(i)
    fut.stop()
    assert fut.wait(timeout=5) == [0, 1, 2, 3, 4]
