Photometrics Cameras
====================




Configuration Options
---------------------

Photometrics cameras support all features provided by the basic Camera device class. 

::
    
    Camera:
        driver: 'PVCam'
        config:
            serial: 'PM1394Cam'
            parentDevice: 'Microscope'          ## tells us that the camera is rigidly connected to the scope, and
                                                ##   thus will inherit its transformations.
            transform:                          ## transform defines the relationship between the camera's
                                                ##   sensor coordinate system (top-left is usually 0,0 and
                                                ##   pixels are 1 unit wide) and the coordinate system of its
                                                ##   parentDevice. This is where we would rotate/flip the camera if needed.
                position: (0, 0)
                scale: (1, -1)
                angle: 0
            exposeChannel:                      ## Channel for recording expose signal
                device: 'DAQ'
                channel: '/Dev1/port0/line8'
                type: 'di'
            triggerOutChannel:                  ## Channel the DAQ should trigger off of to sync with camera
                device: 'DAQ'
                channel: '/Dev1/PFI5'
            triggerInChannel:                   ## Channel the DAQ should raise to trigger the camera
                device: 'DAQ'
                channel: '/Dev1/port0/line28'
                type: 'do'
                invert: True                    ## invert because Quantix57 triggers on TTL LOW
            params:                             ## default parameters to apply to camera at startup
                #TEMP_SETPOINT:  -2000
                exposure: 10e-3    
    
    
Manager Interface
-----------------


Protocol Runner Interface
-------------------------
