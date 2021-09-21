.. _userDevicesQImagingCameras:

QImaging Cameras
================

The ``QCam`` device class in ACQ4 provides support for all cameras that make use of the QImaging QCam library. With only a few exceptions, these devices follow all of the conventions described for :ref:`generic Camera devices <userDevicesCamera>`.



Configuration Options
---------------------


QImaging cameras support all of the configuration options as :ref:`generic Camera devices <userDevicesCameraConfiguration>`. Extra options are:
    
* **serial**: An integer identifying the camera to be used (for systems that have more than one QCam-based camera). If an incorrect serial number is given, then an error will be displayed listing the serial numbers of cameras found in the system.
* **defaults**: In addition to the standard camera parameters, several parameters defined by the QCam library may be specified here. These parameters are listed in the camera's :ref:`Manager interface <userDevicesCameraManager>`.

