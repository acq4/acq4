.. _userCalibration:

Configuring and Calibrating Hardware
====================================

Many of ACQ4's advanced features require that it has an accurate internal representation of your hardware. For example, perhaps you want to take multiple pictures of your sample at different locations and magnifications, and be able to reconstruct the mosaic later on. Or perhaps you want to be able to click on a cell and have a pipette tip or laser move automatically to the cell. For ACQ4 to make these cases possible, it needs to know which devices are physically attached to each other, their relative position and orientation, the magnification of each objective lens, and so on.

This section describes the recommended procedure for configuring hardware in a standard patch ephys + imaging rig to support these features. Most of the steps here involve modifying your :ref:`device configuration file <userConfiguration>`. Each step builds on previous steps, so it is important to follow each section in order.

Coordinate Systems
------------------

ACQ4 uses a global coordinate system to represent the locations of physical objects and data in the experiment -- for example images, cells, pipette tips, and photostimulus patterns. We define the coordinate system as follows:

1. The origin of the global coordinate system is in the center of the sample / recording chamber, on the top surface of the glass that would hold the sample. (This choice is arbitrary, but we find it helps us visualize and understand the global coordinate system if it always has a consistent origin).
2. The X axis points toward the right side of the microscope stage, the Y axis points toward the microscope / away from the operator, and the Z axis points up.
3. The coordinate system has units of unscaled meters. For example, a distance of 10 μm is represented as 10e-6 in this system (in fact, all data in acq4 are represented in unscaled SI units).

    .. figure:: images/global_cs.svg


1. Camera Scale
---------------

This step tells ACQ4 about the physical size of pixels in your camera sensor. For now this is just about the camera sensor itself; later on we will add in the per-objective corrections that let us relate pixels to distances on the sample being imaged.

1. Look up the pixel size reported by the manufacturer for your camera.
2. This should be written in to the transform:scale option in the camera config like::

    Camera:
        ...
        transform:
            scale: 6.5*um/px, 6.5*um/px


2. Camera Orientation
---------------------

Most calibrations that follow use the camera to make measurements. Thus, 

This step tells acq4 about the orientation of your camera around its Z axis--its X and Y axes should align with the X and Y axes of the stage.

1. First we need to ensure that your camera image is not mirrored or rotated incorrectly. Place an object under the microscope objective that can be used to verify the orientation of the camera. For example, a micrometer slide where the correct orientation is known, or very fine print, or the letter "R" written about 1-2 mm tall on a slip of paper.
2. Load the camera module and start live video display (click "Acquire Video"); focus on the object.
3. The appearance on screen should be in the same orientation as under the microscope:
    a. The rightward and leftward directions for an operator facing the computer screen should be the same as the rightward and leftward directions when facing the microscope. This is the X axis in acq4's global coordinate system
    b. The upward direction on the screen should be the same as the direction pointing away from the operator, toward the microscope. This is the Y axis in acq4's global coordinate system.
4. If the camera view is rotated relative to the physical object, then you can either rotate the camera to match, or add a rotation to the camera's transform->angle configuration option
5. If the camera view is reversed relative to the physical object, then you need to multiply one of the x- or y-scale factors by -1 in the camera's transform->scale configuration.
6. To ensure that the camera is precisely orthogonal to the stage axes, put an ROI on a visible feature when said feature is at the extreme leftmost edge of the field of view. Then move the stage such that the feature is at the extreme rightmost edge of the view and measure the difference in Y value between the ROI and the feature.
7. Physically rotate the camera around its Z axis to compensate for half the observed drift.
8. Repeat 6-7 until sufficiently oriented.




3. Verify the scale using a micrometer slide. ACQ4’s Camera module has a scale bar at the bottom right for reference, or use a ruler ROI to be more precise





