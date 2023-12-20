import time, weakref
from typing import Union, Optional

import numpy as np
import pyqtgraph as pg
from MetaArray import MetaArray

from acq4.util import Qt, ptime
from acq4.util.Thread import Thread
from acq4.util.Mutex import Mutex
import acq4.Manager as Manager
from acq4.util.future import Future


def runZStack(imager, z_range_args) -> Future:
    """Acquire a Z stack from the given imager.

    Args:
        imager: Imager instance
        z_range_args: (start, end, step)

    Returns:
        Future: Future object that will contain the frames once the acquisition is complete.
    """
    return ImageSequencerFuture({
        "imager": imager,
        "zStack": True,
        "zStackRangeArgs": z_range_args,
        "timelapseCount": 1,
        "timelapseInterval": 0,
        "save": False,
    })


class ImageSequencerFuture(Future):
    def __init__(self, protocol):
        Future.__init__(self)
        self._protocol = protocol
        self._thread = ImageSequencerThread()
        self._thread.finished.connect(self._threadFinished)
        self._thread.start(protocol)

    def percentDone(self):
        return 100 if self.isDone() else 0

    def _threadFinished(self):
        self._taskDone()

    def getResult(self, timeout=None):
        self.wait(timeout)
        return self._thread.getResult()


def _enforce_linear_z_stack(frames: list["Frame"], step: float) -> list["Frame"]:
    """Ensure that the Z stack frames are linearly spaced. Frames are likely to come back with
    grouped z-values due to the stage's infrequent updates (i.e. 4 frames will arrive
    simultaneously, or just in the time it takes to get a new z value). This assumes the z
    values of the first and last frames are correct, but not necessarily any of the other
    frames."""
    if len(frames) < 2:
        return frames
    if step == 0:
        raise ValueError("Z stack step size must be non-zero.")
    step = abs(step)
    frames = [(f.mapFromFrameToGlobal(pg.Vector(0, 0, 0)).z(), f) for f in frames]
    expected_size = abs(frames[-1][0] - frames[0][0]) / step
    if len(frames) < expected_size:
        raise ValueError("Insufficient frames to have one frame per step.")
    # throw away frames that are nearly identical to the previous frame (hopefully this only
    # happens at the endpoints)

    def difference_is_significant(frame1, frame2):
        """Returns whether the absolute difference between the two frames is significant. Frames are
        tuples of (z, frame)."""
        z1, frame1 = frame1
        z2, frame2 = frame2
        return z1 != z2  # for now
        if z1 != z2:
            return True
        img1 = frame1.data()
        img2 = frame2.data()
        dmax = np.iinfo(img1.dtype).max
        threshold = (dmax / 512)  # arbitrary
        overflowed_diff = img1 - img2  # e.g. uint16: 4 - 1 = 3, 1 - 4 = 65532
        if np.issubdtype(img1.dtype, np.unsignedinteger):
            abs_adjust = (img1 < img2).astype(img1.dtype) * dmax + 1  # e.g. uint16: "-1" (65535) if img1 < img2, 1 otherwise
            return np.mean(overflowed_diff * abs_adjust) > threshold
        else:
            return np.mean(np.abs(overflowed_diff)) > threshold
    frames = [frames[0]] + [
        f for i, f in enumerate(frames[1:], 1)
        if difference_is_significant(f, frames[i - 1])
    ]
    if len(frames) < expected_size:
        raise ValueError("Insufficient frames to have one frame per step (after pruning nigh identical frames).")

    return [f for _, f in sorted(frames, )]

    # TODO do we want this?
    # TODO interpolate first?
    if frames[0][0] < frames[-1][0]:
        ideal_z_values = np.arange(frames[0][0], frames[-1][0] + step, step)
    else:
        ideal_z_values = np.arange(frames[0][0], frames[-1][0] - step, -step)
    # [(0, f1), (0, f2), (1, f3)] with ideal z's of [0, 1] should become [(0, f1), (1, f3)]
    # [(0, f1), (2, f2), (2, f3), (2, f4)] with ideal z's of [0, 1, 2] should become [(0, f1), (1, f2), (2, f4)]
    ideal_idx = 0
    actual_idx = 0
    actual_z_values = np.array([z for z, _ in frames])
    new_frame_idxs = []
    while ideal_idx < len(ideal_z_values) and actual_idx < len(frames):
        next_closest = np.argmin(np.abs(actual_z_values - ideal_z_values[ideal_idx]))  # TODO this could be made faster if needed
        next_closest = max(next_closest, actual_idx)  # don't go backwards
        new_frame_idxs.append(next_closest)
        ideal_idx += 1
        actual_idx = next_closest + 1
    if len(new_frame_idxs) < expected_size:
        raise ValueError("Insufficient frames to have one frame per step (after walking through).")
    return [frames[i][1] for i in new_frame_idxs]


