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
            bgFrameArray = np.stack([f.data() for f in bgFrames], axis=0)
            bgFrame = bgFrameArray.mean(axis=0)

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
        cs = np.cumsum(avg - avg.min())
        centerIndex = np.searchsorted(cs, cs.max()/2, 'left')

        # get time of the frame with the center point
        centerTime = pipetteCameraDelay + frames[centerIndex].info()['time']
        # get position of pipette at center time
        centerPipPos = getPipettePositionAtTime(posEvents, centerTime)

        # move back to center position
        pipette._moveToGlobal(centerPipPos, speed='fast').wait()

        # todo: at this point we could compare the current image to the previously collected video
        # to see whether we made it back to the desired position (and if not, apply
        # a correction as well as remember the apparent time delay between camera images and
        # position updates)

        # record from imager and pipette position while retracting pipette out of frame
        retractPos = centerPipPos - pipVector * 2e-3
        frames2, posEvents2 = watchMovingPipette(pipette, imager, retractPos, speed=searchSpeed, _future=_future)

        # measure image intensity at a line perpendicular to the pipette that crosses the center of the frame        
        profile, interpCoords = interpolate_orthogonal_line(frames2, bgFrame, pipVector)
        # avg should be drifting at the beginning and flat at the end
        # the point where we transition from drifting to flat should be where the pipette tip crosses
        # the center of the frame
        avg2 = np.abs(profile).mean(axis=1)

        # do the same for background frames
        bgProfile, _ = interpolate_orthogonal_line(bgFrames, bgFrame, pipVector)
        bgAvg2 = np.abs(bgProfile.mean(axis=1))
        
        # choose threshold for detecting pipette tip crossing the center
        thresholdSize = max(bgAvg2.std() * 3, 0.2 * (avg2.max()-avg2[-1]))
        threshold = avg2[-1] + thresholdSize

        # find index where we just reach the flat region
        endIndex = np.argwhere(avg2 > threshold).max()
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
        zStackArray = np.stack([frame.data() for frame in zStack])
        zDiff = np.abs(np.diff(zStackArray.astype(float), axis=0))
        zProfile = zDiff.max(axis=2).max(axis=1)
        zProfCs = np.cumsum(zProfile - zProfile.min())
        zThreshold = 0.1 * zProfCs.max()
        zIndex = np.searchsorted(zProfCs, zThreshold)
        tipFrame = zStack[zIndex]
        
        # find tip 
        tipImg = zDiff[zIndex]
        tipThreshold = 0.5 * (tipImg.max() + tipImg.min())
        imgPos = np.argwhere(tipImg > tipThreshold).mean(axis=0)
        globalPos = tipFrame.mapFromFrameToGlobal([imgPos[0], imgPos[1], 0])
        pipette.resetGlobalPosition(globalPos)

        # focusScore = score_frames(zStack)
        # targetScore = focusScore.min() + 0.1 * (focusScore.max() - focusScore.min())
        # focusIndex = np.argwhere(focusScore > targetScore)[:,0].min()
        # depth = zStack[focusIndex].mapFromFrameToGlobal([0, 0, 0])[2]

        imager.setFocusDepth(globalPos[2]).wait()

        # find tip!
        # cal = pipette.tracker.autoCalibrate()

    finally:
        _future.l = locals().copy()


def interpolate_orthogonal_line(frames, bgFrame, pipVector):
    """Given a video in *frames* and a background frame to subtract, return
    a 2D slice of the video data across all frames and along the diagonal line that is
    orthogonal to the pipette x axis and passes through the center of the frame
    
    This is a cheaper way of measuring the cross-section of the pipette
    without having to rotate the entire video relative to the pipette yaw angle.

    Returns
    -------
        profile : ndarray of shape (n_frames, n_points)
            The 2D profile (frames, points) sliced from the video
        interpCoords : ndarray of shape (n_points, 2)
            The (row,col) image coordinates chosen to slice values from the video.
            len(interpCoords) == profile.shape[1]
    """
    center = np.array(frames[0].shape) // 2
    frame_tr = frames[0].globalTransform().inverted()[0]
    imgVector = frame_tr.map(pipVector) - frame_tr.map([0, 0, 0])
    imgVector /= np.linalg.norm(imgVector)
    orthoVector = np.array([imgVector[1], -imgVector[0]])  # 90 deg CW

    radiusPx = (center**2).sum()**0.5
    start = center - radiusPx * orthoVector
    interpCoords = start + np.arange(int(radiusPx*2))[:, np.newaxis] * orthoVector[np.newaxis, :]

    profile = np.empty((len(frames), interpCoords.shape[0]))
    for i,frame in enumerate(frames):
        profile[i] = scipy.interpolate.interpn(
            points=(np.arange(frame.shape[0]), np.arange(frame.shape[1])),
            values=frame.data() - bgFrame,
            xi=interpCoords,
            method='nearest',
            bounds_error=False,
            fill_value=0,
        )
    return profile, interpCoords

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



    


