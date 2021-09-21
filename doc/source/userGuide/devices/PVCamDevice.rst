.. _userDevicesPhotometricsCameras:

Photometrics Cameras
====================

The ``PVCam`` device class in ACQ4 provides support for all cameras that make use of the Photometrics PVCam library. With only a few exceptions, these devices follow all of the conventions described for :ref:`generic Camera devices <userDevicesCamera>`.


Configuration Options
---------------------

Photometrics cameras support all of the configuration options as :ref:`generic Camera devices <userDevicesCameraConfiguration>`. Extra options are:
    
* **serial**: A string identifying the camera to be used (for systems that have more than one PVCam-based camera). This name is defined using the PvCam config utility available from Photometrics.
* **defaults**: In addition to the standard camera parameters, several parameters defined by the PVCam library may be specified here. It is strongly recommended to read the documentation for your camera to understand the effects of these parameters, because some parameters have names that do *not* correspond to their function. For example, configuring QuantEM cameras to operate in "overlapping" frame exposure mode requires setting ``CLEAR_MODE: 'Pre-sequence'``.

A complete PVCam configuration example follows:

::
    
    Camera:
        driver: 'PVCam'
        serial: 'PM1394Cam'
        parentDevice: 'Microscope'          ## tells us that the camera is rigidly connected to the scope, and
                                            ##   thus will inherit its transformations.
        transform:                          ## transform defines the relationship between the camera's
                                            ##   sensor coordinate system (top-left is usually 0,0 and
                                            ##   pixels are 1 unit wide) and the coordinate system of its
                                            ##   parentDevice. This is where we would rotate/flip the camera if needed.
            position: (0, 0)
            scale: (1, -1)                  ## Invert y-axis 
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
        defaults:                           ## default parameters to apply to camera at startup
            #TEMP_SETPOINT:  -2000
            exposure: 10e-3    
    



..  Manager Interface
..  -----------------

..  The Manager interface for PVCam cameras 

..      .. figure:: images/Camera_ManagerInterface.png


..  Task Runner Interface
..  ---------------------

..  The task interface for PVCam devices is the same as for :ref:`generic camera devices<userDevicesCameraTaskInterface>`. 
