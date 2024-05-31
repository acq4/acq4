import numpy as np
from .pipette import Pipette
from acq4.devices.Camera import Camera
from .planners import PipetteMotionPlanner
from acq4.util.future import Future


@Future.wrap
def calibratePipette(pipette: Pipette, imager: Camera, scopeDevice, _future):
    """
    Find the tip of a new pipette by moving it across the objective while recording from the imager.
    """
    # focus 2mm above surface
    surfaceZ = scopeDevice.getSurfaceDepth()
    _future.waitFor(imager.setFocusDepth(surfaceZ + 2e-3))

    # move pipette to search position
    center = imager.globalCenterPosition(mode='roi')
    pipVector = pipette.globalDirection()
    pipY = np.cross(pipVector, [0, 0, 1])
    searchPos1 = center + pipVector * 1e-3 + pipY * 2e-3
    searchPos2 = center + pipVector * 1e-3 - pipY * 2e-3
    # using a planner avoids possible collisions with the objective
    planner = PipetteMotionPlanner(pipette, searchPos1, speed=1e-3)
    _future.waitFor(planner.move())

    # record from imager and pipette position while moving pipette across the objecive
    with imager.ensureRunning():
        try:
            imgFuture = imager.acquireFrames()
            pipRecorder = pipette.startRecording()
            planner = PipetteMotionPlanner(pipette, searchPos2, speed=1e-3)
            _future.waitFor(planner.move())
        finally:
            pipRecorder.stop()
            imgFuture.stop()

    # analyze frames for center point
    frames = imgFuture.getResult()
    avg = np.array([frame.data().mean() for frame in frames])
    # avg should be mostly flat with a symmetrical bumpy thing in the middle
    signal = (avg - avg[0]) ** 2
    # center of mass should be close to the center of the bump
    centerOfMass = np.percentile(np.cumsum(signal), 50)
    # find where close to the center of mass is the derivative zero
    deriv = np.diff(signal)
    roots = np.argwhere(signal[1:] >= 0 != signal[:-1]).flatten()
    centerIdx = np.argmin(np.abs(roots - centerOfMass))

    # get time of the frame with the center point
    centerTime = frames[centerIdx].info()['time']
    # get position of pipette at center time
    # TODO: pipRecorder should make use of existing code to organize event logging data (so we can ask for position at time)








    

