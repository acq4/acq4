Camera Devices
==============

In ACQ4, a Camera can be any device used for collecting image data. Currently this includes support for Photometrics and Q-Imaging cameras, but other types of imaging devices (such as laser scanning imaging hardware) may be included in the future. A simulated camera device is also included for testing.

Cameras support the following features:

* May be triggered by an arbitrary waveform generated on a DAQ digital output
* May be used to trigger the start of a DAQ acquisition
* Precisely timed frame acquisition by recording TTL exposure signal on a DAQ digital input
* Graphical interface for control via the Camera module
* Graphical interface for configuration via the Manager module
* Graphical interface for control via the Task Runner module

Note that the exact features available may differ depending on the capabilities of the camera hardware.


Camera device subclasses:
    
.. toctree::
    :maxdepth: 1
    
    QCamDevice
    PVCamDevice
    MockCameraDevice


Hardware Configuration
----------------------

Physical layout, triggering, exposure signals...

Note: If the exposure signal from the camera is connected to both DI and PFI ports, the DI recording may fail if the PFI is not being used.
This is because the PFI ports have very low impedance when unused.


Configuration Options
---------------------

The following is an example camera configuration:

::
    
    Camera:
        driver: '<driver name>'
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
