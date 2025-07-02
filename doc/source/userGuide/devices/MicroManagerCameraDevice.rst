MicroManager Camera
==================

.. currentmodule:: acq4.devices.MicroManagerCamera

.. autoclass:: MicroManagerCamera
    :members:
    :undoc-members:
    :show-inheritance:

The MicroManagerCamera device provides camera control through the MicroManager interface, allowing ACQ4 to work with a wide variety of cameras supported by MicroManager's plugin system.

**Note**: This device has been marked as potentially stale. It may require updates to work with current MicroManager versions.

Configuration
-------------

The MicroManagerCamera requires specific MicroManager configuration parameters:

* **mmAdapterName**: The MicroManager adapter name (e.g., 'HamamatsuHam')
* **mmDeviceName**: The MicroManager device name (e.g., 'HamamatsuHam_DCAM')
* **path**: Optional path to MicroManager installation directory

Example configuration::

    Camera:
        driver: 'MicroManagerCamera'
        mmAdapterName: 'HamamatsuHam'
        mmDeviceName: 'HamamatsuHam_DCAM'
        path: '/Applications/Micro-Manager'

Dependencies
------------

* pymmcore (Python wrapper for MicroManager Core)
* MicroManager installation with matching API versions
* Appropriate MicroManager device adapters for your camera hardware