Scanner Devices
==========================

The scanner device is used to control a set of scan mirrors. It translates a position that is designated by the user in 
the camera window into a pair of voltages applied to the mirrors. 

Configuration
---------------------------



Manager Interface
---------------------------
Scanner calibration happens in the main Acq4 Manager window. In order to calibrate the scan mirrors you need to have a 
camera module open and running. 

To calibrate:

    #. In camera window, set Binning to 2.
    #. Open the shutter(s).
    #. Make sure spot is visible, in focus, and not saturated. (You may need to increase/decrease the exposure time in the 
    camera window.)
    #. Close the shutter(s).
    #. Make sure that the appropriate objective is selected in the Manager window.
    #. Click "Calibrate"
    
The results of the calibration should appear in the window to the right. There should be clear laser spots with circles 
drawn around them. In the table, the Spot column lists a relative measure of the amount of light in the spot, and diameter 
of the spot where intensity drops off to 1/e. This diameter also determines the size of the targets used to setup and run 
protocols.

Calibrations are stored for each combination of camera/objective/laser. When you calibrate, any calibrations previously
stored for the combination you're calibrating are overwritten. 

Calibration Parameters
++++++++++++++++++++++

* Laser and Camera selection boxes: You can tell the scanner which camera and laser to use (if you
    have more than one) for the calibration by selecting them here. 
* Scan Duration: Sets the total amount of time for the calibration. Make the scan duration longer if the calibration is not
    working because too few spots are being detected. 
* X & Y Min and Max: Set the range of voltages that are scanned over during the calibration. 
* Store Camera Config: Clicking this button stores the current configuration of the camera to use for future calibrations.
    If you are having trouble calibrating, it is a good idea to manually adjust all the camera settings and then re-click 
    "Store Camera Config."

Virtual Shutter
+++++++++++++++

The scanner can be used to simulate a shutter by directing the laser out to the side so that it doesn't enter the objective. 
If you use this make sure that when in the "off" position the laser is directed onto an absorbant surface. Use the X and Y boxes designate the voltage to use for the "off" position. If the virtual shutter is closed an "Open Shutter" button should be available. Click "Open Shutter" to enable scanning. When scanning is enabled this button should switch to read "Close Shutter". Click "Close Shutter" to send the scanner to the "off" position and disable scanning. 



Protocol Runner Interface
---------------------------

To include the scanner in a protocol, first mark the Scanner check box in the list of devices. This should bring up the Scanner's protocol interface.

Controls
++++++++

* Camera and Laser: Select the camera and laser that you want to use in the protocol. Be sure that you have calibrated whatever combination of camera and laser that you choose.
* Simulate Shutter Check: This determines whether you are using the Virtual Shutter function or not. If checked, the scanner will send the spot to the "off" position whenever the shutter is closed (set this in the Protocol runner interface for the shutter.)
    If not checked, the scanner ignores the virtual shutter option and you need to have a real shutter somewhere in the path.
* Display Controls Check: Not sure if this does anything or not......LUKE?????????
* Minimum Time and Minimum Distance: These two numbers determine how frequently sites can be stimulated in space and time. If Minimum Time is 5 seconds and Minimum Distance is 500 microns, this means that when Spot A is stimulated, spots that are less then 500 microns away won't be stimulated within 5 seconds. However, spots further than 500 microns can be stimulated with no delay.
* Grid Spacing: This determines how closely the target spots in grids are packed. Lowering the grid spacing packs the spots closer together. Note: This has absolutely NO effect on the actual spot size. 
    
Adding Targets
++++++++++++++

There is currently only one type of target implemented: A spot. You can add target spots individually, or you can add them as grids. Eventually, we will implement more complex scanning patterns that will include scanning along lines (including spirals), and stimulating multiple locations within the same trace. But not yet.....

Whenever there is a scanner protocol interface open, a pink target spot will appear in the selected camera. This pink spot is a test spot and will be stimulated whenever Test Single or Record Single is clicked. 

To add targets that will be stimulated in sequence click Add Grid or Add Point. Add Grid will add a grid of points to the camera window. You can adjust the position of this grid in the camera window. To translate the grid click in the middle of the grid and drag. To rotate the grid, click and drag on of the circular handles on the corner of the grid. And to scale the grid, click and drag one of the square handles. You can add as many grids and points to a protocol sequence as you like. If you do not want to use a grid or point during a protocol sequence, you can either uncheck it in the Items list, or you can select it in the Items list and delete it by clicking Delete.

Active target points will appear in green by default. If they are selected in the item list they will appear in light pink. Use this to identify which spots to delete/uncheck.

If you want a grid (perhaps over the area around a cell) but have an area that you don't want to stimulate (for example where an electrode is over the slice) you can add an Occlusion. You can adjust the location of the corners of the occlusion by dragging any of the corner handles, and you can translate the occlusion by clicking and dragging it by the middle. Any points whose centers fall within the occlusion will be removed from the target list (and appear in dark grey in the camera window). 

Total Time displays the time that the computer calculates it will take to run the scan. I have found this to not be particularly accurate.

If you close the scanner protocol interface (for example, to open a different protocol) all the Target items and occlusions that you have added will be saved, and will reappear when you open another Scanner interface. This is very helpful for switching between scanning protocols where you want to stimulate the same spots. 