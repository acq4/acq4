Principles of Operation
=======================

Overview
--------

ACQ4 is both a platform for application development and a suite of modules built on that platform. At the core of ACQ4 is a central Manager that controls access to devices, executes tasks that synchronize the actions of multiple devices, manages the storage and retrieval of data, and loads user interface modules (Figure 1). Each user interface module provides a specific functions such as camera access, synchronized recording and device control, data browsing, and various analysis tasks. These modules make use of the services provided by the Manager, allowing them to communicate with one another.

In most cases, user interface modules control the acquisition hardware indirectly by submitting task requests to the Manager. These task requests specify which devices will participate in the task and describe the intended actions for each device. The manager then handles all aspects of device configuration and synchronization, while ensuring that tasks submitted by different modules do not attempt to access the same hardware simultaneously. This is one of the most important services provided by the Manager because it simplifies the creation of new acquisition modules and at the same time encourages scalability. For situations that require low-level access to the hardware, modules may instead request direct access from the Manager.

The data management system in ACQ4 is designed to emphasize flexibility and longevity. Data is organized into a hierarchy of directories with user-defined structure. Each directory contains a human readable index file that stores annotations and other metadata related to both the directory and any files contained within it. Most data acquired by ACQ4 is stored using the HDF5 file format (www.hdfgroup.org). These files contain both the raw data arrays, for example from camera and digitized recordings, as well as meta-information related to the recordings. ACQ4 provides libraries for reading these files in both Python and MATLAB. When the data is analyzed, the results may be stored in an SQLite relational database file (www.sqlite.org). The use of industry-standard HDF5 and SQLite formats helps to ensure that data is readable by a variety of different applications, both now and in the future. 




Manager
-------

The Manager is the central object in ACQ4. It is used mainly to initialize devices, launch new modules, inquire about existing modules and devices, and configure hardware for running synchronized tasks. The Manager is not visible to the user, but it is nevertheless helpful to understand that it exists and that it is working behind the scenes to make sure everything runs together smoothly. 

Devices
-------

A :ref:`device <userDevices>`, as discussed in this documentation, refers either to a single physical piece of hardware or its logical representation within ACQ4. A device can be a camera, patch amplifier, temperature controller, micromanipulator, ADC, etc. It is common for devices to communicate with the computer solely via an ADC board (shutters and LEDs, for example). Such devices are still considered as distinct from the ADC device itself. 


Modules
-------

A *module* is a single, independently functioning user interface. Each module has its own window and can be opened/closed without affecting other modules. By default, ACQ4 starts by displaying the :ref:`manager module <userModulesManager>`. As you might guess, this is a user interface to the Manager itself, from which you can launch new modules and interact directly with devices in the system. Other modules include:
    
* :ref:`Camera <userModulesCamera>` - live streaming and recording of video
* :ref:`Patch <userModulesPatch>` - for monitoring progress in cell patching and long-term cell health
* :ref:`Task Runner <userModulesTaskRunner>` - the workhorse for designing and running tasks
* :ref:`Imager <userModulesImager>` - for laser scanning imaging
* :ref:`Data Manager <userModulesDataManager>` - for organizing and browsing data, also the access point for analysis modules 

.. _userPrinciplesTasks:

Tasks
-----

Although it is possible to directly interact with each device, the Manager provides a high-level system that handles all details of configuring and synchronizing devices to perform complex acquisition tasks. User interface modules may acquire data by submitting task requests to the Manager, which runs each queued task in order as hardware becomes available. This system greatly reduces the effort required to develop new data acquisition modules by providing a simple and flexible language for describing a set of synchronous device activities.

A *task* is a set of instructions issued to a group of devices all at once. For example, making a 1-second voltage clamp recording might involve 1) configuring the amplifier to switch to voltage clamp mode with a particular holding potential and 2) configuring the ADC to record on the correct channel for 1 second. A more complicated task might involve a voltage clamp recording synchronized with a camera recording, a laser flash, and a specific set of scanning mirror commands, while recording temperature. Any module may request that the Manager run a task on its behalf, and the Manager makes sure these requests do not collide--two tasks using the same hardware may not run at the same time.

