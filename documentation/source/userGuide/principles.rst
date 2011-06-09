Principles of Operation
=======================

As experimenters, we are faced with a constantly evolving set of tools, techniques, and goals. Inspiration often comes out of the blue, or suddenly in the middle of an experiment. The central goals of ACQ4 are to 1) make it as easy and fast as possible to design and execute a new type of experiment while 2) allowing established experiments to become streamlined and efficient.

Overview
--------

The ACQ4 user interface is broken up into *modules*. Each module is designed for a particular task such as viewing live camera streams or browsing through previously recorded data. Modules may communicate with one another or operate completely independently. At the core of ACQ4 is an object called the *Manager*. The Manager's most important tasks are to 1) keep track of the *devices* configured in the system and 2) coordinate and synchronize the actions of the modules as they interact with the devices.


Manager
-------

The Manager is the central object in ACQ4. It is used mainly to initialize devices, launch new modules, inquire about existing modules and devices, and configure hardware for running synchronized protocols. The Manager is not visible to the user, but it is nevertheless helpful to understand that it exists and that it is working behind the scenes to make sure everything runs together smoothly. 

Devices
-------

A *device*, as discussed in this documentation, refers either to a single physical piece of hardware or its logical representation within ACQ4. A device can be a camera, patch amplifier, temperature controller, micromanipulator, ADC, etc. It is common for devices to communicate with the computer solely via an ADC board (shutters and LEDs, for example). Such devices are still considered as distinct from the ADC device itself. 


Modules
-------

A *module* is a single, independently functioning user interface. Each module has its own window and can be opened/closed without affecting other modules. By default, ACQ4 starts my displaying the *manager module*. As you might guess, this is a user interface to the :term:`Manager` itself, from which you can launch new modules and interact directly with devices in the system. Other modules include:
    * Camera - live streaming and recording of video
    * Patch - for monitoring progress in cell patching and long-term cell health
    * Protocol Runner - the workhorse for designing and running protocols
    * Data Manager - for organizing and browsing data, also the access point for analysis modules [link]

Protocols
---------

A *protocol* is a set of instructions issued to a group of devices all at once. For example, making a 1-second voltage clamp recording might involve 1) configuring the amplifier to switch to voltage clamp mode with a particular holding potential and 2) configuring the ADC to record on the correct channel for 1 second. A more complicated protocol might involve a voltage clamp recording synchronized with a camera recording, a laser flash, and a specific set of scanning mirror commands, while recording temperature. Any module may request that the Manager run a protocol on its behalf, and the Manager makes sure these requests do not collide--two protocols using the same hardware may not run at the same time.

The Protocol Runner module is designed to allow fast and easy prototyping of protocols. It provides a graphical interface allowing the user to select which devices are to be included in the protocol and to configure each device.

Data Handling
-------------

Experimental results are generally stored immediately as they are collected. It is the user's responsibility to decide where to store data *before* actually collecting it. This allows data to be collected rapidly and efficiently during crucial moments. 

Data is stored in hierarchies of folders with a file named ".index" in each folder. This index file stores meta-information about each file and allows the user (and modules) to annotate each file as it is stored. The index files are human-readable, although it is gemerally preferred to use ACQ4's built-in data management to handle these files. Individual raw data files are stored as :ref:`MetaArray files <user-metaarray-files>`, which use the standard `HDF5 <http://www.hdfgroup.org/HDF5/>`_ format. This data can be read by many third-party analysis applications.

The hierarchical file storage allows complete flexibility when designing experiments. This can be problematic for analysis, however, since there is no guarantee that all data will be laid out according to some predetermined structure. To some extent, it is the responsibility of the experimenter to make sure data is organized consistently wnere required. 

The built-in analysis system also stores data and results using an SQL database, which generally forces all data to conform to the same layout. Thus we have a 2-tier approach to data handling: data is first collected in a hierarchical format allowing flexibility, and is later homogenized into SQL tables for analysis.
