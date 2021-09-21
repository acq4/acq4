.. _userModulesManager:
    
The Manager module
==================

The Manager module is the central control point for launching other user interface modules and directly configuring devices. This module is automatically loaded when ACQ4 is started unless the ``-n`` flag is given in the command line.

    .. figure:: images/manager.svg


.. _userModulesManagerModuleList:

Loadable module list
--------------------

On the left is a list of user interface modules which may be loaded. Each entry in this list corresponds to an entry in the :ref:`modules section <userConfigurationModules>` of the configuration. Double-clicking on an entry creates a new instance of that module. Most modules may be loaded multiple times, although some modules will refuse to instantiate more than once.


.. _userModulesManagerDevices:
    
Device control area
-------------------

Each of the devices listed in the ACQ4 :ref:`device configuration <userConfigurationDevices>` may optionally add a control widget to the device control area of the Manager module window. These panels may be rearranged, resized, and stacked as the user sees fit. The behavior of each control panel is described in the corresponding :ref:`device section <userDevices>` of the documentation.
