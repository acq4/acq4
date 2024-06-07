import itertools
import weakref
from typing import Union, Optional, Generator

import numpy as np

import acq4.Manager as Manager
import pyqtgraph as pg
from acq4.util import Qt, ptime
from acq4.util.DataManager import DirHandle
from acq4.util.future import Future
from acq4.util.imaging import Frame
from acq4.util.surface import find_surface
from acq4.util.threadrun import runInGuiThread


def _enforce_linear_z_stack(frames: list[Frame], step: float) -> list[Frame]:
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
    depths = [(f.depth, f) for f in frames]
    expected_size = abs(depths[-1][0] - depths[0][0]) / step
    if len(depths) < expected_size:
        raise ValueError("Insufficient frames to have one frame per step.")
    # throw away frames that are nearly identical to the previous frame (hopefully this only
    # happens at the endpoints)

    def difference_is_significant(frame1: tuple[float, Frame], frame2: tuple[float, Frame]):
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
    depths = [depths[0]] + [
        f for i, f in enumerate(depths[1:], 1)
        if difference_is_significant(f, depths[i - 1])
    ]
    if len(depths) < expected_size:
        raise ValueError("Insufficient frames to have one frame per step (after pruning nigh identical frames).")

    return [f for _, f in sorted(depths)]

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
def _slow_z_stack(imager, start, end, step, _future) -> list[Frame]:
    sign = np.sign(end - start)
    direction = sign * -1
    step = sign * abs(step)
    frames_fut = imager.acquireFrames()
    _set_focus_depth(imager, start, direction, speed='fast', future=_future)
    with imager.ensureRunning(ensureFreshFrames=True):
        for z in np.arange(start, end + step, step):
            _future.waitFor(imager.acquireFrames(1))
            _set_focus_depth(imager, z, direction, speed='slow', future=_future)
        _future.waitFor(imager.acquireFrames(1))
    frames_fut.stop()
    _future.waitFor(frames_fut)
    return frames_fut.getResult()


def _hold_imager_focus(idev, hold):
    """Tell the focus controller to lock or unlock.
    """
    fdev = idev.getFocusDevice()
    if fdev is None:
        raise Exception(f"Device {idev} is not connected to a focus controller.")
    if hasattr(fdev, "setHolding"):
        fdev.setHolding(hold)


def _open_shutter(idev, open):
    if hasattr(idev, "openShutter"):
        idev.openShutter(open)


def _status_message(iteration, maxIter):
    if maxIter == 0:
        return f"iter={iteration + 1}"
    else:
        return f"iter={iteration + 1}/{maxIter}"


def _save_results(
        frames: "Frame | list[Frame]",
        storage_dir: DirHandle,
        idx: int,
        is_timelapse: bool = False,
        is_mosaic: bool = False,
        is_z_stack: bool = False,
):
    """
        +-----------+--------+---------+------------------------+
        | timelapse | mosaic | z-stack |    resultant files     |
        +-----------+--------+---------+------------------------+
        | true      | true   | true    | folders of z-stack mas |
        | true      | true   | false   | folders of images      |
        | true      | false  | true    | multiple z-stack mas   |
        | true      | false  | false   | single timelapse ma    |
        | false     | true   | true    | multiple z-stack mas   |
        | false     | true   | false   | multiple images        |
        | false     | false  | true    | single z-stack ma      |
        | false     | false  | false   | single image           |
        +-----------+--------+---------+------------------------+
    """
    if is_mosaic and is_timelapse:
        storage_dir = storage_dir.getDir(f"mosaic_{idx:03d}", create=True)

    if is_z_stack:
        stack = None
        for frame in frames:
            if stack is None:
                # TODO do we want to save the background/contrast display data for each frame, too
                stack = frame.saveImage(storage_dir, "z_stack.ma")
            else:
                stack = frame.appendImage(stack)
    elif is_timelapse and not is_mosaic:
        if idx == 0:
            frames.saveImage(storage_dir, "timelapse.ma", autoIncrement=False)
        else:
            fh = storage_dir["timelapse.ma"]  # MC: I don't like this
            frames.appendImage(fh)
    else:
        frames.saveImage(storage_dir, "image.tif")


