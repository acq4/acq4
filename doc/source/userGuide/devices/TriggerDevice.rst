Trigger Devices
===============

Triggers are very simple devices that do nothing more than assign a device name to a particular PFI input channel on the DAQ. This allows tasks to be executed that require a particular input line to be activated before starting.

Note that other devices (cameras in particular) define their own triggering capabilities; it is not necessary to define a separate trigger device in that case.


Configuration Options
---------------------

Example configuration for a foot switch connected to a DAQ PFI. The switch can then be used to trigger the start of a task.

::
  
    FootSwitch:
        driver: 'Trigger'
        config:
            DAQ: '/Dev1/PFI5'
  

Manager Interface
-----------------


Protocol Runner Interface
-------------------------