def _set_focus_depth(imager, depth: float, direction: float, speed: Union[float, str], future: Optional[Future] = None):
    if depth is None:
        return

    dz = depth - imager.getFocusDepth()

    # Avoid hysteresis:
    if direction > 0 and dz > 0:
        # stack goes downward
        f = imager.setFocusDepth(depth + 20e-6, speed)
        if future is not None:
            future.waitFor(f)
        else:
            f.wait()
    elif direction < 0 and dz < 0:
        # stack goes upward
        f = imager.setFocusDepth(depth - 20e-6, speed)
        if future is not None:
            future.waitFor(f)
        else:
            f.wait()

    f = imager.setFocusDepth(depth, speed=speed)
    if future is not None:
        future.waitFor(f)
    else:
        f.wait()


@Future.wrap
def _slow_z_stack(imager, start, end, step, _future) -> list["Frame"]:
    sign = np.sign(end - start)
    direction = sign * -1
    step = sign * abs(step)
    frames_fut = imager.acquireFrames()
    _set_focus_depth(imager, start, direction, speed='fast', future=_future)
    with imager.run(ensureFreshFrames=True):
        for z in np.arange(start, end + step, step):
            _future.waitFor(imager.acquireFrames(1))
            _set_focus_depth(imager, z, direction, speed='slow', future=_future)
        _future.waitFor(imager.acquireFrames(1))
    frames_fut.stop()
    _future.waitFor(frames_fut)
    return frames_fut.getResult()


