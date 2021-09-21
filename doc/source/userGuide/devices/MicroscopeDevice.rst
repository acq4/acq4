.. _userDevicesMicroscope:
    
Microscope Devices
==================

The primary purpose of a Microscope device in ACQ4 is to keep track of a set of objective lenses and either allow the user to specify which lens is currently in use, or automatically determine which is in use. Each objective lens introduces a particular scaling and offset to the :ref:`optomechanical transform hierarchy <userDevicesOptomech>`. This information is used by other devices and modules: 
    
* Cameras generate frames with metadata that specifies the location and scaling of the frame relative to the global coordinate system, as well as which objective was used while acquiring the frame.
* Scanners and Lasers use information about the current optical path to select the correct calibration data.
* The Camera module uses position and scaling data to track the location of a video feed as it moves around the sample.

Although the name 'Microscope' is specific, the features provided are quite general and may be used in other contexts to indicate a change in the optomechanical pathway.

Hardware configuration
----------------------

As an :ref:`optomechanical device <userDevicesOptomech>`, Microscopes may be rigidly connected to any other optomechanical devices without restriction. However, it is very common for a microscope to have a motorized :ref:`stage <userDevicesStage>` as a parent and one or more :ref:`cameras <userDevicesCamera>` and :ref:`scanners <userDevicesScanner>` as children on the device hierarchy::
    
        Stage
          ↓
     Microscope
    [ 5x ] [ 63x ]
          ↓
    Camera, Scanner      

In this contex, a Microscope is essentially a switchable component in the optomechanical transform hierarchy. That is, a Microscope has multiple objectives, each of which carries its own set of transformations. When the currently active objective is changed, the total transformation of the Microscope (and thus, of its children as well) changes with it. 

It is important when collecting data that includes positioning or transform information, that ACQ4 know which objective is currently in use. For this purpose, the user may manually select the current objective every time it changes. However, we have found that it is much more convenient and reliable for these transitions to be handled automatically. Thus, we use a simple microswitch circuit to detect the currently active position on our two-slot objective mounts:
    
    .. figure:: images/microscopeSwitch.svg

The state of the DAQ digital input is then polled with a :ref:`Switch device <userDevicesDIOSwitch>` to detect changes in the objective state.


Configuration Options
---------------------

Below is an example configuration for a microscope device that is rigidly-connected to a motorized stage. It also uses a 'Switch' device to determine the objective lens currently in use.

::
    
    Microscope:
        driver: 'Microscope'
        parentDevice: 'Stage'
        objectiveSwitch: 'Switch', 'objective'  ## monitor the 'objective' channel from the 'Switch' device
        objectives:
            0:  # first slot always has a 5X objective
                5x_0.25NA:
                    name: '5x 0.25na FLUAR'
                    scale: 1.0 / 5.0
            1:  # second slot may have a 40x or 63x objective
                63x_0.9NA:
                    name: '63x 0.9na Achroplan'
                    scale: 1.0 / 63.0
                    offset: 70*um, 65*um
                40x:
                    name: '40x 0.75na Achroplan'
                    scale: 1.0 / 40.0
                    offset: -43*um, 9*um

The supported configuration parameters are:

* **driver** must be 'Microscope'
* **parentDevice** and **transform**, which define the device's :ref:`optomechanical configuration <userDevicesOptomech>`.
* **objectiveSwitch** is an optional pair of values (deviceName, switchName) referring to :ref:`a switch device <userDevicesDIOSwitch>` that is used to indicate the currently used slot on a multi-objective microscope.
* **objectives** describes the set of objectives that may appear in a microscope. First, there is one numerical key per objective 'slot' in the microscope. Next, each numbered slot contains one or more objective descriptors with the following format::
    
      unique_identifier:
          name: "description of objective lens"
          scale: <numerical scale factor>
          offset: <x,y offset>
          
  In the example configuration above, the microscope has two numbered objective 'slots': 0 and 1. The first slot will always have a 5x objective in it, whereas the second slot may have either a 63x or 40x objective. The switch device informs ACQ4 which slot (0 or 1) is currently in use

Manager Interface
-----------------

The :ref:`Manager user interface <userModulesManagerDevices>` for Microscope devices displays a list of the configured objective slots:

    .. figure:: images/Microscope_ManagerInterface.png

From this interface, the user may select which slot is currently active, select the objective lens currently attached to each slot (if more than one are defined), and modify the transformation for each objective. Transform modifications allow the user to test the effects of changing these parameters at runtime, although they do not modify the original configuration file. 
