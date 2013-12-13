Microscope Devices
==================

The primary purpose of a Microscope device in ACQ4 is to keep track of a set of objective lenses and either allow the user to specify which lens is currently in use, or automatically determine which is in use. Each objective lens introduces a particular scaling and offset to the optomechanical transform hierarchy. This information is used by other devices and modules: 
    
* Cameras generate frame with metadata that specifies the location and scaling of the frame relative to the global coordinate system, as well as which objective was used while acquiring the frame.
* Scanners and Lasers use information about the current optical path to select the correct calibration data.
* The Camera module uses position and scaling data to track the location of a video feed as it moves around the sample.

Although the name 'Microscope' is specific, the features provided are quite general and may be used in other contexts to indicate a change in the optomechanical pathway.


Configuration Options
---------------------

Example microscope device which is rigidly-connected to a motorized 
stage (defined above). It also uses the 'Switch' device to determine the
objective lens currently in use.

::
    
    Microscope:
        driver: 'Microscope'
        config:
            parentDevice: 'SutterStage'
            objectiveSwitch: 'Switch', 'objective'  ## monitor the 'objective' channel from the 'Switch' device
            objectives:  
                ## All scales in m/px
                0:
                    63x0.9:                            ## unique identifier
                        name: '63x 0.9na Achroplan'    ## descriptive name
                        scale: 0.205*um/px
                        offset: 70*um, 65*um
                    63x0.95:
                        name: '63x 0.95na Achroplan'
                        scale: 0.205*um/px
                        offset: 70*um, 65*um
                    40x:
                        name: '40x 0.75na Achroplan'
                        scale: 0.324*um/px
                        offset: -43*um, 9*um
                1:
                    5x0.25:
                        name: '5x 0.25na FLUAR'
                        scale: 2.581*um/px


Manager Interface
-----------------


Protocol Runner Interface
-------------------------