class ImageSequencerThread(Thread):
    """Background thread that controls image acquisition / stage motion sequences.

    Used for collecting Z stacks and tiled mosaics.
    """

    class StopException(Exception):
        pass

    sigMessage = Qt.Signal(object)  # message

    def __init__(self):
        Thread.__init__(self)
        self.prot = None
        self._stop = False
        self._frames = None
        self._paused = False
        self.lock = Mutex(recursive=True)

    def start(self, protocol):
        if self.isRunning():
            raise Exception("Sequence is already running.")
        self.prot = protocol
        self._stop = False
        self.sigMessage.emit("[ running.. ]")
        Thread.start(self)

    def stop(self):
        with self.lock:
            self._stop = True

    def pause(self, p):
        with self.lock:
            self._paused = p

    def run(self):
        try:
            self.runSequence()
        except self.StopException:
            return

    def runSequence(self):
        # setup
        prot = self.prot
        maxIter = prot["timelapseCount"]
        interval = prot["timelapseInterval"]
        imager = self.prot["imager"]
        self.holdImagerFocus(True)
        self.openShutter(True)  # don't toggle shutter between stack frames
        self._frames = []

        # record
        with Manager.getManager().reserveDevices([imager, imager.parentDevice()]):  # TODO this isn't complete or correct
            try:
                for i in range(maxIter):
                    start = ptime.time()
                    if prot["zStack"]:
                        start, end, step = prot["zStackRangeArgs"]
                        direction = start - end
                        _set_focus_depth(imager, start, direction, 'fast')
                        # fps = imager.getEstimatedFrameRate().getResult()
                        stage = imager.scopeDev.getFocusDevice()
                        z_per_second = stage.positionUpdatesPerSecond
                        meters_per_frame = abs(step)
                        speed = meters_per_frame * z_per_second * 0.5
                        future = imager.acquireFrames()
                        with imager.run(ensureFreshFrames=True):
                            imager.acquireFrames(1).wait()  # just to be sure the camera's recording
                            _set_focus_depth(end, direction, speed)
                            imager.acquireFrames(1).wait()  # just to be sure the camera caught up
                            future.stop()
                            self._frames += future.getResult(timeout=10)
                        try:
                            self._frames = _enforce_linear_z_stack(self._frames, step)
                        except ValueError:
                            self.sigMessage.emit("Failed to enforce linear z stack. Retrying with stepwise movement.")
                            self._frames = _slow_z_stack(imager, start, end, step).getResult()
                            self._frames = _enforce_linear_z_stack(self._frames, step)
                    else:  # single frame
                        with imager.run(ensureFreshFrames=True):
                            self._frames.append(imager.acquireFrames(1).getResult()[0])
                    self.sendStatusMessage(i, maxIter)
                    self.sleep(until=start + interval)
            finally:
                if prot["save"]:
                    self.saveResults()
                self.openShutter(False)
                self.holdImagerFocus(False)

        # TODO do we need any of this?
        #                 except RuntimeError:
        #                     if i == 4:
        #                         print(
        #                             "Did not reach focus after 5 iterations ({:g} != {:g})".format(
        #                                 self.prot["imager"].getDevice().getFocusDepth(), depths[depthIndex]
        #                             )
        #                         )

    def sendStatusMessage(self, iteration, maxIter):
        if maxIter == 0:
            itermsg = f"iter={iteration + 1}"
        else:
            itermsg = f"iter={iteration + 1}/{maxIter}"

        self.sigMessage.emit(f"[ running  {itermsg} ]")

    def holdImagerFocus(self, hold):
        """Tell the focus controller to lock or unlock.
        """
        idev = self.prot["imager"]
        fdev = idev.getFocusDevice()
        if fdev is None:
            raise Exception("Device %s is not connected to a focus controller." % idev)
        if hasattr(fdev, "setHolding"):
            fdev.setHolding(hold)

    def openShutter(self, open):
        idev = self.prot["imager"]
        if hasattr(idev, "openShutter"):
            idev.openShutter(open)

    def recordFrame(self, frame, idx):
        # Handle new frame
        dh = self.prot["storageDir"]
        name = f"image_{idx:03d}"

        if self.prot["zStack"]:
            # start or append focus stack
            arrayInfo = [
                {"name": "Depth", "values": [frame.mapFromFrameToGlobal(pg.Vector(0, 0, 0)).z()]},
                {"name": "X"},
                {"name": "Y"},
            ]
            data = MetaArray(frame.getImage()[np.newaxis, ...], info=arrayInfo)
            if idx == 0:
                self.currentDepthStack = dh.writeFile(data, name, info=frame.info(), appendAxis="Depth")
            else:
                data.write(self.currentDepthStack.name(), appendAxis="Depth")

        else:
            # record single-frame image
            arrayInfo = [{"name": "X"}, {"name": "Y"}]
            data = MetaArray(frame.getImage(), info=arrayInfo)
            dh.writeFile(data, name, info=frame.info())

    def sleep(self, until):
        # Wait until some event occurs
        # check for pause / stop while waiting
        while True:
            with self.lock:
                if self._stop:
                    raise self.StopException("stopped")
                paused = self._paused
                has_frames = len(self._frames) > 0
            if paused:
                wait = 0.1
            else:
                if until == "frame":
                    if has_frames:
                        return
                    wait = 0.1
                else:
                    now = ptime.time()
                    wait = until - now
                    if wait <= 0:
                        return
            time.sleep(min(0.1, wait))

    def getResult(self):
        return self._frames

    def saveResults(self):
        for i, f in enumerate(self._frames):
            self.recordFrame(f, i)


