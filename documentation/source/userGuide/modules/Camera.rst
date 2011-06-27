The Camera Module
=================

The Camera Module provides a window for using the Camera. It contains:

    * Basic camera controls.
    * Image and video acquisition controls.
    * A canvas that displays the camera image as well as any images added to it.
    * ROIs
    * Online image processing.
    
Camera Dock
-----------

The camera dock contains basic camera controls and controls for aquiring and saving images and videos.

Acquisition controls:

    * Acquire Button: Starts/stops camera acquisition and image display. No data is saved.
    * Snap Button: Saves the current image as a .tif file.
    * Record Button: Records a video. Recording starts when "Record" is pressed, and lasts until "Record" is pressed again. The number of frames in the video is displayed in the lower left corner of the window.
    
Camera controls:
    
    * Binning: Sets the binning on the camera. All binning is square, even if the camera supports non-square binning. 
    * Exposure: Sets the exposure time on the camera.
    * Full Frame and camera regions: The camera region is controlled through the canvas. On the corners of the image there are scale handles that can be dragged adjust the region. This limits the area of the camera ccd that is acquiring data. Thus, if you are trying to optimize frame speed, reducing the camera region is very helpful. The *Full Frame* button returns the camera region to its full extent. 
    * Scale 1:1: Optimizes display speed by scaling the camera image so that one camera pixel maps to one display pixel.
    

Display Gain Dock
-----------------

This dock contains controls for adjusting the display of the image. These controls do not affect data that is stored to disk; all data is stored in its raw format as it is collected.

    * Autogain : Autogain is on by default. When autogain is on, the display automatically adjusts the black and white levels to provide the most contrast. 
    * Black/White Slider: Use this to adjust the black and white levels in the image. Can be used with autogain.
    * Slow: Causes the auto gain to respond with a time delay. This is useful for cameras with periodic spike noise which would otherwise cause the display to flash.
    * Center Weight: Causes auto gain to meter off of the center 1/3 of the frame. A value of 1.0 meters entirely off of the center, while a value of 0.0 meters from the entire frame


Plots Dock (ROIs)
-----------------

ROIs (Regions of Interest) can be used in the camera window to plot intensity in any particular region (or regions) of the image. They can also be used as markers without plotting (for example, to mark the location of a cell while patching).

    * Add: To add an ROI to the image click the *Add* button. This will cause a colored rectangle to appear in the center of the camera image. This rectangle defines the ROI. Click and drag inside the rectangle to move it, and resize with the scale handle in the corner. You can add addtional ROIs that will appear in different colors. 
    * Clear: The *Clear* button removes all ROIs.
    * Enable ROIs Check box: When checked, brightness levels from all the ROIs present will be plotted in colors corresponding to the ROIs. If you just want to use ROIs as markers, disable plotting by unchecking the Enable ROIs check box.
    * Time: Determines the amount of time that is plotted. 


Persistent Frames Dock
----------------------

Persistent frames are images that are added to the canvas background. This feature is especially helpful if you have a device that tracks the position of your microscope as you move it. It can also be helpful when using multiple objectives. By adding persistent frames you can create a mosaic image of the preparation.

    * Add : Adds the current camera image to the canvas. 
    * Clear: Removes all images from the canvas.

Background Subtraction Dock
---------------------------

Background Subtraction can be used to enhance contrast and make it easier to see cells under high magnification. It works particularly well with off-center illumination.

To use background subtraction:

    #. Focus just above the preparation, where the whole image is blurry.
    #. Press the *Divide Background* button. This averages a stream of frames and divides them out of the image. 
    #. Wait until the image turns to grey noise. 
    #. Press the *Lock Background* button. This stops incorporating new frames into the average background frame. Now a fixed average background frame is divided out of all the new incoming frames.
    #. Focus back down to the slice.
    
Depending on your lighting conditions you can move the microscope around a bit without resetting the background subtraction. But if you move a lot, or if the image looks funny/not as good, you should reset the background image. To reset, click both the *Lock Background* and *Divide Background* buttons to turn them off. Then repeat the steps above.

Parameters:

    * Time Const: the length of time to integrate while collecting background frames
    * Blur Bg: Causes the background frame to be blurred before dividing it from the current frame. This can aid contrast enhancement under some circumstances, but may slow the video display considerably.
    
    