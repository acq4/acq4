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
        parentDevice: 'Microscope'
        transform:
            scale: 6.5*um/px, 6.5*um/px


2. Objective Scaling
--------------------

Here we tell acq4 about the magnification factors of your objective lenses. These factors, combined with the physical size of pixels on your camera sensor, tells us how large one image pixel is relative to the sample that is being imaged.

1. Make sure all objectives are added to the *Microscope* device in your device configuration file, with proper scale factors. A 5x objective, for example, should have a scale factor very close to 1.0/5.0. For example::

    Microscope:
        driver: 'Microscope'
        parentDevice: 'Stage'
        objectives:
            0:  # first slot
                5x_0.25NA:
                    name: '5x 0.25na FLUAR'
                    scale: 1.0 / 5.0
            1:  # second slot
                40x:
                    name: '40x 0.75na Achroplan'
                    scale: 1.0 / 40.0


This value can be adjusted by a small amount to correct for manufacturing tolerance (but most scientific objectives have good accuracy here).
Some microscopes may have extra optics to increase or reduce the total magnification. In that case, the extra magnification should be included in the value for each objective.

2. Verify the scale factor by imaging a micrometer slide and measuring the distance between lines using the ruler ROI tool in the camera module. Check that the scale is reported correctly for all objectives. ACQ4 should automatically keep track of which objective is currently in use and adjust accordingly. If the correct objective is not selected, then a device misconfiguration may be to blame. If your hardware does not support reporting the objective that is currently in use, then it is necessary to manually select the current objective via the Microscope dock in the main Manager window whenever it changes.


3. Camera Orientation
---------------------

