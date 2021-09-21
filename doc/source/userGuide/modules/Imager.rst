.. _userModulesImager:
    
Imager Module
=============

The Imager module provides laser scanning imaging functionality for multiphoton and confocal microscopes. This module combines control of scanning mirrors, laser power, and signal detection devices (such as photomultiplier tubes or photodiodes). Like other modules, the Imager module operates in the global coordinate system and displays its output in the display area of a :ref:`Camera module <userModulesCamera>`. It also displays a user-positionable rectangle which defines the extents of the laser scanning area. The Imager module supports overscanning to remove retrace artifacts as well as bidirectional scanning with automated field shifting to reduce comb artifacts. While the interface includes detailed control of scanning parameters, tiling, and the collection of image stacks, common functionality such as fast (video) scanning or the collection of standardized high-resolution images may also be accessed from preset configurations to simplify user interaction during experiments. 

    .. figure:: images/imager.svg

Configuration
-------------

The imager requires five components to be available within the system: a :ref:`Camera module <userModulesCamera>`, a :ref:`Scanner device <userDevicesScanner>`, a :ref:`Laser device <userDevicesLaser>`, a detector device (:ref:`generic DAQ channel device <userDevicesDAQGeneric>`), and an attenuator device (such as a Pockels cell; also a :ref:`generic DAQ channel device <userDevicesDAQGeneric>`). The names of each component must be specified in the configuration::
    
    modules:
        Imager:
            module: 'Imager'
            config:
                # Names of modules and devices needed by the Imager
                cameraModule: 'Camera'
                scanner: 'Scanner'
                laser: 'Laser-UV'
                detector: 'PMT', 'Input'  # device and channel names for DAQGeneric channel
                attenuator: 'PockelsCell', 'Switch'
        
Basic usage
-----------

Before the Imager module can be loaded, a :ref:`Camera module <userModulesCamera>` must be loaded to display the region-of-interest control that defines the area within the :ref:`global coordinate system <userCoordinateSystems>` to be imaged. Once the Imager is loaded, the following settings must be adjusted to achieve the desired imaging conditions:
    
* Adjust the ROI to the desired imaging area
* Choose an appropriate image resolution and sample rate
* Choose an appropriate Pockels cell voltage
* Check **Store** if acquired images should be saved to the currently selected :ref:`storage directory <userModulesDataManagerStorageDirectory>`

Click **Snap** to acquire a single image, and **Video** to acquire continuously.

Optionally, several other parameters provide additional control over the imaging procedure:

* **Downsample** causes detector data to be downsampled to reduce noise before it is converted into an image. It is recommended to sample at the highest possible rate, then downsample to achieve the desired image quality.
* **Average** causes multiple frames to be acquired and averaged together to further reduce noise.
* **Bidirectional** causes the scan mirror to scan alternating rows in opposite directions. This speeds up scanning but also creates comb artifats.
* **Decomb** shifts the detector data in time to correct for comb artifats from bidirectional scanning. Use **Auto** to automatically determine the optimal shift value.



