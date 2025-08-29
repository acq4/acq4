Pipette
=======

.. currentmodule:: acq4.devices.Pipette

.. autoclass:: Pipette
    :members:
    :undoc-members:
    :show-inheritance:

The Pipette device represents a pipette or electrode attached to a motorized manipulator, providing camera module interface capabilities for visual control and automated positioning.

Features
--------

* **Visual Control**: Camera module interface for visually directing pipette tip
* **Automatic Alignment**: Align pipette tip for diagonal approach to cells
* **Tip Calibration**: Automatic calibration of pipette tip position via tracking
* **Path Planning**: Intelligent movement planning to avoid obstacles
* **Tip Detection**: Computer vision-based pipette tip detection and tracking

Configuration
-------------

The Pipette device must be configured with a Stage as its parent device.

Required configuration options:

* **pitch** (float or 'auto'): The angle of the pipette in degrees relative to horizontal plane
  Positive values point downward
* **parentDevice** (str): Name of the Stage device controlling the manipulator

Optional configuration:

* **searchHeight** (float): Height above focal plane to search for pipette tip (default: 200e-6 m)
* **searchRegion** (tuple): (width, height) of search region in meters (default: (500e-6, 500e-6))
* **approachAngle** (float): Angle for diagonal approach in degrees (default: 45)

Example configuration::

    Pipette1:
        driver: 'Pipette'
        parentDevice: 'Manipulator1'
        pitch: 15.0  # degrees downward from horizontal
        searchHeight: 200e-6
        searchRegion: [500e-6, 500e-6]
        approachAngle: 45.0

Coordinate System
-----------------

The local coordinate system is configured such that:

* **X axis**: Points in the direction of the pipette tip
* **Z axis**: Points upward (same as global +Z)  
* **Y axis**: Perpendicular to both X and Z

Camera Module Integration
-------------------------

The Pipette device provides a camera module interface that allows:

* Visual targeting of cells and structures
* Real-time tip position feedback
* Interactive movement control
* Automated approach sequences

Path Planning
-------------

The device includes sophisticated path planning capabilities:

* Obstacle avoidance during movements
* Optimized trajectory calculation
* Safe retraction paths
* Collision detection with other devices

Tip Detection and Tracking
---------------------------

Uses computer vision algorithms to:

* Automatically detect pipette tip location
* Track tip position during movements
* Calibrate tip position relative to manipulator coordinates
* Provide visual feedback on tip status

Dependencies
------------

* Stage device (parent manipulator)
* Camera device (for visual feedback)
* Optional: Recording chamber for coordinate reference