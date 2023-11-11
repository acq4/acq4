import time, weakref
import numpy as np
import pyqtgraph as pg
from MetaArray import MetaArray
from acq4.util import Qt, ptime
from acq4.util.Thread import Thread
from acq4.util.Mutex import Mutex
import acq4.Manager as Manager

SequencerTemplate = Qt.importTemplate(".sequencerTemplate")


class ImageSequencerThread(Thread):
    """Background thread that controls image acquisition / stage motion sequences.

    Used for collecting Z stacks and tiled mosaics.
    """

    sigMessage = Qt.Signal(object)  # message

    def __init__(self):
        Thread.__init__(self)
        self.prot = None
        self._stop = False
        self._frame = None
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

    def newFrame(self, frame):
        with self.lock:
            self._frame = frame

    def run(self):
        try:
            self.runSequence()
        except Exception as e:
            if hasattr(e, 'message') and e.message == "stopped":
                return
            raise

    def runSequence(self):
        prot = self.prot
        maxIter = prot["timelapseCount"]
        interval = prot["timelapseInterval"]
        dev = self.prot["imager"].getDevice()

        depths = prot["zStackValues"]
        iter = 0
        while True:
            start = ptime.time()

            running = dev.isRunning()
            dev.stop()
            self.holdImagerFocus(True)
            self.openShutter(True)  # don't toggle shutter between stack frames
            try:
                for depthIndex in range(len(depths)):
                    # Focus motor is unreliable; ask a few times if needed.
                    for i in range(5):
                        try:
                            self.setFocusDepth(depthIndex, depths)
                            break
                        except RuntimeError:
                            if i == 4:
                                print(
                                    "Did not reach focus after 5 iterations ({:g} != {:g})".format(
                                        self.prot["imager"].getDevice().getFocusDepth(), depths[depthIndex]
                                    )
                                )

                    frame = self.getFrame()
                    self.recordFrame(frame, iter, depthIndex)

                    self.sendStatusMessage(iter, maxIter, depthIndex, depths)

                    # check for stop / pause
                    self.sleep(until=0)

            finally:
                self.openShutter(False)
                self.holdImagerFocus(False)
                if running:
                    dev.start()

            iter += 1
            if maxIter != 0 and iter >= maxIter:
                break

            self.sleep(until=start + interval)

    def sendStatusMessage(self, iter, maxIter, depthIndex, depths):
        if maxIter == 0:
            itermsg = "iter=%d" % (iter + 1)
        else:
            itermsg = "iter=%d/%s" % (iter + 1, maxIter)

        if depthIndex is None or depths[depthIndex] is None:
            depthmsg = ""
        else:
            depthstr = pg.siFormat(depths[depthIndex], suffix="m")
            depthmsg = "depth=%s %d/%d" % (depthstr, depthIndex + 1, len(depths))

        self.sigMessage.emit("[ running  %s  %s ]" % (itermsg, depthmsg))

    def setFocusDepth(self, depthIndex, depths):
        imager = self.prot["imager"].getDevice()
        depth = depths[depthIndex]
        if depth is None:
            return

        dz = depth - imager.getFocusDepth()

        # Avoid hysteresis:
        if depths[0] > depths[-1] and dz > 0:
            # stack goes downward
            imager.setFocusDepth(depth + 20e-6).wait()
        elif depths[0] < depths[-1] and dz < 0:
            # stack goes upward
            imager.setFocusDepth(depth - 20e-6).wait()

        imager.setFocusDepth(depth).wait()

    def holdImagerFocus(self, hold):
        """Tell the focus controller to lock or unlock.
        """
        idev = self.prot["imager"].getDevice()
        fdev = idev.getFocusDevice()
        if fdev is None:
            raise Exception("Device %s is not connected to a focus controller." % idev)
        if hasattr(fdev, "setHolding"):
            fdev.setHolding(hold)

    def openShutter(self, open):
        idev = self.prot["imager"].getDevice()
        if hasattr(idev, "openShutter"):
            idev.openShutter(open)

    def getFrame(self):
        # request next frame
        imager = self.prot["imager"]
        with self.lock:
            # clear out any previously received frames
            self._frame = None

        frame = imager.takeImage(closeShutter=False)  # we'll handle the shutter elsewhere

        if frame is None:
            # wait for frame to arrive by signal
            # (camera and LSM imagers behave differently here; this behavior needs to be made consistent)
            self.sleep(until="frame")
            with self.lock:
                frame = self._frame
                self._frame = None
        return frame

    def recordFrame(self, frame, iter, depthIndex):
        # Handle new frame
        dh = self.prot["storageDir"]
        name = "image_%03d" % iter

        if self.prot["zStack"]:
            # start or append focus stack
            arrayInfo = [
                {"name": "Depth", "values": [self.prot["zStackValues"][depthIndex]]},
                {"name": "X"},
                {"name": "Y"},
            ]
            data = MetaArray(frame.getImage()[np.newaxis, ...], info=arrayInfo)
            if depthIndex == 0:
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
                    raise Exception("stopped")
                paused = self._paused
                frame = self._frame
            if paused:
                wait = 0.1
            else:
                if until == "frame":
                    if frame is not None:
                        return
                    wait = 0.1
                else:
                    now = ptime.time()
                    wait = until - now
                    if wait <= 0:
                        return
            time.sleep(min(0.1, wait))


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
            return self.mod().interfaces[name]

    def stateChanged(self, name, value):
        if name == "deviceCombo":
            if self.imager is not None:
                pg.disconnect(self.imager.sigNewFrame, self.newFrame)
            imager = self.selectedImager()
            if imager is not None:
                imager.sigNewFrame.connect(self.newFrame)
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
            if end < start:
                prot["zStackValues"] = list(np.arange(start, end, -spacing))
            else:
                prot["zStackValues"] = list(np.arange(start, end, spacing))
        else:
            prot["zStackValues"] = [None]

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
            itermsg = "iter=0/%d" % prot["timelapseCount"]
        else:
            itermsg = "iter=0"

        if prot["zStack"]:
            depthmsg = "depth=0/%d" % (len(prot["zStackValues"]))
        else:
            depthmsg = ""

        msg = "[ stopped  %s %s ]" % (itermsg, depthmsg)
        self.ui.statusLabel.setText(msg)

    def newFrame(self, iface, frame):
        self.thread.newFrame(frame)

    def setStartClicked(self):
        dev = self.selectedImager()
        if dev is None:
            raise Exception("Must select an imaging device first.")
        dev = dev.getDevice()
        self.ui.zStartSpin.setValue(dev.getFocusDepth())

    def setEndClicked(self):
        dev = self.selectedImager()
        if dev is None:
            raise Exception("Must select an imaging device first.")
        dev = dev.getDevice()
        self.ui.zEndSpin.setValue(dev.getFocusDepth())

