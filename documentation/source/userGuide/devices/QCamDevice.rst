QImaging Cameras
================




Configuration Options
---------------------

QImaging devices support all options provided by the base Camera class.

Simple example for QImaging cameras. No trigger/exposure lines are defined
in this example. 

::

    Camera:
        driver: 'QCam'
        config:
            parentDevice: 'Microscope'          ## tells us that the camera is rigidly connected to the scope, and
                                                ##   thus will inherit its transformations.
            transform:                          ## transform defines the relationship between the camera's
                                                ##   sensor coordinate system (top-left is usually 0,0 and
                                                ##   pixels are 1 unit wide) and the coordinate system of its
                                                ##   parentDevice. This is where we would rotate/flip the camera if needed.
                position: (0, 0)
                scale: (1, 1)
                angle: 0

Manager Interface
-----------------


Protocol Runner Interface
-------------------------