The :ref:`Task Runner module <userModulesTaskRunner>` is designed to allow fast and easy prototyping of tasks. It provides a graphical interface allowing the user to select which devices are to be included in the task and to configure each device.

Data Handling
-------------

Experimental results are generally stored immediately as they are collected. It is the user's responsibility to decide where to store data *before* actually collecting it. This allows data to be collected rapidly and efficiently during crucial moments. 

Data is stored in hierarchies of folders with a file named ".index" in each folder. This index file stores meta-information about each file and allows the user (and modules) to annotate each file as it is stored. The index files are human-readable, although it is gemerally preferred to use ACQ4's built-in data management to handle these files. Individual raw data files are stored as :ref:`MetaArray files <userMetaArrayFiles>`, which use the standard `HDF5 <http://www.hdfgroup.org/HDF5/>`_ format. This data can be read by many third-party analysis applications.

The hierarchical file storage allows complete flexibility when designing experiments. This can be problematic for analysis, however, since there is no guarantee that all data will be laid out according to some predetermined structure. To some extent, it is the responsibility of the experimenter to make sure data is organized consistently where required. 

The built-in analysis system also stores data and results using an SQL database, which generally forces all data to conform to the same layout. Thus we have a 2-tier approach to data handling: data is first collected in a hierarchical format allowing flexibility, and is later homogenized into SQL tables for analysis.

.. _userCoordinateSystems:

Coordinate systems in ACQ4
--------------------------

The experiments that ACQ4 is designed to handle often involve multiple devices whose spatial relationships to each other must be calibrated, tracked, and reported. For example, a user may wish to collect a set of images from a range of locations across a sample, mark locations for later reference, or direct a scanning laser to specific sites in the sample. To accomplish this, a global coordinate system is used throughout ACQ4 to represent the physical coordinates of the sample. Any recording or stimulation that has a defined spatial relationship to the sample is automatically registered with the global coordinate system. Thus, images and photostimulation data are automatically stored alongside their global position and scale, allowing automatic reconstruction of image mosaics (multiple tiled images). 

A broad subclass of devices, referred to as :ref:`optomechanical devices <userDevicesOptomech>`, represent hierarchically-linked hardware with defined physical or optical relationships to one another and, ultimately, to the global coordinate system. The choice of an appropriate global coordinate system is arbitrary and left to the experimenter, although in systems which use any type of imaging, the global coordinate system is typically chosen to be fixed relative to the imaged subject. Static relationships between devices are specified in the device configuration file, whereas any changes in dynamic relationships (for example, when a motorized stage moves, or an objective lens is changed) will be immediately reflected in the coordinate system transformations between devices in the hierarchy. In most cases, the static configuration is determined and written manually. For more complex relationships, however, automated calibration functions may be used to assist in generating the necessary configuration. 

For example, a motorized stage, microscope, and camera may all be linked optomechanical devices. As the stage moves, the global coordinate location of the microscope and camera will shift to reflect this new arrangement. Likewise, changing the objective lens currently in use will change the optical scaling and offset associated with the microscope, which in turn defines the boundaries of the camera sensor relative to the sample. In this example, the scaling of the camera sensor coordinates would be measured manually under different objective lenses by imaging a calibration target or by moving the sample by a known distance. Because all coordinates are represented in 3D, it is also possible to seamlessly and transparently add Z-control such as a motorized focusing mechanism.

The end result is that devices in the optomechanical hierarchy generate data that is registered to the physical coordinates of the sample, and this requires no effort from the user during the experiment as long as ACQ4 is able to record positioning information. The structure of this device hierarchy is entirely user-definable, allowing ACQ4 to work with arbitrary device configurations.

