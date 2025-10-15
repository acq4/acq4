from __future__ import annotations

import itertools
import weakref
from typing import Union, Optional, Generator

import numpy as np
from scipy.optimize import linear_sum_assignment
from skimage.metrics import structural_similarity as ssim

import acq4.Manager as Manager
import pyqtgraph as pg
from acq4.util import Qt, ptime
from acq4.util.DataManager import DirHandle
from acq4.util.future import Future, future_wrap
from acq4.util.imaging import Frame
from acq4.util.surface import find_surface
from acq4.util.threadrun import runInGuiThread


def enforce_linear_z_stack(frames: list[Frame], start: float, stop: float, step: float) -> list[Frame]:
    """Ensure that the Z stack frames are linearly spaced. Frames are likely to come back with
    grouped z-values due to the stage's infrequent updates (i.e. 4 frames will arrive
    simultaneously, or just in the time it takes to get a new z value). This assumes the z
    values of the first and last frames are correct, but not necessarily any of the other
    frames."""
    if step == 0:
        raise ValueError("Z stack step size must be non-zero.")
    start, stop = sorted((start, stop))
    step = abs(step)
    depths = sorted([(f.depth, i) for i, f in enumerate(frames)])
    if (stop - start) % step != 0:
        expected_depths = np.arange(start, stop, step)
    else:
        expected_depths = np.arange(start, stop + step, step)
    if len(depths) < len(expected_depths):
        raise ValueError("Insufficient frames to have one frame per step.")

    first = depths.pop(0)
    last = depths.pop(-1)

    def is_significant(frame1: tuple[float, int]):
        # throw out frames with depth equal to the first or last
        tol = np.clip(step / 10, 1e-12, 1e-7)
        return not (np.isclose(frame1[0], first[0], atol=tol) or np.isclose(frame1[0], last[0], atol=tol))

    depths = [first] + [d for d in depths if is_significant(d)] + [last]
    if len(depths) < len(expected_depths):
        raise ValueError("Insufficient frames to have one frame per step (after pruning nigh identical frames).")

    # get the closest frame for each expected depth using the Hungarian algorithm
    interpolated_depths = np.linspace(start, stop, len(depths))
    cost_matrix = np.abs(expected_depths[:, None] - interpolated_depths[None, :])
    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    idxes = np.full(len(expected_depths), -1, dtype=int)
    for i, j in zip(row_ind, col_ind):
        idxes[i] = j
    assert np.all(idxes >= 0), "I did the Hungarian wrong"
    # frames = [frames[depths[i][1]]
    ret_frames = []
    for i in idxes:
        depth, j = depths[i]
        frame = frames[j]
        xform = frame.globalTransform()
        xform.setTranslate(xform.getTranslation()[0], xform.getTranslation()[1], depth)
        frame.addInfo(transform=xform.saveState())
        ret_frames.append(frame)
    return ret_frames