@Future.wrap
def run_image_sequence(
        imager,
        count: float = 1,
        interval: float = 0,
        pin: "Callable[[Frame]] | None" = None,
        z_stack: "tuple[float, float, float] | None" = None,
        mosaic: "tuple[float, float, float, float, float] | None" = None,
        storage_dir: "DirHandle | None" = None,
        _future: Future = None
) -> "Frame | list[Frame | list[Frame | list[Frame]]]":
    _hold_imager_focus(imager, True)
    _open_shutter(imager, True)  # don't toggle shutter between stack frames
    man = Manager.getManager()
    result = []
    is_timelapse = count > 1

    def handle_new_frames(f: "Frame | list[Frame]", idx: int):
        if is_timelapse:
            if idx + 1 > len(result):
                result.append([])
            dest = result[-1]
        else:
            dest = result
        dest.append(f)
        if pin:
            if z_stack:
                most_focused = find_surface(f) or (len(f) // 2)
                pin(f[most_focused])
            else:
                pin(f)
        if storage_dir:
            _save_results(f, storage_dir, idx, count > 1, bool(mosaic), bool(z_stack))

    # record
    with man.reserveDevices(imager.devicesToReserve()):
        try:
            for i in itertools.count():
                if i >= count:
                    break
                start = ptime.time()
                for move in movements_to_cover_region(imager, mosaic):
                    _future.waitFor(move)
                    if z_stack:
                        stack = acquire_z_stack(imager, *z_stack, block=True).getResult()
                        handle_new_frames(stack, i)
                    else:  # single frame
                        frame = _future.waitFor(imager.acquireFrames(1, ensureFreshFrames=True)).getResult()[0]
                        handle_new_frames(frame, i)
                    _future.checkStop()
                _future.setState(_status_message(i, count))
                _future.sleep(interval - (ptime.time() - start))
        finally:
            _open_shutter(imager, False)
            _hold_imager_focus(imager, False)
    return result


def movements_to_cover_region(
    imager, region: "tuple[float, float, float, float, float] | None"
) -> Generator[Future, None, None]:
    """
    Generate a sequence of snaking movements to cover the region. `region` is a tuple containing the `left`, `top`,
    `right`, and `bottom` coordinates, as well as an `overlap`, all in global/meters. `region` can also be None, in
    which case this yields once with a no-op Future.
    """
    if region is None:
        yield Future.immediate()
        return

    for pos in positions_to_cover_region(region, imager.globalCenterPosition(), imager.getBoundary(mode="roi")):
        yield imager.moveCenterToGlobal(pos, "fast")


def positions_to_cover_region(region, imager_center, imager_region) -> Generator[tuple, None, None]:
    """Ha! (ignoring overlap), `region` is (x1, y1, x2, y2), `imager_region` is (x1, y1, w, h)."""
    z = imager_center[2]
    img_x, img_y, img_w, img_h = imager_region
    img_top_left = np.array((img_x, img_y, z))
    move_offset = imager_center - img_top_left
    img_bottom_right = np.array((img_x + img_w, img_y + img_h, z))
    coverage_offset = imager_center - img_bottom_right
    overlap = region[-1]
    step = np.abs(img_bottom_right - img_top_left)[:2] - overlap
    if np.any(step <= 0):
        raise ValueError(f"Overlap {overlap:g} exceeds field of view")

    region_top_left = np.array((*region[:2], z))
    region_bottom_right = np.array((*region[2:4], z))
    pos = region_top_left + move_offset
    x_finished = y_finished = False
    x_tests = (
            lambda: (pos - coverage_offset)[0] >= region_bottom_right[0],
            lambda: (pos + coverage_offset)[0] <= region_top_left[0],
    )
    x_steps = (step[0], -step[0])
    x_direction = 0

    while not y_finished:
        y_finished = (pos - coverage_offset)[1] <= region_bottom_right[1]
        while not x_finished:
            yield pos
            x_finished = x_tests[x_direction]()
            if not x_finished:
                pos[0] += x_steps[x_direction]
        pos[1] -= step[1]
        x_direction = (x_direction + 1) % 2
        x_finished = False


@Future.wrap
def acquire_z_stack(imager, start: float, stop: float, step: float, _future: Future) -> Future:
    """Acquire a Z stack from the given imager.

    Args:
        imager: Imager instance
        start: z position to begin
        stop: z position to end (can be above or below start)
        step: expected distance between frames

    Returns:
        Future: Future object that will contain the frames once the acquisition is complete.
    """
    # TODO think about strobing the lighting for clearer images
    direction = start - stop
    _set_focus_depth(imager, start, direction, 'fast')
    stage = imager.scopeDev.getFocusDevice()
    z_per_second = stage.positionUpdatesPerSecond
    meters_per_frame = abs(step)
    speed = meters_per_frame * z_per_second * 0.5
    man = Manager.getManager()
    with man.reserveDevices(imager.devicesToReserve()):
        frames_fut = imager.acquireFrames()
        with imager.ensureRunning(ensureFreshFrames=True):
            _future.waitFor(imager.acquireFrames(1))  # just to be sure the camera's recording
            _set_focus_depth(imager, stop, direction, speed)
            _future.waitFor(imager.acquireFrames(1))  # just to be sure the camera caught up
            frames_fut.stop()
            frames = _future.waitFor(frames_fut).getResult(timeout=10)
        try:
            frames = _enforce_linear_z_stack(frames, step)
        except ValueError:
            _future.setState("Failed to enforce linear z stack. Retrying with stepwise movement.")
            frames = _slow_z_stack(imager, start, stop, step).getResult()
            frames = _enforce_linear_z_stack(frames, step)
    return frames


class ImageSequencerCtrl(Qt.QWidget):
    """GUI for acquiring z-stacks, timelapse, and mosaic.
    """

    def __init__(self, cameraMod):
        self.mod = weakref.ref(cameraMod)
        Qt.QWidget.__init__(self)

        self.imager = None
        self._manuallyStopped = False

        self.ui = Qt.importTemplate(".sequencerTemplate")()
        self.ui.setupUi(self)

        self.ui.zStartSpin.setOpts(value=100e-6, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        self.ui.zEndSpin.setOpts(value=50e-6, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        self.ui.zSpacingSpin.setOpts(min=1e-9, value=1e-6, suffix="m", siPrefix=True, dec=True, minStep=1e-9, step=0.5)
        self.ui.intervalSpin.setOpts(min=0, value=1, suffix="s", siPrefix=True, dec=True, minStep=1e-3, step=1)
        self.ui.xLeftSpin.setOpts(value=0, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        self.ui.xRightSpin.setOpts(value=0, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        self.ui.yTopSpin.setOpts(value=0, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        self.ui.yBottomSpin.setOpts(value=0, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        self.ui.mosaicOverlapSpin.setOpts(value=50e-6, suffix="m", siPrefix=True, step=1e-6, decimals=6, bounds=(0, float('inf')))

        self.updateDeviceList()
        self.ui.statusLabel.setText("[ stopped ]")

        self._future: Optional[Future] = None

        self.state = pg.WidgetGroup(self)
        self.state.sigChanged.connect(self.stateChanged)
        cameraMod.sigInterfaceAdded.connect(self.updateDeviceList)
        cameraMod.sigInterfaceRemoved.connect(self.updateDeviceList)
        self.ui.startBtn.clicked.connect(self.startClicked)
        self.ui.setStartBtn.clicked.connect(self.setStartClicked)
        self.ui.setEndBtn.clicked.connect(self.setEndClicked)
        self.ui.setTopLeftBtn.clicked.connect(self.setTopLeftClicked)
        self.ui.setBottomRightBtn.clicked.connect(self.setBottomRightClicked)

    def updateDeviceList(self):
        items = ["Select device.."]
        self.ui.deviceCombo.clear()
        items.extend(k for k, v in self.mod().interfaces.items() if v.canImage)
        self.ui.deviceCombo.setItems(items)

    def selectedImager(self):
        if self.ui.deviceCombo.currentIndex() < 1:
            return None
        name = self.ui.deviceCombo.currentText()
        return self.mod().interfaces[name].getDevice()

    def _selectedImagerOrComplain(self):
        dev = self.selectedImager()
        if dev is None:
            raise ValueError("Must select an imaging device first.")
        return dev

    def stateChanged(self, name, value):
        if name == "deviceCombo":
            imager = self.selectedImager()
            self.imager = imager
        self.updateStatus()

    def makeProtocol(self):
        """Build a description of everything that needs to be done during the sequence.
        """
        prot = {"imager": self.selectedImager()}
        if self.ui.zStackGroup.isChecked():
            start = self.ui.zStartSpin.value()
            end = self.ui.zEndSpin.value()
            spacing = self.ui.zSpacingSpin.value()
            prot["z_stack"] = (start, end, spacing)

        if self.ui.timelapseGroup.isChecked():
            count = self.ui.iterationsSpin.cleanText()
            if count == "inf":
                count = float(count)
            else:
                count = int(count)
            prot["count"] = count
            prot["interval"] = self.ui.intervalSpin.value()
        else:
            prot["count"] = 1
            prot["interval"] = 0

        if self.ui.mosaicGroup.isChecked():
            prot["mosaic"] = (
                self.ui.xLeftSpin.value(),
                self.ui.yTopSpin.value(),
                self.ui.xRightSpin.value(),
                self.ui.yBottomSpin.value(),
                self.ui.mosaicOverlapSpin.value(),
            )

        if self.ui.pinCheckbox.isChecked():
            prot["pin"] = lambda f: runInGuiThread(self.mod().displayPinnedFrame, f)

        return prot

    def startClicked(self, b):
        if b:
            self.start()
        else:
            self.stop()

    def start(self):
        try:
            if self.selectedImager() is None:
                raise RuntimeError("No imaging device selected.")
            prot = self.makeProtocol()
            dh = Manager.getManager().getCurrentDir().getDir("ImageSequence", create=True, autoIncrement=True)
            dhinfo = prot.copy()
            del dhinfo["imager"]
            if "pin" in dhinfo:
                del dhinfo["pin"]
            if dhinfo["count"] == float("inf"):
                dhinfo["count"] = -1
            dh.setInfo(dhinfo)
            prot["storage_dir"] = dh
            self.setRunning(True)
            self._future = run_image_sequence(**prot)
            self._future.sigFinished.connect(self.threadStopped)
            self._future.sigStateChanged.connect(self.threadMessage)
        except Exception:
            self.threadStopped(self._future)
            raise
        if self._future.isDone():  # probably an immediate error
            self.threadStopped(self._future)

    def stop(self):
        if self._future is not None:
            self.ui.startBtn.setText("Stopping...")
            self.ui.startBtn.setEnabled(False)
            self._future.stop()
            self._manuallyStopped = True

    def threadStopped(self, future):
        self.ui.startBtn.setText("Start")
        self.ui.startBtn.setChecked(False)
        self.setRunning(False)
        self.updateStatus()
        if self._future is not None:
            fut = self._future
            self._future.sigFinished.disconnect(self.threadStopped)
            self._future.sigStateChanged.disconnect(self.threadMessage)
            self._future = None
            if not self._manuallyStopped:
                fut.wait(timeout=1)  # to raise errors if any happened
                self._manuallyStopped = False

    def setRunning(self, b):
        self.ui.startBtn.setEnabled(True)
        self.ui.startBtn.setText("Stop" if b else "Start")
        self.ui.zStackGroup.setEnabled(not b)
        self.ui.mosaicGroup.setEnabled(not b)
        self.ui.timelapseGroup.setEnabled(not b)
        self.ui.deviceCombo.setEnabled(not b)

    def threadMessage(self, future, message):
        self.ui.statusLabel.setText(message)

    def updateStatus(self):
        prot = self.makeProtocol()
        if prot["count"] > 1:
            itermsg = f"iter=0/{prot['count']}"
        else:
            itermsg = "iter=0"

        msg = f"[ stopped  {itermsg} ]"
        self.ui.statusLabel.setText(msg)

    def setStartClicked(self):
        dev = self._selectedImagerOrComplain()
        self.ui.zStartSpin.setValue(dev.getFocusDepth())

    def setEndClicked(self):
        dev = self._selectedImagerOrComplain()
        self.ui.zEndSpin.setValue(dev.getFocusDepth())

    def setTopLeftClicked(self):
        cam = self._selectedImagerOrComplain()
        region = cam.getParam("region")
        bound = cam.globalTransform().map(Qt.QPointF(region[0], region[1]))
        self.ui.xLeftSpin.setValue(bound.x())
        self.ui.yTopSpin.setValue(bound.y())

    def setBottomRightClicked(self):
        cam = self._selectedImagerOrComplain()
        region = cam.getParam("region")
        bound = cam.globalTransform().map(Qt.QPointF(region[0] + region[2], region[1] + region[3]))
        self.ui.xRightSpin.setValue(bound.x())
        self.ui.yBottomSpin.setValue(bound.y())
