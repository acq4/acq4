Simulated Cameras
=================

MockCamera is a simulated camera device, providing:
    
* Position-dependent procedural imagery (a Mandelbrot fractal). When combied with a mock microscope device, this allows to explore different parts of the imagery. 
* Simulation of CCD noise including efects of exposure time and binning
* Simulated calcium indicator sources.


Configuration Options
---------------------

::
    
    Camera:
        driver: 'MockCamera'
        config:
            parentDevice: 'Microscope'
            transform:                          ## transform defines the relationship between the camera's
                                                ## sensor coordinate system (top-left is usually 0,0 and
                                                ## pixels are 1 unit wide) and the coordinate system of its
                                                ## scopeDevice
                position: (0, 0)
                scale: (1, 1)
                angle: 0

            exposeChannel:                                 ## Channel for recording expose signal
                device: 'DAQ'
                channel: '/Dev1/port0/line0'
                type: 'di'
            #triggerOutChannel: 'DAQ', '/Dev1/PFI5'        ## Channel the DAQ should trigger off of to sync with camera
            triggerInChannel:                              ## Channel the DAQ should raise to trigger the camera
                device: 'DAQ'
                channel: '/Dev1/port0/line1'
                type: 'do'


Manager Interface
-----------------


Protocol Runner Interface
-------------------------