def calculate_hysteresis(frames: list[Frame], center: Frame, min_likeness=0.95) -> float:
    if not frames:
        raise ValueError("Stack is empty")

    # Check if center frame is potentially in the stack
    center_data = center.data()
    if all(not np.array_equal(center_data.shape, f.data().shape) for f in frames):
        raise ValueError("Center frame is not in the stack")

    similarities = []
    for f in frames:
        f_data = f.data()
        try:
            similarity = ssim(f_data, center_data)
            similarities.append(similarity)
        except ValueError:
            # Handle frames with different shapes or other issues
            similarities.append(-float('inf'))

    if all(sim < min_likeness for sim in similarities):
        raise ValueError("Center frame does not match any frame in the stack")

    closest_match = np.argmax(similarities)
    return frames[closest_match].depth - frames[len(frames) // 2].depth


def _set_focus_depth(
    imager,
    depth: float,
    direction: float,
    speed: Union[float, str],
    hysteresis_correction: bool = True,
    future: Optional[Future] = None,
):
    if depth is None:
        return

    if isinstance(speed, str):
        speed = imager.getFocusDevice()._interpretSpeed(speed)
    dz = depth - imager.getFocusDepth()
    timeout = max(10, 3 * abs(dz) / speed)

    # Avoid hysteresis:
    if hysteresis_correction and direction > 0 and dz > 0:
        # stack goes downward
        move = imager.setFocusDepth(depth + 20e-6, speed)
    elif hysteresis_correction and direction < 0 and dz < 0:
        # stack goes upward
        move = imager.setFocusDepth(depth - 20e-6, speed)
    else:
        move = imager.setFocusDepth(depth, speed)

    if future is not None:
        future.waitFor(move, timeout=timeout)
    else:
        move.wait(timeout=timeout)

    move = imager.setFocusDepth(depth, speed)  # maybe redundant
    if future is not None:
        future.waitFor(move, timeout=timeout)
    else:
        move.wait(timeout=timeout)


def _stepped_z_stack(imager, start, end, step, future) -> list[Frame]:
    sign = np.sign(end - start)
    direction = sign * -1
    step = sign * abs(step)
    frames_fut = imager.acquireFrames()
    _set_focus_depth(imager, start, direction, speed="fast", future=future)
    with imager.ensureRunning(ensureFreshFrames=True):
        for z in np.arange(start, end + step, step):
            future.waitFor(imager.acquireFrames(1))
            _set_focus_depth(imager, z, direction, speed="slow", future=future)
        future.waitFor(imager.acquireFrames(1))
    frames_fut.stop()
    future.waitFor(frames_fut)
    return frames_fut.getResult()


def _hold_imager_focus(idev, hold):
    """Tell the focus controller to lock or unlock."""
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
    Returns either the containing dir or the single file handle.
        +-----------+--------+---------+------------------------+----------------+
        | timelapse | mosaic | z-stack |    resultant files     |  fh to return  |
        +-----------+--------+---------+------------------------+----------------+
        | true      | true   | true    | folders of z-stack mas |  storage_dir   |
        | true      | true   | false   | folders of images      |  storage_dir   |
        | true      | false  | true    | multiple z-stack mas   |  storage_dir   |
        | true      | false  | false   | single timelapse ma    |  timelapse.ma  |
        | false     | true   | true    | multiple z-stack mas   |  storage_dir   |
        | false     | true   | false   | multiple images        |  storage_dir   |
        | false     | false  | true    | single z-stack ma      |  z_stack.ma    |
        | false     | false  | false   | single image           |  image.tif     |
        +-----------+--------+---------+------------------------+----------------+
    """
    ret_fh = storage_dir
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
        if not is_timelapse and not is_mosaic:
            ret_fh = stack
    elif is_timelapse and not is_mosaic:
        if idx == 0:
            ret_fh = frames.saveImage(storage_dir, "timelapse.ma", autoIncrement=False)
        else:
            fh = storage_dir["timelapse.ma"]  # MC: I don't like this
            frames.appendImage(fh)
            ret_fh = fh
    else:
        fh = frames.saveImage(storage_dir, "image.tif")
        if not is_mosaic and not is_timelapse:
            ret_fh = fh

    return ret_fh


@future_wrap(logLevel='debug')
def run_image_sequence(
    imager,
    count: float = 1,
    interval: float = 0,
    pin: "Callable[[Frame]] | None" = None,
    z_stack: "tuple[float, float, float] | None" = None,
    mosaic: "tuple[float, float, float, float, float] | None" = None,
    storage_dir: "DirHandle | None" = None,
    _future: Future = None,
) -> "Frame | list[Frame | list[Frame | list[Frame]]]":
    _hold_imager_focus(imager, True)
    _open_shutter(imager, True)  # don't toggle shutter between stack frames
    man = Manager.getManager()
    result = []
    is_timelapse = count > 1
    ret_fh = None

    def handle_new_frames(f: "Frame | list[Frame]", idx: int):
        nonlocal ret_fh
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
            fh = _save_results(f, storage_dir, idx, count > 1, bool(mosaic), bool(z_stack))
            if ret_fh is None:
                ret_fh = fh

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
                        stack = acquire_z_stack(imager, *z_stack, block=True, checkStopThrough=_future).getResult()
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
    _future.imagesSavedIn = ret_fh
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


@future_wrap(logLevel='debug')
def acquire_z_stack(
    imager,
    start: float,
    stop: float,
    step: float,
    hysteresis_correction=True,
    slow_fallback=True,
    device_reservation_timeout=10.0,
    max_dz_per_frame=5e-6,  # m
    _future: Future = None,
) -> list[Frame]:
    """Acquire a Z stack from the given imager.

    Parameters
    ----------
    imager: np.ndarray
        The imager instance to use for acquisition.
    start: float
        Z position to begin the stack.
    stop: float
        Z position to end the stack (can be above or below start).
    step: float
        Expected distance between frames.
    hysteresis_correction: bool
        If True, approach each z position from the same direction to avoid hysteresis.
    slow_fallback: bool
        If True, and the fast acquisition method fails to produce a linear stack, retry with the
        slower stepwise method.
    device_reservation_timeout: float
        Maximum time to wait for device reservation.
    max_dz_per_frame: float

    Returns
    -------
    Future[list[Frame]]
        Future wrapped around the acquired frames, with corrected z positions.
    """
    # TODO think about strobing the lighting for clearer images
    direction = start - stop
    _set_focus_depth(imager, start, direction, "fast", hysteresis_correction, _future)
    stage = imager.scopeDev.getFocusDevice()
    exposure = imager.getParam('exposure')
    # todo estimate the depth of field of the objective from its numerical aperture and wavelength
    z_per_second = stage.positionUpdatesPerSecond
    meters_per_frame = abs(step)
    speed = meters_per_frame * z_per_second * 0.5
    dz_per_frame = speed * exposure
    man = Manager.getManager()
    if dz_per_frame > max_dz_per_frame:
        with man.reserveDevices(imager.devicesToReserve(), timeout=device_reservation_timeout):
            frames = _stepped_z_stack(imager, start, stop, step, _future)
        frames = enforce_linear_z_stack(frames, start, stop, step)
    else:
        with man.reserveDevices(imager.devicesToReserve(), timeout=device_reservation_timeout):
            with imager.ensureRunning(ensureFreshFrames=True):
                frames_fut = imager.acquireFrames()
                try:
                    _future.waitFor(imager.acquireFrames(1))  # just to be sure the camera's recording
                    _set_focus_depth(imager, stop, direction, speed, hysteresis_correction, _future)
                    _future.waitFor(imager.acquireFrames(1))  # just to be sure the camera caught up
                finally:
                    frames_fut.stop()
        frames = _future.waitFor(frames_fut).getResult(timeout=10)
        try:
            frames = enforce_linear_z_stack(frames, start, stop, step)
        except ValueError:
            if not slow_fallback:
                raise
            imager.logger.info("Failed to fast-acquire linear z stack. Retrying with stepwise movement.")
            with man.reserveDevices(imager.devicesToReserve(), timeout=device_reservation_timeout):
                frames = _stepped_z_stack(imager, start, stop, step, _future)
            frames = enforce_linear_z_stack(frames, start, stop, step)
    _fix_frame_transforms(frames, step)
    return frames


def _fix_frame_transforms(frames, z_step):
    for f in frames:
        xform = f.globalTransform()
        scale = xform.getScale()
        # Set z scale such that the transform oni the first frame can be used for the entire stack
        # (which should be approximately true if the frames are about evenly spaced)
        xform.setScale(scale[0], scale[1], z_step)
        f.addInfo(transform=xform.saveState())


class ImageSequencerCtrl(Qt.QWidget):
    """GUI for acquiring z-stacks, timelapse, and mosaic."""

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
        self.ui.mosaicOverlapSpin.setOpts(
            value=50e-6, suffix="m", siPrefix=True, step=1e-6, decimals=6, bounds=(0, float("inf"))
        )

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
        """Build a description of everything that needs to be done during the sequence."""
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
            self._future.onFinish(self.threadStopped, inGui=True)
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
        try:
            self.ui.startBtn.setText("Start")
            self.ui.startBtn.setChecked(False)
            self.setRunning(False)
            self.updateStatus()
            if self._future is not None:
                fut = self._future
                self._future.sigStateChanged.disconnect(self.threadMessage)
                self._future = None
                if not self._manuallyStopped:
                    fut.wait(timeout=1)  # to raise errors if any happened
        finally:
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