class ImageSequencerCtrl(Qt.QWidget):
    """GUI for acquiring z-stacks, timelapse, and mosaic.
    """

    def __init__(self, cameraMod):
        self.mod = weakref.ref(cameraMod)
        Qt.QWidget.__init__(self)

        self.imager = None

        self.ui = Qt.importTemplate(".sequencerTemplate")()
        self.ui.setupUi(self)

        self.ui.zStartSpin.setOpts(value=100e-6, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        self.ui.zEndSpin.setOpts(value=50e-6, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        self.ui.zSpacingSpin.setOpts(min=1e-9, value=1e-6, suffix="m", siPrefix=True, dec=True, minStep=1e-9, step=0.5)
        self.ui.intervalSpin.setOpts(min=0, value=1, suffix="s", siPrefix=True, dec=True, minStep=1e-3, step=1)

        self.updateDeviceList()
        self.ui.statusLabel.setText("[ stopped ]")

        self.thread = ImageSequencerThread()

        self.state = pg.WidgetGroup(self)
        self.state.sigChanged.connect(self.stateChanged)
        cameraMod.sigInterfaceAdded.connect(self.updateDeviceList)
        cameraMod.sigInterfaceRemoved.connect(self.updateDeviceList)
        self.thread.finished.connect(self.threadStopped)
        self.thread.sigMessage.connect(self.threadMessage)
        self.ui.startBtn.clicked.connect(self.startClicked)
        self.ui.pauseBtn.clicked.connect(self.pauseClicked)
        self.ui.setStartBtn.clicked.connect(self.setStartClicked)
        self.ui.setEndBtn.clicked.connect(self.setEndClicked)

    def updateDeviceList(self):
        items = ["Select device.."]
        self.ui.deviceCombo.clear()
        for k, v in self.mod().interfaces.items():
            if v.canImage:
                items.append(k)
        self.ui.deviceCombo.setItems(items)

    def selectedImager(self):
        if self.ui.deviceCombo.currentIndex() < 1:
            return None
        else:
            name = self.ui.deviceCombo.currentText()
            return self.mod().interfaces[name].getDevice()

    def stateChanged(self, name, value):
        if name == "deviceCombo":
            imager = self.selectedImager()
            self.imager = imager
        self.updateStatus()

    def makeProtocol(self):
        """Build a description of everything that needs to be done during the sequence.
        """
        prot = {
            "imager": self.selectedImager(),
            "zStack": self.ui.zStackGroup.isChecked(),
            "timelapse": self.ui.timelapseGroup.isChecked(),
        }
        if prot["zStack"]:
            start = self.ui.zStartSpin.value()
            end = self.ui.zEndSpin.value()
            spacing = self.ui.zSpacingSpin.value()
            prot["zStackRangeArgs"] = (start, end, spacing)
        else:
            prot["zStackRangeArgs"] = None

        if prot["timelapse"]:
            prot["timelapseCount"] = self.ui.iterationsSpin.value()
            prot["timelapseInterval"] = self.ui.intervalSpin.value()
        else:
            prot["timelapseCount"] = 1
            prot["timelapseInterval"] = 0

        return prot

    def startClicked(self, b):
        if b:
            self.start()
        else:
            self.stop()

    def pauseClicked(self, b):
        self.thread.pause(b)

    def start(self):
        try:
            if self.selectedImager() is None:
                raise Exception("No imaging device selected.")
            prot = self.makeProtocol()
            self.currentProtocol = prot
            dh = Manager.getManager().getCurrentDir().getDir("ImageSequence", create=True, autoIncrement=True)
            dhinfo = prot.copy()
            del dhinfo["imager"]
            dh.setInfo(dhinfo)
            prot["storageDir"] = dh
            prot["save"] = True
            self.ui.startBtn.setText("Stop")
            self.ui.zStackGroup.setEnabled(False)
            self.ui.timelapseGroup.setEnabled(False)
            self.ui.deviceCombo.setEnabled(False)
            self.thread.start(prot)
        except Exception:
            self.threadStopped()
            raise

    def stop(self):
        self.thread.stop()

    def threadStopped(self):
        self.ui.startBtn.setText("Start")
        self.ui.startBtn.setChecked(False)
        self.ui.zStackGroup.setEnabled(True)
        self.ui.timelapseGroup.setEnabled(True)
        self.ui.deviceCombo.setEnabled(True)
        self.updateStatus()

    def threadMessage(self, message):
        self.ui.statusLabel.setText(message)

    def updateStatus(self):
        prot = self.makeProtocol()
        if prot["timelapse"]:
            itermsg = f"iter=0/{prot['timelapseCount']}"
        else:
            itermsg = "iter=0"

        msg = f"[ stopped  {itermsg} ]"
        self.ui.statusLabel.setText(msg)

    def setStartClicked(self):
        dev = self.selectedImager()
        if dev is None:
            raise Exception("Must select an imaging device first.")
        self.ui.zStartSpin.setValue(dev.getFocusDepth())

    def setEndClicked(self):
        dev = self.selectedImager()
        if dev is None:
            raise Exception("Must select an imaging device first.")
        self.ui.zEndSpin.setValue(dev.getFocusDepth())
