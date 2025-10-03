VimbaX Camera
=============

.. currentmodule:: acq4.devices.VimbaXCamera

.. autoclass:: VimbaXCamera
    :members:
    :undoc-members:
    :show-inheritance:

The VimbaXCamera device provides support for Allied Vision cameras using the VmbPy interface.

Configuration
-------------

The VimbaXCamera requires the camera ID as reported by the Vimba driver:

* **id**: Camera ID string as reported by Vimba driver

Example configuration::

    Camera:
        driver: 'VimbaXCamera'
        id: 'DEV_1AB22C003F52'

To find available camera IDs, use::

    from acq4.devices.VimbaXCamera import VimbaXCamera
    VimbaXCamera.listCameras()

Dependencies
------------

* VmbPy - Allied Vision VimbaX Python interface
* Allied Vision Vimba SDK
* Compatible Allied Vision camera hardware

Installation
------------

See https://github.com/alliedvision/VmbPy for VmbPy installation instructions.

**Note**: This implementation is primarily designed for test rig usage and may require additional development for production environments.