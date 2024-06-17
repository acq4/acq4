from __future__ import annotations

import contextlib

import numpy as np

from acq4.devices.Camera import Camera
from vmbpy import VmbSystem, Camera as VmbCamera, VmbCameraError, VmbFeatureError


class VimbaXCamera(Camera):
    """Camera class for VimbaX cameras. See https://github.com/alliedvision/VmbPy for driver install instructions."""

    def __init__(self, dm, config, name):
        self._dev: VmbCamera | None = None
        self._config = config
        self._paramProperties = None
        self._allParamNames = ['triggerMode', 'exposure', 'binning', 'region', 'gain', 'sensorSize', 'bitDepth']
        super().__init__(dm, config, name)
        # TODO Camera DEV_000F315B9827: GVSPPacketSize not optimized for streaming GigE Vision. Enable jumbo packets for improved performance.
        # TODO stream.GVSPAdjustPacketSize.run() somehow?
        #                 with contextlib.suppress(AttributeError, VmbFeatureError):
        #                     stream = self._dev.get_streams()[0]
        #                     stream.GVSPAdjustPacketSize.run()
        #                     while not stream.GVSPAdjustPacketSize.is_done():
        #                         pass

    def setupCamera(self):
        with VmbSystem.get_instance() as vmb:
            _id = self._config['id']
            try:
                self._dev = vmb.get_camera_by_id(_id)
            except VmbCameraError as e:
                available = "', '".join(c.get_id() for c in vmb.get_all_cameras())
                raise ValueError(f"Failed to open camera with id '{_id}'. Available: '{available}'") from e
            # TODO fill in more _allParamNames

    def listParams(self, params=None):
        if self._paramProperties is None:
            self._paramProperties = {
                'binningX': ((1, 2, 4), True),
                'binningY': ((1, 2, 4), True),
                'regionX': ((0, self.getParam('sensorWidth') - 1), True),
                'regionY': ((0, self.getParam('sensorHeight') - 1), True),
                'regionW': ((1, self.getParam('sensorWidth')), True),
                'regionH': ((1, self.getParam('sensorHeight')), True),
            }
            # TODO discover all the others
        if params is None:
            return self._paramProperties
        return {p: self._paramProperties[p] for p in params}

    def getParams(self, params=None):
        # AcquisitionAbort
        # AcquisitionFrameCount
        # AcquisitionFrameRateAbs
        # AcquisitionFrameRateLimit
        # AcquisitionMode
        # AcquisitionStart
        # AcquisitionStop
        # BandwidthControlMode
        # BinningHorizontal
        # BinningVertical
        # BlackLevel
        # BlackLevelSelector
        # ChunkModeActive
        # DSPSubregionBottom
        # DSPSubregionLeft
        # DSPSubregionRight
        # DSPSubregionTop
        # DeviceFirmwareVersion
        # DeviceID
        # DeviceModelName
        # DevicePartNumber
        # DeviceScanType
        # DeviceTemperature
        # DeviceTemperatureSelector
        # DeviceVendorName
        # EventAcquisitionEnd
        # EventAcquisitionRecordTrigger
        # EventAcquisitionStart
        # EventError
        # EventExposureEnd
        # EventFrameTrigger
        # EventFrameTriggerReady
        # EventLine1FallingEdge
        # EventLine1RisingEdge
        # EventLine2FallingEdge
        # EventLine2RisingEdge
        # EventLine3FallingEdge
        # EventLine3RisingEdge
        # EventLine4FallingEdge
        # EventLine4RisingEdge
        # EventNotification
        # EventOverflow
        # EventSelector
        # EventsEnable1
        # ExposureAuto
        # ExposureAutoAdjustTol
        # ExposureAutoAlg
        # ExposureAutoMax
        # ExposureAutoMin
        # ExposureAutoOutliers
        # ExposureAutoRate
        # ExposureAutoTarget
        # ExposureMode
        # ExposureTimeAbs
        # FirmwareVerBuild
        # FirmwareVerMajor
        # FirmwareVerMinor
        # Gain
        # GainAuto
        # GainAutoAdjustTol
        # GainAutoMax
        # GainAutoMin
        # GainAutoOutliers
        # GainAutoRate
        # GainAutoTarget
        # GainSelector
        # Gamma
        # GevSCPSPacketSize
        # GevTimestampControlLatch
        # GevTimestampControlReset
        # GevTimestampTickFrequency
        # GevTimestampValue
        # Height
        # HeightMax
        # ImageSize
        # LUTAddress
        # LUTBitDepthIn
        # LUTBitDepthOut
        # LUTEnable
        # LUTIndex
        # LUTLoadAll
        # LUTMode
        # LUTSaveAll
        # LUTSelector
        # LUTSizeBytes
        # LUTValue
        # NonImagePayloadSize
        # OffsetX
        # OffsetY
        # PayloadSize
        # PixelFormat
        # RecorderPreEventCount
        # SensorBits
        # SensorHeight
        # SensorType
        # SensorWidth
        # StreamBytesPerSecond
        # StreamFrameRateConstrain
        # StreamHoldCapacity
        # StreamHoldEnable
        # StrobeDelay
        # StrobeDuration
        # StrobeDurationMode
        # StrobeSource
        # SyncInGlitchFilter
        # SyncInLevels
        # SyncInSelector
        # SyncOutLevels
        # SyncOutPolarity
        # SyncOutSelector
        # SyncOutSource
        # TriggerActivation
        # TriggerDelayAbs
        # TriggerMode
        # TriggerOverlap
        # TriggerSelector
        # TriggerSoftware
        # TriggerSource
        # UserSetDefaultSelector
        # UserSetLoad
        # UserSetSave
        # UserSetSelector
        # Width
        # WidthMax

        def name(f):
            n = f.get_name()
            return n[0].lower() + n[1:]

        with VmbSystem.get_instance():
            with self._dev:
                if params is None:
                    return self.getParams(self._allParamNames)
                retval = {}
                for p in params:
                    if p == 'sensorSize':
                        retval[p] = (self.getParam('sensorWidth'), self.getParam('sensorHeight'))
                    elif p == 'binning':
                        retval[p] = (self.getParam('binningX'), self.getParam('binningY'))
                    elif p == 'region':
                        retval[p] = (self.getParam('regionX'), self.getParam('regionY'),
                                     self.getParam('regionW'), self.getParam('regionH'))
                    else:
                        retval[p] = getattr(self._dev, _mapParamNameToFeatureName(p)).get()
                return retval

    def setParams(self, params: dict | list[tuple], autoRestart=True, autoCorrect=True):
        retval = {}
        restart = False
        with VmbSystem.get_instance():
            with self._dev:
                if isinstance(params, dict):
                    params = params.items()
                for p, v in params:
                    if p == 'region':
                        x, y = self.getParam('binning')
                        newvals, _r = self.setParams(
                            [
                                ('regionX', v[0] // x),
                                ('regionY', v[1] // y),
                                ('regionW', v[2] // x),  # TODO this is still out-of-bounds. what math are they doing?
                                ('regionH', v[3] // y),
                            ],
                            autoRestart=autoRestart,
                            autoCorrect=autoCorrect,
                        )
                    elif p == 'binning':
                        newvals, _r = self.setParams(
                            [('binningX', v[0]), ('binningY', v[1])], autoRestart=autoRestart, autoCorrect=autoCorrect
                        )
                    else:
                        getattr(self._dev, _mapParamNameToFeatureName(p)).set(v)
                        # TODO autocorrect
                        newvals = {p: v}
                        _r = False  # TODO ?
                    retval.update(newvals)
                    restart = restart or _r
        # TODO autoRestart
        return retval, restart

    def newFrames(self):
        pass

    def startCamera(self):
        pass

    def stopCamera(self):
        pass

    def _acquireFrames(self, n) -> np.ndarray:
        with VmbSystem.get_instance():
            with self._dev:
                return np.concatenate(
                    [f.as_numpy_ndarray()[np.newaxis, ...] for f in self._dev.get_frame_generator(n)]
                )


def _mapParamNameToFeatureName(name):
    known_map = {
        'binningX': 'BinningHorizontal',
        'binningY': 'BinningVertical',
        'regionX': 'OffsetX',
        'regionY': 'OffsetY',
        'regionW': 'Width',
        'regionH': 'Height',
        'bitDepth': 'SensorBits',
        'exposure': 'ExposureTimeAbs',
    }
    return known_map.get(name, name[0].upper() + name[1:])


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
    class MockManager:
        def declareInterface(self, *args, **kwargs):
            pass
    cam = VimbaXCamera(MockManager(), {'id': 'DEV_000F315B9827'}, 'test')
    print(cam.getParam('bitDepth'))
    fut = cam.driverSupportedFixedFrameAcquisition(5)
    f = fut.getResult()
    print(len(f))
    # with VmbSystem.get_instance() as _v:
    #     _cam = _v.get_all_cameras()[0]
    #     print(f'Camera ID: {_cam.get_id()}')
    #     with _cam:
    #         show_features(_cam)
    #         for stream in _cam.get_streams():
    #             show_features(stream, '\t')


if __name__ == '__main__':
    main()
