.. _userDevicesTrigger:

Trigger Devices
===============

Triggers are very simple devices that do nothing more than assign a device name to a particular PFI input channel on the DAQ. This allows tasks to be executed that require a particular input line to be activated before starting.

Note that other devices (cameras in particular) define their own triggering capabilities; it is not necessary to define a separate trigger device in such cases.


Configuration Options
---------------------

Example configuration for a foot switch connected to a DAQ PFI. The switch can then be used to trigger the start of a task.

::
  
    FootSwitch:            # the name "FootSwitch" will appear in the list of 
                           # trigger sources in the NiDAQ TaskRunner interface
        driver: 'Trigger'
        channels:
            DAQ: '/Dev1/PFI5'  # This line specifies that the device named "DAQ" can listen
                               # for triggers from "FootSwitch" on its channel "/Dev1/PFI5"


Task Runner Interface
---------------------

Trigger devices do not implement a TaskRunner interface. However, the :ref:`NiDAQ device task interface <userDevicesNiDAQTaskInterface>` allows to select a trigger device.
