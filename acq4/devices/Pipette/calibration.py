import numpy as np
import scipy.interpolate
from acq4.util.surface import find_surface, score_frames
from .pipette import Pipette
from acq4.devices.Camera import Camera
from .planners import PipetteMotionPlanner
from acq4.util.future import Future
from acq4.util.imaging.sequencer import acquire_z_stack


@Future.wrap
def calibratePipette(pipette: Pipette, imager: Camera, scopeDevice, searchSpeed=0.5e-3, pipetteCameraDelay=0, _future=None):
    """
    Find the tip of a new pipette by moving it across the objective while recording from the imager.
    """

    try:
        # focus 2mm above surface
        surfaceZ = scopeDevice.getSurfaceDepth()
        startDepth = surfaceZ + 2e-3
        _future.waitFor(imager.setFocusDepth(startDepth))

        # collect background images, analyze noise
        with imager.ensureRunning():
            bgFrames = imager.acquireFrames(10).getResult()
            bgFrames = np.stack([f.data() for f in bgFrames], axis=0)
            bgFrame = bgFrames.mean(axis=0)

        # move pipette to search position
        center = imager.globalCenterPosition(mode='roi')
        pipVector = pipette.globalDirection()
        pipY = np.cross(pipVector, [0, 0, 1])
        searchPos1 = center + pipVector * 1e-3 + pipY * 2e-3
        searchPos2 = center + pipVector * 1e-3 - pipY * 2e-3
        # using a planner avoids possible collisions with the objective
        planner = PipetteMotionPlanner(pipette, searchPos1, speed='fast')
        _future.waitFor(planner.move())

        # record from imager and pipette position while moving pipette across the objecive
        frames, posEvents = watchMovingPipette(pipette, imager, searchPos2, speed=searchSpeed, _future=_future)

        # analyze frames for center point
        # avg should be mostly flat with a symmetrical bumpy thing in the middle
        avg = np.array([((frame.data() - bgFrame)**2).mean() for frame in frames])

        # Find the center of the bump
        cs = np.cumsum(avg)
        centerIndex = np.searchsorted(cs, cs.max()/2, 'left')

        # center of mass should be close to the center of the bump
        # centerOfMass = np.percentile(np.cumsum(signal), 50)
        # find where close to the center of mass is the derivative zero
        # deriv = np.diff(signal)
        # roots = np.argwhere((signal[1:] >= 0) != (signal[:-1])).flatten()
        # centerIdx = np.argmin(np.abs(roots - centerOfMass))

        # get time of the frame with the center point
        centerTime = pipetteCameraDelay + frames[centerIndex].info()['time']
        # get position of pipette at center time
        centerPipPos = getPipettePositionAtTime(posEvents, centerTime)

        # move back to center position
        pipette._moveToGlobal(centerPipPos, speed='fast').wait()

        # record from imager and pipette position while retracting pipette out of frame
        retractPos = centerPipPos - pipVector * 2e-3
        frames2, posEvents2 = watchMovingPipette(pipette, imager, retractPos, speed=searchSpeed, _future=_future)

        # analyze frames for center point
        # direction of 
        # pick a line perpendicular to the pipette that crosses the center of the frame        
        center = np.array(frames2[0].shape) // 2
        frame_tr = frames2[0].globalTransform().inverted()[0]
        imgVector = frame_tr.map(pipVector) - frame_tr.map([0, 0, 0])
        imgVector /= np.linalg.norm(imgVector)
        orthoVector = np.array([imgVector[1], -imgVector[0]])  # 90 deg CW

        radiusPx = (center**2).sum()**0.5
        start = center - radiusPx * orthoVector
        interpCoords = start + np.arange(int(radiusPx*2))[:, np.newaxis] * orthoVector[np.newaxis, :]

        profile = np.empty((len(frames2), interpCoords.shape[0]))
        for i,frame in enumerate(frames2):
            profile[i] = scipy.interpolate.interpn(
                points=(np.arange(frame.shape[0]), np.arange(frame.shape[1])),
                values=frame.data() - bgFrame,
                xi=interpCoords,
                method='nearest',
                bounds_error=False,
                fill_value=0,
            )

        # avg should be drifting at the beginning and flat at the end
        avg2 = np.abs(profile.mean(axis=1))

        # find index where we just reach the flat region
        endIndex = len(avg2) - np.searchsorted(avg2[::-1], avg2[-1] + 0.02 * (avg2.max()-avg2[-1]))
        endTime = pipetteCameraDelay + frames2[endIndex].info()['time']
        
        # find pipette position at end time
        endPipPos = getPipettePositionAtTime(posEvents2, endTime)

        # find center of mass when the pipette crossed the center of the frame
        cs2 = np.cumsum(np.abs(profile[endIndex]))
        centerIndex2 = np.searchsorted(cs2, cs2.max()/2, 'left')
        centerPosPx = interpCoords[centerIndex2]
        # centerPos = frames2[0].globalTransform().map(list(centerPosPx) + [0])
        yDistPx = centerIndex2 - len(interpCoords) // 2
        yDist = frames2[0].info()['pixelSize'][0] * yDistPx


        # # add 1/2 width of fov
        # halfFrameWidth = frames2[0].info()['pixelSize'][0] * (frames2[0].data().shape[0] //2)
        # centerPipPos2 = endPipPos + pipVector * halfFrameWidth 
        centerPipPos2 = endPipPos + np.array([0, yDist, 0])

        # move to new center
        pipette._moveToGlobal(centerPipPos2, speed='fast').wait()

        # autofocus
        z_range = (startDepth - 500e-6, startDepth + 500e-6, 10e-6)
        zStack = acquire_z_stack(imager, *z_range, block=True).getResult()
        focusScore = score_frames(zStack)
        targetScore = focusScore.min() + 0.1 * (focusScore.max() - focusScore.min())
        focusIndex = np.argwhere(focusScore > targetScore)[:,0].min()
        depth = zStack[focusIndex].mapFromFrameToGlobal([0, 0, 0])[2]
        imager.setFocusDepth(depth).wait()

        # find tip!
        cal = pipette.tracker.autoCalibrate()

    finally:
        _future.l = locals().copy()


def watchMovingPipette(pipette: Pipette, imager: Camera, pos, speed, _future):
    with imager.ensureRunning():
        pipRecorder = None
        imgFuture = None
        try:
            imgFuture = imager.acquireFrames()
            pipRecorder = pipette.startRecording()
            pipFuture = pipette._moveToGlobal(pos, speed=speed)
            _future.waitFor(pipFuture)
        finally:
            if pipRecorder is not None:
                pipRecorder.stop()
            if imgFuture is not None:
                imgFuture.stop()    

    # return only position change events
    events = [ev for ev in pipRecorder.events if ev['event'] == 'position_change']

    return imgFuture.getResult(), events


def getPipettePositionAtTime(events, time):
    pipTimes = [ev['event_time'] for ev in events]
    pipIndex = np.searchsorted(pipTimes, time, 'left')
    pipPos = events[pipIndex]['position']
    return pipPos



    


