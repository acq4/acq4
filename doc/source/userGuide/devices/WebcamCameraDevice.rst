WebcamCamera
============

.. currentmodule:: acq4.devices.WebcamCamera.webcam_camera

.. autoclass:: WebcamCamera
    :members:
    :show-inheritance:

Minimal camera driver using OpenCV ``VideoCapture``.

Configuration
-------------

Exactly one of **cameraIndex** or **cameraName** is required.

* **cameraIndex** (int): index for ``cv2.VideoCapture``
* **cameraName** (str): case-insensitive substring of the device description
* **backend** (int or str, optional): OpenCV backend, e.g. ``CAP_DSHOW``
* **resolution** ([w, h], optional): capture size, used as sensor size (default [640, 480])
* **colorMode** (``'gray'`` or ``'bgr'``, optional): output format (default ``'gray'``)
* **bufferSize** (int, optional): requested driver buffer size
* **pixelFormat** (str, optional): initial FOURCC, e.g. ``MJPG``
* **pixelFormats** (list of str, optional): pixel formats offered as choices

Example configuration::

    Camera:
        driver: 'WebcamCamera'
        cameraName: 'USB Camera'
        resolution: [1280, 720]
        colorMode: 'gray'

Features
--------

* Continuous frame streaming; trigger mode, ROI and binning fixed
* Optional OpenCV controls (brightness, contrast, gain, focus, exposure, frame rate, etc.) exposed only when the camera supports them
* If neither index nor name is given, the error lists available ``index: description`` pairs

Dependencies
------------

* ``opencv-python`` (``cv2``) and ``numpy``
