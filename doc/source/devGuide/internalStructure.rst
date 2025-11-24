Internal Structure
==================

Overview
--------

ACQ4's architecture is built around several core components that work together to provide a flexible
platform for data acquisition and experimental control.

Manager (Core Controller)
--------------------------

The Manager class (``acq4/Manager.py``) serves as the central controller for the application:

* Loads and configures devices
* Manages modules (UI components)
* Coordinates device interactions
* Provides configuration management
* Controls application lifecycle

Devices
-------

Devices (``acq4/devices/``) represent hardware abstractions:

* Base class: ``Device`` in ``devices/Device.py``
* Each device implements hardware-specific functionality
* Devices are configured through the Manager
* Task interfaces allow controlled experiment execution
* Resource locking prevents conflicts between modules

Modules
-------

Modules (``acq4/modules/``) provide user interface components:

* Base class: ``Module`` in ``modules/Module.py``
* Each module offers specific functionality (imaging, patching, etc.)
* Can interact with devices through the Manager
* Can be loaded/unloaded dynamically

Interface System
----------------

The interface system (``acq4/Interfaces.py``) enables component discovery:

* Components advertise capabilities through interfaces
* Interfaces provide standardized APIs
* Components can discover other components by interface

Data Management
---------------

DataManager handles data organization:

* Directory structure for organizing data
* File I/O for various data formats
* MetaArray format for multi-dimensional data
* Metadata storage and retrieval
