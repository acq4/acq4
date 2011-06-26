Scanner Devices
==========================

The scanner device is used to control a set of galvometric mirrors to precisely direct a scanning laser beam. 
The device allows the user to specify the desired laser spot location by graphically selecting the location from within a camera module. The transformation between camera coordinates and X,Y voltages is determined by an automatic calibration procedure.

Configuration
---------------------------



Manager Interface
---------------------------

Calibration
+++++++++++

The primary function of the Scanner device is to allow the user to select the a laser spot position relative to camera coordinates. The scanner device, therefore, must know the corresponding transformation. This is achieved through a simple, automatic calibration routine: 

#. The pre-stored camera configuration is loaded
#. The camera begins recording at a high frame rate (30-100fps)
#. The mirror voltages are systematically varied to raster-scan the laser spot
#. Spots are automatically detected in each camera frame and matched with their corresponding voltages
#. The relationship between camera coordinates and mirror voltages are determined by linear regression
#. The camera is returned to its previous state

If there are multiple cameras, lasers, or objective lenses, one calibration must be made for each combination.
This process is somewhat complex and requires that the user ensure the hardware is configured properly prior to calibration:
    
* The camera must indicate its frame exposure times via a TTL signal connected to the DAQ board.
* The camera must be acquiring at a high frame rate, usually 30fps or more. If the camera is acquiring too slowly, then too few spots will be captured to make an accurate linear regression.
* The exposure time of each frame must be short, usually less than 5ms. Otherwise, the spot images captured will be 'smeared' and their location will not be detected accurately.
* The laser spot must be brightly visible to the camera
* Objective lenses must be clean
* Laser spot should be projected on a flat, bright surface (we recommend using small pieces of fluorescent tape or plastic)

To achieve these requirements, it is common to configure the camera to use binning and to operate over a restricted region of interest. When the camera is configured with all appropriate settings, click the "Store Camera Config" button in the manager interface. All calibrations from then on will load these camera settings before starting and restore the original settings afterward.

When all hardware is configured correctly, do the following to start a calibration:

#. Select the laser and camera to be calibrated in the manager interface
#. Be sure that the correct microscope objective is selected in the scope interface
#. Click 'Calibrate'.
    
The results of the calibration should appear in the window to the right. There should be clear laser spots with circles 
drawn around them. In the table, the Spot column lists a relative measure of the amount of light in the spot, and diameter 
of the spot where intensity drops off to 1/e. This diameter also determines the size of the targets used to setup and run 
protocols.

Calibrations are stored for each combination of camera/objective/laser. When you calibrate, any calibrations previously
stored for the combination you're calibrating are overwritten. 

Calibration Parameters
''''''''''''''''''''''

* Laser and Camera selection boxes: You can tell the scanner which camera and laser to use (if you have more than one) for the calibration by selecting them here. 
* Scan Duration: Sets the total amount of time for the calibration. For cameras that are slow or not sensitive enough, increase the scan duration to allow more time for frame collection and integration.
* X & Y Min and Max: Set the range of voltages that are scanned over during the calibration.
* Store Camera Config: Clicking this button stores the current configuration of the camera to use for future calibrations. If you are having trouble calibrating, it is a good idea to manually adjust all the camera settings and then re-click "Store Camera Config."

Virtual Shutter
+++++++++++++++

The scanner can be used to simulate a shutter by directing the laser to a beam block outside the microscope illumination path. 
If you use this make sure that when in the "off" position the laser is directed onto an absorbant surface (please use common sense). Use the X and Y boxes to designate the voltage to use for the "off" position. The shutter can be 'opened' and 'closed' using the button that reads either 'Open Shutter' or 'Close Shutter'.



Protocol Runner Interface
---------------------------

To include the scanner in a protocol, first mark the Scanner check box in the list of devices. This should bring up the Scanner's
protocol interface.

Controls
++++++++

* Camera and Laser: Select the camera and laser that you want to use in the protocol. Be sure that you have calibrated whatever combination of camera and laser that you choose.
* Simulate Shutter Check: This determines whether you are using the Virtual Shutter function or not. If checked, the scanner will send the spot to the "off" position whenever the shutter is closed (set this in the Protocol runner interface for the shutter.) If not checked, the scanner ignores the virtual shutter option and you need to have a real shutter somewhere in the path.
* Display Controls Check: Not sure if this does anything or not......LUKE?????????
* Minimum Time and Minimum Distance: These two numbers determine how frequently sites can be stimulated in space and time. If Minimum Time is 5 seconds and Minimum Distance is 500 microns, this means that when Spot A is stimulated, spots that are less then 500 microns away won't be stimulated within 5 seconds. However, spots further than 500 microns can be stimulated with no delay.
* Grid Spacing: This determines how closely the target spots in grids are packed. Lowering the grid spacing packs the spots closer together. Note: This has absolutely NO effect on the actual spot size. 
    
Adding Targets
++++++++++++++

There is currently only one type of target implemented: A spot. You can add target spots individually, or you can add them as grids.
Eventually, we will implement more complex scanning patterns that will include scanning along lines (including spirals), and 
stimulating multiple locations within the same trace. But not yet.....

Whenever there is a scanner protocol interface open, a pink target spot will appear in the selected camera. This pink spot is a test
spot and will be stimulated whenever Test Single or Record Single is clicked. 

To add targets that will be stimulated in sequence click Add Grid or Add Point. Add Grid will add a grid of points to the camera window. You can adjust the position of this grid in the camera window. To translate the grid click in the middle of the grid and drag. To rotate the grid, click and drag on of the circular handles on the corner of the grid. And to scale the grid, click and drag one of the square handles. You can add as many grids and points to a protocol sequence as you like. If you do not want to use a grid or point during a protocol sequence, you can either uncheck it in the Items list, or you can select it in the Items list and delete it by clicking Delete. Active target points will appear in green by default. If they are selected in the item list they will appear in light pink. Use this to identify which spots to delete/uncheck.

If you want a grid (perhaps over the area around a cell) but have an area that you don't want to stimulate (for example where an electrode is over the slice) you can add an Occlusion. You can adjust the location of the corners of the occlusion by dragging any of the corner handles, and you can translate the occlusion by clicking and dragging it by the middle. Any points whose centers fall within the occlusion will be removed from the target list (and appear in dark grey in the camera window). 

Total Time displays the time that the computer calculates it will take to run the scan. I have found this to not be particularly accurate.

If you close the scanner protocol interface (for example, to open a different protocol) all the Target items and occlusions that you have added will be saved, and will reappear when you open another Scanner interface. This is very helpful for switching between scanning protocols where you want to stimulate the same spots. 