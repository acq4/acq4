"""Frozen copy of CameraTaskResult and CameraTask.getResult() from before partial results; test oracle only."""
from __future__ import annotations

import numpy as np

from MetaArray import MetaArray, axis
from acq4.util.Mutex import Mutex


def legacyGetResult(frames, daqResult, task):
    """The result the original CameraTask.getResult() built from the final *frames* and *daqResult*."""
    return LegacyCameraTaskResult(task, frames, daqResult)


class LegacyCameraTaskResult:
    def __init__(self, task, frames, daqResult):
        self.lock = Mutex(recursive=True)
        self._task = task
        self._frames = frames
        self._daqResult = daqResult
        self._marr = None
        self._arr = None
        self._frameTimes = None
        self._frameTimesPrecise = False

    def frames(self):
        """Return a list of Frame instances collected during the task"""
        return self._frames[:]

    def info(self):
        """Return meta-info for the first frame recorded or {} if there were no frames."""
        if len(self._frames) == 0:
            return {}
        info = self._frames[0].info().copy()
        info.update({"preciseTiming": self._frameTimesPrecise})
        return info

    def asArray(self):
        with self.lock:
            if self._arr is None:
                if len(self._frames) > 0:
                    self._arr = np.concatenate([f.data()[np.newaxis, ...] for f in self._frames])
        return self._arr

    def asMetaArray(self):
        """Return a MetaArray containing all frame and timing data"""
        with self.lock:
            if self._marr is None:
                arr = self.asArray()
                if arr is not None:
                    times, precise = self.frameTimes()
                    times = times[: arr.shape[0]]
                    info = [
                        axis(name="Time", units="s", values=times),
                        axis(name="x"),
                        axis(name="y"),
                        self.info(),
                    ]
                    self._marr = MetaArray(arr, info=info)

        return self._marr

    def daqResult(self):
        """Return results of DAQ channel recordings"""
        return self._daqResult

    def frameTimes(self):
        if self._frameTimes is None:
            # generate MetaArray of images collected during recording
            times = None
            precise = False  # becomes True if we are able to determine precise frame times.
            with self.lock:
                if (
                    len(self._frames) > 0
                ):  # extract frame times as reported by camera. This is a first approximation.
                    try:
                        times = np.array([f.info()["time"] for f in self._frames])
                    except:
                        raise
                    times -= times[0]
                else:
                    return None, False

                expose = None
                daqResult = self._daqResult
                if daqResult is not None and daqResult.hasColumn("Channel", "exposure"):
                    expose = daqResult["Channel":"exposure"]

            # Correct times for each frame based on data recorded from exposure channel.
            if expose is not None:

                # Extract times from trace
                ex = expose.view(np.ndarray).astype(np.int32)
                exd = ex[1:] - ex[:-1]

                timeVals = expose.xvals("Time")
                inds = np.argwhere(exd > 0.5)[:, 0] + 1
                onTimes = timeVals[inds]

                # If camera triggered DAQ, then it is likely we missed the first 0->1 transition
                if self._task.camCmd.get("triggerProtocol", False) and ex[0] > 0.5:
                    onTimes = np.array([timeVals[0]] + list(onTimes))

                inds = np.argwhere(exd < 0.5)[:, 0] + 1
                offTimes = timeVals[inds]

                # Determine average frame transfer time
                txLen = (offTimes[: len(times)] - times[: len(offTimes)]).mean()

                # Determine average exposure time (excluding first frame, which is often shorter)
                expLen = (offTimes[1 : len(onTimes)] - onTimes[1 : len(offTimes)]).mean()

                if self._task.camCmd["params"].get(
                    "triggerMode", "Normal"
                ) == "Normal" and not self._task.camCmd.get("triggerProtocol", False):
                    # Can we make a good guess about frame times even without having triggered the first frame?
                    # frames are marked with their arrival time. We will assume that a frame most likely
                    # corresponds to the last complete exposure signal.
                    pass

                elif len(onTimes) > 0:
                    # If we triggered the camera (or if the camera triggered the DAQ),
                    # then we know frame 0 occurred at the same time as the first expose signal.
                    # New times list is onTimes, any extra frames just increment by tx+exp time
                    times[: len(onTimes)] = onTimes[
                        : len(times)
                    ]  # set the times for which we detected an exposure pulse

                    # Try to determine mean framerate
                    if len(onTimes) > 1:
                        framePeriod = (onTimes[-1] - onTimes[0]) / (len(onTimes) - 1)
                    else:
                        framePeriod = (times[-1] - times[0]) / (len(times) - 1)

                    # For any extra frames that did not have an exposure signal, just try
                    # to guess the correct time based on the average framerate.
                    lastTime = onTimes[-1]
                    if framePeriod is not None:
                        for i in range(len(onTimes), len(times)):
                            lastTime += framePeriod
                            times[i] = lastTime

                    precise = True

            self._frameTimes = times
            self._frameTimesPrecise = precise

        return self._frameTimes, self._frameTimesPrecise
