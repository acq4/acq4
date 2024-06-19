from __future__ import annotations

import contextlib
import queue
from threading import RLock

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
        self._paramValues = {}
        self._frameQueue = queue.Queue()
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
                self._paramValues[name] = f.get()
                f.register_change_handler(self._updateParamCache)
                rng = None
                if hasattr(f, "get_range"):
                    rng = f.get_range()
                elif isinstance(f, BoolFeature):
                    rng = [False, True]
                elif hasattr(f, "get_all_entries"):
                    rng = [str(e) for e in f.get_all_entries()]
                self._paramProperties[_featureNameToParamName(name)] = (rng, f.is_writeable(), True, [])

    def quit(self):
        super().quit()
        self._dev.__exit__(None, None, None)
        VmbSystem.get_instance().__exit__(None, None, None)
        self._dev = None

    def _updateParamCache(self, feature):
        # not in the mutex, because this is called from a C context that loses track its python context
        self._paramValues[feature.get_name()] = feature.get()
        self.sigParamsChanged.emit({_featureNameToParamName(feature.get_name()): feature.get()})

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
                retval[p] = (self.getParam('regionX'), self.getParam('regionY'),
                             self.getParam('regionW'), self.getParam('regionH'))
            elif p == 'exposure':
                retval[p] = self._paramValues['ExposureTimeAbs'] / 1000
            else:
                retval[p] = self._paramValues[_paramNameToFeatureName(p)]
        return retval

    def setParams(self, params: dict | list[tuple], autoRestart=True, autoCorrect=True):
        retval = {}
        restart = False
        with self._lock:
            if isinstance(params, dict):
                params = params.items()
            for p, v in params:
                if p == 'region':
                    x, y = self.getParam('binning')
                    newvals, _r = self.setParams(
                        [
                            ('regionX', v[0] // x),  # TODO it says that the x/y can't be non-zero most of the time. why?
                            ('regionY', v[1] // y),
                            ('regionW', v[2] // x),  # TODO this is still out-of-bounds under binning. what math are they doing?
                            ('regionH', v[3] // y),
                        ],
                        autoRestart=autoRestart,
                        autoCorrect=autoCorrect,
                    )
                    newvals['region'] = (newvals['regionX'], newvals['regionY'], newvals['regionW'], newvals['regionH'])
                elif p == 'binning':
                    newvals, _r = self.setParams(
                        [('binningX', v[0]), ('binningY', v[1])], autoRestart=autoRestart, autoCorrect=autoCorrect
                    )
                    newvals['binning'] = (newvals['binningX'], newvals['binningY'])
                elif p == 'triggerMode':
                    if v == 'Normal':
                        self._dev.TriggerMode.set(False)
                    else:
                        self._dev.TriggerMode.set(True)
                    newvals = {p: v}
                    _r = True
                elif p == 'exposure':
                    self._dev.ExposureTimeAbs.set(v * 1000)
                    newvals = {p: v}
                    _r = True
                else:
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


# TODO stream features:
        #          Feature name   : StreamID
        #          Feature name   : StreamType
        #          Feature name   : StreamAnnouncedBufferCount
        #          Feature name   : StreamAcquisitionModeSelector
        #          Feature name   : StreamBufferHandlingMode
        #          Feature name   : StreamAnnounceBufferMinimum
        #          Feature name   : StreamInputBufferCount
        #          Feature name   : StreamOutputBufferCount
        #          Feature name   : StreamIsGrabbing
        #          Feature name   : MulticastEnable
        #          Feature name   : MulticastIPAddress
        #          Feature name   : GVSPFilterVersion
        #          Feature name   : GVSPFilterCompatibility
        #          Feature name   : GVSPTimeout
        #          Feature name   : GVSPDriver
        #          Feature name   : GVSPHostReceiveBufferSize
        #          Feature name   : GVSPBurstSize
        #          Feature name   : GVSPMaxLookBack
        #          Feature name   : GVSPMaxRequests
        #          Feature name   : GVSPMissingSize
        #          Feature name   : GVSPTiltingSize
        #          Feature name   : GVSPMaxWaitSize
        #          Feature name   : GVSPPacketSize
        #          Feature name   : GVSPAdjustPacketSize
        #          Feature name   : GVSPProtocol
        #          Feature name   : FrameStatisticsCounter
        #          Feature name   : FrameStatisticsCounterSelector
        #          Feature name   : FramePacketStatisticsCounter
        #          Feature name   : FramePacketStatisticsCounterSelector
        #          Feature name   : FrameRate
        #          Feature name   : FrameRateSelector
        #          Feature name   : StreamTimeElapsed
        #          Feature name   : StatPacketUnavailable
        #          Feature name   : StatFrameDelivered
        #          Feature name   : StatFrameDropped
        #          Feature name   : StatFrameUnderrun
        #          Feature name   : StatFrameShoved
        #          Feature name   : StatFrameRescued
        #          Feature name   : StatPacketReceived
        #          Feature name   : StatPacketMissed
        #          Feature name   : StatPacketErrors
        #          Feature name   : StatPacketRequested
        #          Feature name   : StatPacketResent
        #          Feature name   : StatFrameRate
        #          Feature name   : StatLocalRate
        #          Feature name   : StatTimeElapsed


def show_features(obj, prefix=''):
    for feature in obj.get_all_features():
        print(f'{prefix} {feature.get_name():<40} : {feature.get_tooltip()}')
        # print(f'{prefix} Display name   : {feature.get_display_name()}')
        # print(f'{prefix} Tooltip        : {feature.get_tooltip()}')
        # print(f'{prefix} Description    : {feature.get_description()}')
        # print(f'{prefix} SFNC Namespace : {feature.get_sfnc_namespace()}')
        # print(f'{prefix} Visibility     : {feature.get_visibility()}')
        with contextlib.suppress(Exception):
            value = feature.get()
            # print(f'{prefix} Value          : {value}')
        # print()


def main():
    from time import sleep

    class MockManager:
        def declareInterface(self, *args, **kwargs):
            pass
    cam = VimbaXCamera(MockManager(), {'id': 'DEV_000F315B9827'}, 'test')
    print(cam.getParam('bitDepth'))
    cam.setParam('region', (0, 0, 40, 40))
    cam.setParam('exposure', 0.01)
    cam.setParam('triggerMode', 'Normal')
    cam.setParam('binning', (2, 2))
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
    cam.quit()


if __name__ == '__main__':
    main()