By convention, we say that the global X and Y axes are aligned with the rows and columns of the camera sensor. This is not strictly required (it's possible to use the camera at any angle); however, we also represent the global X and Y axes as rows and columns of pixels *on screen*. For image display, it's appealing to have the camera and screen perfectly aligned.

First we should ensure that the camera image is correctly rotated / mirrored such that the image onscreen matches the orientation of the sample:

* The rightward direction onscreen points toward the right side of the rig
* The upward direction onscreen points toward the back of the rig, away from the operator

1. Place an object under the microscope objective that can be used to verify the orientation of the camera. For example, a micrometer slide where the correct orientation is known, or very fine print, or the letter "R" written about 1-2 mm tall on a slip of paper.
2. Load the camera module and start live video display (click "Acquire Video"); focus on the object.
3. The appearance on screen should be in the same orientation as under the microscope:
    a. The rightward and leftward directions for an operator facing the computer screen should be the same as the rightward and leftward directions when facing the microscope. This is the X axis in acq4's global coordinate system
    b. The upward direction on the screen should be the same as the direction pointing away from the operator, toward the microscope. This is the Y axis in acq4's global coordinate system.
4. If the camera view is rotated relative to the physical object, then you can either physically rotate the camera to match, or add a rotation to the camera's transform->angle configuration option::

    Camera:
        ...
        transform:
            scale: 6.5*um/px, 6.5*um/px
            angle: -90                   # rotate camera image 90 deg

5. If the camera view is reversed (mirrored) relative to the physical object, then you need to multiply one of the x- or y-scale factors by -1 in the camera's transform->scale configuration::

    Camera:
        ...
        transform:
            scale: 6.5*um/px, -6.5*um/px  # invert y axis to flip image vertically
            angle: -90


4. Stage Orientation
--------------------

The next step is to ensure that acq4 understands how the stage's x,y,z axes are oriented and scaled relative to the global coordinate system.

1. Check z-axis scale and orientation. We assume that your stage's Z axis is vertical.
    a. The configuration for your stage device should have a ``scale:`` section that contains x,y,z scale factors to convert from hardware-reported
       position values to unscaled meters. These values are usually 1e-6 (most devices report their position in micrometers). If you are not certain 
       of this value, choose 1e-6 for now; we'll correct it later::

            Stage:
                driver: 'Sensapex'
                device: 20
                scale: 1.0e-6, 1.0e-6, -1.0e-6  # x,y,z scale factors relating hardware-reported position to global coordinates

    a. Load the Camera module, find the "Depth" plot, and look for the yellow line indicating the Z position of the focal plane.       
    b. Verify that when focusing the objective lens physically upward, the yellow line also moves upward on-screen.
    c. If not, the ``scale`` section of the stage’s config should get a sign change on the 3rd numeric value; restart acq4 and verify the Z orientation is correct.

2. Set z-axis scale
    a. Open the camera module, start video, and focus on a pipette tip.
    b. In the Camera module's Microscope dock, click "set surface". This should display a green line over the yellow line 
       (in the depth plot), and will also make it easier to measure changes in the focus Z position.
    b. Move the pipette tip a known distance in the Z (vertical) direction (e.g. +1 mm).
    c. Adjust focus to match, taking note of the distance traveled -- this difference should now be displayed next to the "set surface" button, 
       and will also be visible as the distance between green and yellow lines on the Microscope dock's depth plot.
    d. If there is any discrepancy between the pipette distance traveled and the focus distance traveled, this should be corrected in the 
       stage's scale configuration parameter; restart acq4 and verify the stage Z scale is correct. For example, if you moved the pipette 
       1 mm and acq4 reports that the focus changed by 10 mm, then this indicates that the configuration Z scale factor should be multiplied by 0.1.
    e. If you change the scale factor, remember to restart acq4 and test again.

3. Check x/y axis scale and orientation
    a. Focus on something visible (a pipette tip or a piece of dirt will work). Draw an ROI around the object.
    b. Move the stage in the x direction and confirm that the object and ROI move together.
    c. If the object and ROI move in opposite directions on screen, then multiply the stage X scale by -1, restart acq4, and try again.
    d. If the object and ROI move in the same direction on screen but different distances, then correct the scale factor. 
       For example, if the ROI moves twice as far as the object, then divide the X scale factor by 2. 
       Note: the accuracy of this step depends on the accuracy of your micromanipulator. 
       Use large movements to minimize potential errors, or use a micrometer slide if possible.
    e. Repeat in the y direction.


5. Fine Tuning the Stage Orientation
------------------------------------

We also find that it's helpful (but again not strictly required) to have the microscope stage's X and Y axes well-aligned with the camera. 
In this step we'll physically rotate the camera by a small angle until it is well aligned with the stage axes.

1. Find a small, visible feature in the camera view -- dust on the cover glass, a pipette tip, etc. 
   Move the stage until that feature is at the left edge of the view, vertically centered. Add an ROI around the feature.
2. Move the stage along its X axis until the feature is at the extreme rightmost edge of the view. 
   At this point, the ROI may be a small distance either above or below the feature -- their Y position on screen may differ, 
   but their X position should be the same. (If there is a difference in X position, go back to "Check x/y axis scale and orientation")
3. Physically rotate the camera a small angle around its Z axis to compensate for *half* of the observed drift.
4. Repeat previous steps until the ROI maintains the same Y location as the feature on either side of the view.


6. Set the global coordinate origin
-----------------------------------

In this step we configure position offsets such that the global coordinate origin lies at the center of the recording chamber, on the glass. This is not strictly required, but often makes our job easier when we need to make sense of those coordinate values.

1. Under the high-power objective, center the camera view over the center of the recording chamber and focus on the top surface of the glass coverslip (for *in vivo* rigs with no coversliip, pick any suitable focal plane to be the Z origin). If this is a water immersion objective, it is important to be dipped in water (ideally saline) at this point.
2. In the manager window, under the Microscope dock, make sure the x,y,z values for the high power objective are all set to 0.
3. In the camera window, point your mouse cursor close to the center of the view and note the x,y coordinates displayed in the bottom right corner of the camera module window. We would like these to read (0, 0) so that the origin of the global coordinate system is at the center of the recording chamber. The z position is displayed in the Depth dock on the right-hand side of the camera window, and we would like the 0 here to mean “on the glass”. Note: If you have a multi-well setup, you might choose to place the origin in the center of a specific well, or in the center of all wells, etc.
4. To move the origin, we will subtract the currently displayed x,y,z position values from the ``transform -> pos`` setting in the stage's device configuration. (if no setting exists here yet, the values are assumed to be 0)::

        Stage:
            driver: 'Sensapex'
            device: 20
            scale: 1.0e-6, 1.0e-6, -1.0e-6
            transform:
                pos: -3.45*mm, -12.27*mm, 8.552*mm

5. After correcting these values, restart acq4 and confirm that the global origin is roughly where you expect it to be.


7. Objective offset calibration
-------------------------------

In this step we tell acq4 how far apart the focal planes and objective centers are for your objectives. Note that some objective changers will attempt to automatically adjust the focal position when switching to compensate for parfocality; this calibration step does _not_ affect that behavior, and also is not affected by that behavior.

1. Focus on a pipette tip under the highest power objective. If you are using an immersion objective, then the pipette tip and objective should be dipped in saline.
   Note: we assume here that you have a standard 2-objective ephys rig, but these instructions should apply easily to more objectives.
2. In the manager window, under the Microscope dock, make sure the x,y,z values for the high power objective are all set to 0.
   These values will _stay_ 0 because by convention we calibrate the position offsets of each objective relative to the highest power objective.
3. Draw a small ROI around the tip of the pipette and click the "set surface" button. This gives us a reference point (green line in the depth plot) for measuring the offset between two objectives.
4. Switch to the low power objective, remove the saline from around the pipette (assuming this is an air objective), and focus on the pipette (but don't move the stage x/y axes)
   Note: the reason we do this calibration in saline for the high power objective and in air for the low power objective is that these are the most common conditions under which we will want to "transfer" pipette positions from one objective to another -- in some setups we do a coarse pipette calibration in air under the low-power objective, then do a refined calibration under high power dipped in saline.
5. In the manager window, under the Microscope dock, adjust the x,y values for the low-power objective until the pipette tip is matched to the ROI again. Likewise, adjust the z value until the yellow focus line is matched to the green "surface" line.
6. Copy the x,y,z values you have chosen in to the objective offset position in the microscope configuration. Do this for all objectives (including the high-power objective with values set to 0)::

    Microscope:
        driver: 'Microscope'
        parentDevice: 'Stage'
        objectives:
            0:  # first slot
                5x_0.25NA:
                    name: '5x 0.25na FLUAR'
                    scale: 1.0 / 5.0
                    offset: -43*um, 9*um
            1:  # second slot
                40x:
                    name: '40x 0.75na Achroplan'
                    scale: 1.0 / 40.0

7. Verify after restarting acq4 that the offsets are working correctly by repeating steps 1-4.


8. Initial manipulator calibration
----------------------------------

This procedure should be performed any time a manipulator is physically reconfigured (like if the orientation of the manipulator or headstage is adjusted), or whenever it appears that the manipulator calibrations are no longer correct. Before starting this procedure, it is a good idea to make sure your manipulator is securely seated in a good position such that:

* Pipette tips can reach a large enough area in the center of the recording chamber as well as any needed cleaning wells. To maximize available reach, it may help to orient the manipulator such that a cleaning well is at one corner of the manipulato's x/y range, and the center of the recording chamber is at the opposite x/y range
* The headstage should be unlikely to collide with the microscope
* Collisions with nearby manipulators are not possible


If your manipulator position meets these requirements, ..

1. Run calibrations recommended by the hardware manufacturer, if needed.
    - For Sensapex uMp: 
        - Move manipulator to a safe position and remove the pipette+holder.
          NOTE: The manipulator will move over its full range of motion, so it is important
          that no collisions are possible during this calibration.
        - Run the position calibration from the sensapex touchpad (tap the manipulator icon [4th from left along the screen bottom], then expand the "Setup" group, then "Calibrate positions").

2. Calibrate manipulator axis orientation. This step tells acq4 about the _direction_ that each manipulator axis points relative to the
   global coordinate system:
    a. Put a new pipette and the high-power objective in solution in the recording chamber. Watch via the camera for a few minutes to verify that the pipette is not drifting. 
       In case of drift, reduce any sources of temperature change -- especially block all air flow around the rig and microscope.
    b. In manager window, find the dock for the manipulator device to be calibrated (e.g. "Sensapex1") and click "calibrate". This opens a new window that manages the collection of calibration data points, which will be used to determine the manipulator axis directions.
    c. In the calibration window, remove all calibration points (if any) by selecting and clicking "remove".
    d. Move the stage to the center of the recording chamber and focus near the plane where you will normally be patching (if you're patching cultured cells, ~10µm above the glass is ok).
    e. In 40x, move the pipette to the left edge of the view, vertical center. The tip should be in sharp focus. 
    f. Click "add point" in the calibration window, then click on the pipette tip. This should be done carefully -- zoom in and pick a specific feature of the pipette tip that you will be able to click on repeatedly. It may help to take a screenshot here as a reference to ensure that you can repeatedly achieve the same focus and point position. 
    g. Move the pipette ~50µm to the right using _only_ the manipulator X axis (do not move the manipulator y/z axes). Re-focus on the tip (using the microscope focus) and add another point. Continue adding points until the pipette tip reaches the right side of the view. During this entire process, the manipulator Y and Z axes must remain unchanged. To calibrate the orientation of each axis, you need a minimum of three calibration points per axis. However, it is recommended to collect several points per axis for better accuracy.
    h. Now repeat the process for the Y and Z axes -- start from the top edge / horizontal center and work your way downward in Y (leaving X and Z unchanged), then start in the center of the screen and work your way upward in Z (cover at least ~100 µm in Z range).
    i. Click "save calibration".

3. Test axis orientation calibration:
    a. Under the multipatch module, enable the pipette by clicking on its numbered button (and disable all other pipettes)
    b. Click "calibrate", then click on the pipette tip in the camera module
    c. Focus on a random x/y/z location, click "set target" in the multipatch module, then click any location in the camera module. A yellow target symbol should appear where you clicked.
    d. Click "to target" and wait for the pipette tip to move. If the calibration was successful, the pipette tip should come very close to the target. Otherwise, it's likely a mistake was made during the calibration procedure.
    e. Check the Z error by using the camera module's depth chart (compare the yellow focus line to the blue pipette triangle; you may need to zoom in using the mouse wheel). 
    f. Within the field of view where calibration was performed, errors should be very small (on the order of 1 µm). As you move farther from the original calibration site (the center of the recording chamber), you should expect some x/y error to accumulate.


9. Set home and cleaning positions for each manipulator
-------------------------------------------------------

1. Set home position
    a. Move manipulator to the center of its y range, almost to the top of its z range, and almost to the end of its x range away from the recording chamber.
    b. In the manager window, under the dock for the manipulator device (e.g. "Sensapex1"), click "Set Home"

2. Set clean / rinse positions
    a. Move pipette tip into the cleaning well, at the desired depth for cleaning.
       Note: during automated pipette cleaning, the manipulator is programmed to move a certain distance above the cleaning position before entering the cleaning well. The default distance is 5 mm, but this can be set in the configuration for patch pipette states under "clean -> approachHeight". If the manipulator cannot move this distance above the selected cleaning position, then an error will occur. Now is a good time to make sure there is enough room to satisfy this constraint.
    b. In the manager window under the dock for the patch pipette device (e.g. "PatchPipette1"), click "Set Clean Pos".
    c. Repeat for rinse position if needed.


10. Configure pipette approach angle
------------------------------------