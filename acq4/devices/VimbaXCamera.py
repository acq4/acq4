from __future__ import annotations

import contextlib
import queue
from threading import RLock
from time import sleep

import numpy as np

from acq4.devices.Camera import Camera
from vmbpy import VmbSystem, Camera as VmbCamera, VmbCameraError, VmbFeatureError, BoolFeature


class VimbaXCamera(Camera):
    """Camera class for VimbaX cameras. See https://github.com/alliedvision/VmbPy for driver install instructions.
    This isn't necessarily production-ready code, and has only been written for use on a test rig."""

    def __init__(self, dm, config, name):
        self._dev: VmbCamera | None = None
        self._lock = RLock()
        self._config = config
        self._paramProperties = {}
        self._paramValuesOnDev = {}
        self._region = ()
        self._frameQueue = queue.Queue()
        self._doParamUpdates = True
        super().__init__(dm, config, name)

    def setupCamera(self):
        with VmbSystem.get_instance() as vmb:
            _id = self._config['id']
            try:
                self._dev = vmb.get_camera_by_id(_id)
            except VmbCameraError as e:
                available = "', '".join(c.get_id() for c in vmb.get_all_cameras())
                raise ValueError(f"Failed to open camera with id '{_id}'. Available: '{available}'") from e

        # MC: Danger! We're hereafter tricking all device access to make it think we're in a context manager
        VmbSystem.get_instance().__enter__()
        self._dev.__enter__()

        with contextlib.suppress(AttributeError, VmbFeatureError):
            stream = self._dev.get_streams()[0]
            stream.GVSPAdjustPacketSize.run()
            while not stream.GVSPAdjustPacketSize.is_done():
                pass

        for f in self._dev.get_all_features():
            if hasattr(f, "get"):
                name = f.get_name()
                self._paramValuesOnDev[name] = f.get()
                f.register_change_handler(self._updateParamCache)
                rng = None
                if name in ('BinningX', 'BinningY'):
                    rng = [r for r in range(*f.get_range()) if r == 1 or r % 2 == 0]
                elif hasattr(f, "get_range"):
                    rng = f.get_range()
                elif isinstance(f, BoolFeature):
                    rng = [False, True]
                elif hasattr(f, "get_all_entries"):
                    rng = [str(e) for e in f.get_all_entries()]
                self._paramProperties[_featureNameToParamName(name)] = (rng, f.is_writeable(), True, [])
        self._region = self._guessInitialRegion()

    def _guessInitialRegion(self):
        bin_x, bin_y = self.getParam('binning')
        x = self.getParam('regionX')
        y = self.getParam('regionY')
        w = self.getParam('regionW')
        h = self.getParam('regionH')
        if (w + 1) * bin_x == self.getParam('sensorWidth'):
            w += 1
        if (h + 1) * bin_y == self.getParam('sensorHeight'):
            h += 1
        return x * bin_x, y * bin_y, w * bin_x, h * bin_y

    def quit(self):
        super().quit()
        self._dev.__exit__(None, None, None)
        VmbSystem.get_instance().__exit__(None, None, None)
        self._dev = None

    def _updateParamCache(self, feature):
        # not in the mutex, because this is called from a C context that loses track its python context
        if not self._doParamUpdates:
            return
        value = feature.get()
        dev_name = feature.get_name()
        name = _featureNameToParamName(dev_name)
        self._paramValuesOnDev[dev_name] = value
        self.sigParamsChanged.emit({name: value})

    @contextlib.contextmanager
    def _noParamUpdates(self):
        self._doParamUpdates = False
        try:
            yield
        finally:
            self._doParamUpdates = True

    def listParams(self, params=None):
        if params is None:
            return self._paramProperties.copy()
        return {p: self._paramProperties[p] for p in params}

    def getParams(self, params=None):
        if params is None:
            return self.getParams(list(self._paramProperties.keys()))
        retval = {}
        for p in params:
            if p == 'sensorSize':
                retval[p] = (self.getParam('sensorWidth'), self.getParam('sensorHeight'))
            elif p == 'binning':
                retval[p] = (self.getParam('binningX'), self.getParam('binningY'))
            elif p == 'region':
                retval[p] = self._region
            elif p == 'exposure':
                retval[p] = self._paramValuesOnDev['ExposureTimeAbs'] / 1000
            else:
                retval[p] = self._paramValuesOnDev[_paramNameToFeatureName(p)]
        return retval

    def setParams(self, params: dict | list[tuple], autoRestart=True, autoCorrect=True):
        retval = {}
        restart = False
        with self._lock:
            if isinstance(params, dict):
                params = params.items()
            for p, v in params:
                if p == 'region':
                    self._region = v
                    x, y = self.getParam('binning')
                    newvals, _r = self.setParams(
                        [
                            ('regionX', v[0] // x),  # TODO it says that the x/y can't be non-zero most of the time. why?
                            ('regionY', v[1] // y),
                            ('regionW', min(v[2] // x, self.getParam('sensorWidth') // x - 1)),
                            ('regionH', min(v[3] // y, self.getParam('sensorHeight') // y - 1)),
                        ],
                        autoRestart=autoRestart,
                        autoCorrect=autoCorrect,
                    )
                    newvals['region'] = v
                elif p == 'binning':
                    with self._noParamUpdates():
                        newvals, _r = self.setParams(
                            [('binningX', v[0]), ('binningY', v[1])], autoRestart=autoRestart, autoCorrect=autoCorrect
                        )
                        x = newvals['binningX']
                        y = newvals['binningY']
                        newvals['binning'] = (x, y)
                elif p == 'triggerMode':
                    self._dev.TriggerMode.set(v in ('On', 1, True))
                    newvals = {p: v}
                    _r = True
                elif p == 'exposure':
                    v = v * 1000
                    if autoCorrect:
                        v = int(min(
                            max(v, self._paramProperties['exposureTimeAbs'][0][0]),
                            self._paramProperties['exposureTimeAbs'][0][1],
                        ))
                    self._dev.ExposureTimeAbs.set(v)
                    newvals = {p: v / 1000}
                    _r = True
                else:
                    self._paramValuesOnDev[_paramNameToFeatureName(p)] = v
                    getattr(self._dev, _paramNameToFeatureName(p)).set(v)
                    # TODO autocorrect
                    newvals = {p: v}
                    _r = True  # TODO how do I know this?
                retval.update(newvals)
                restart = restart or _r
        if restart and autoRestart:
            running = self.isRunning()
            self.stopCamera()
            if running:
                self.startCamera()
        return retval, restart

    def newFrames(self):
        frames = []
        with self._lock:
            with contextlib.suppress(queue.Empty):
                while f := self._frameQueue.get_nowait():
                    arr = f.as_numpy_ndarray()
                    frames.append({
                        'id': f.get_id(),
                        # MC: color data will blow this up
                        'data': arr.reshape(arr.shape[:-1]).T,
                        'time': f.get_timestamp(),
                    })
                    with contextlib.suppress(ValueError):
                        # ValueErrors from "wrong queue for frame" at restart are fine
                        self._dev.queue_frame(f)
        return frames

    def startCamera(self):
        with self._lock:
            self._dev.start_streaming(lambda _, __, f: self._frameQueue.put(f))

    def stopCamera(self):
        with self._lock:
            if self._dev is not None and self._dev.is_streaming():
                self._dev.stop_streaming()

    def _acquireFrames(self, n) -> np.ndarray:
        def reshape(f):
            arr = f.as_numpy_ndarray()[:, :, 0].T
            return arr[np.newaxis, ...]
        with self._lock:
            # MC: color data will be lost here!
            return np.concatenate(
                [reshape(f) for f in self._dev.get_frame_generator(n)]
            )


_known_map = {
    'binningX': 'BinningHorizontal',
    'binningY': 'BinningVertical',
    'regionX': 'OffsetX',
    'regionY': 'OffsetY',
    'regionW': 'Width',
    'regionH': 'Height',
    'bitDepth': 'SensorBits',
}
_inverse_known_map = {v: k for k, v in _known_map.items()}


def _paramNameToFeatureName(name):
    return _known_map.get(name, name[0].upper() + name[1:])


def _featureNameToParamName(name):
    return _inverse_known_map.get(name, name[0].lower() + name[1:])


# TODO stream features, maybe:
# StreamID
# StreamType
# StreamAnnouncedBufferCount
# StreamAcquisitionModeSelector
# StreamBufferHandlingMode
# StreamAnnounceBufferMinimum
# StreamInputBufferCount
# StreamOutputBufferCount
# StreamIsGrabbing
# MulticastEnable
# MulticastIPAddress
# GVSPFilterVersion
# GVSPFilterCompatibility
# GVSPTimeout
# GVSPDriver
# GVSPHostReceiveBufferSize
# GVSPBurstSize
# GVSPMaxLookBack
# GVSPMaxRequests
# GVSPMissingSize
# GVSPTiltingSize
# GVSPMaxWaitSize
# GVSPPacketSize
# GVSPAdjustPacketSize
# GVSPProtocol
# FrameStatisticsCounter
# FrameStatisticsCounterSelector
# FramePacketStatisticsCounter
# FramePacketStatisticsCounterSelector
# FrameRate
# FrameRateSelector
# StreamTimeElapsed
# StatPacketUnavailable
# StatFrameDelivered
# StatFrameDropped
# StatFrameUnderrun
# StatFrameShoved
# StatFrameRescued
# StatPacketReceived
# StatPacketMissed
# StatPacketErrors
# StatPacketRequested
# StatPacketResent
# StatFrameRate
# StatLocalRate
# StatTimeElapsed


def main():
    class MockManager:
        def declareInterface(self, *args, **kwargs):
            pass
    cam = VimbaXCamera(MockManager(), {'id': 'DEV_000F315B9827'}, 'test')
    try:
        cam.setParam('binningX', 1)
        cam.setParam('binningY', 1)
        w, h = cam.getParam('sensorSize')
        # w -= 4
        # h -= 4
        cam.setParam('region', (0, 0, w, h))
        print('pre test', cam.getParam('region'))
        _bin_test(cam, 1, w, h)
        print('real test start!', cam.getParam('region'))
        _bin_test(cam, 2, w, h)
        _bin_test(cam, 4, w, h)

        cam.setParam('exposure', 0.01)
        cam.setParam('triggerMode', 'Normal')
        fut = cam.driverSupportedFixedFrameAcquisition(5)
        res = fut.getResult()
        print(len(res), res[0].data().shape)
            # import ipdb; ipdb.set_trace()
            # with cam.ensureRunning():
            #     fut = cam.acquireFrames(5)
            #     frames = fut.getResult()
            #     print(len(frames), frames[0].data().shape)
            # with VmbSystem.get_instance() as _v:
            #     _cam = _v.get_all_cameras()[0]
            #     print(f'Camera ID: {_cam.get_id()}')
            #     with _cam:
            #         show_features(_cam)
            #         for stream in _cam.get_streams():
            #             show_features(stream, '\t')
    finally:
        # cam.quit()
        pass


def _bin_test(cam, b, w, h):
    print('--------start setting binning------')
    cam.setParam('binning', (b, b))
    print('--------end setting binning------')
    sleep(0.1)
    assert cam.getParam('region') == (0, 0, w, h), f"bin {b}: {cam.getParam('region')}"
    print('>>>>>>>> start setting region <<<<<<<<')
    cam.setParam('region', (0, 0, w, h))
    print('>>>>>>>> end setting region <<<<<<<<')
    sleep(0.1)
    assert cam.getParam('region') == (0, 0, w, h), f"bin {b}: {cam.getParam('region')}"


if __name__ == '__main__':
    main()
