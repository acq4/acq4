import time, weakref
import numpy as np
import pyqtgraph as pg
from MetaArray import MetaArray
from acq4.util import Qt, ptime
from acq4.util.Thread import Thread
from acq4.util.Mutex import Mutex
import acq4.Manager as Manager
from acq4.util.future import Future

SequencerTemplate = Qt.importTemplate(".sequencerTemplate")


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
                        self.setFocusDepth(start, direction)
                        fps = imager.getEstimatedFrameRate()
                        meters_per_frame = abs(step)
                        speed = meters_per_frame * fps
                        future = imager.acquireFrames()
                        with imager.run(ensureFreshFrames=True):
                            self.setFocusDepth(end, direction, speed=speed)
                            future.stop()
                            self._frames += future.getResult(timeout=10)
                        # TODO trim to get linear spacing? but the MockStage/Camera are so not giving me usable data T_T
                    else:  # timelapse
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

    def setFocusDepth(self, depth: float, direction: float, speed='fast'):
        imager = self.prot["imager"]
        if depth is None:
            return

        dz = depth - imager.getFocusDepth()

        # Avoid hysteresis:
        if direction > 0 and dz > 0:
            # stack goes downward
            imager.setFocusDepth(depth + 20e-6, speed).wait()
        elif direction < 0 and dz < 0:
            # stack goes upward
            imager.setFocusDepth(depth - 20e-6, speed).wait()

        imager.setFocusDepth(depth).wait()

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

        self.ui = SequencerTemplate()
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
