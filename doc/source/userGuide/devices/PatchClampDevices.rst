.. _userDevicesPatchClamp:

Patch-Clamp Amplifiers
======================

Three amplifiers are currently supported for electrophysiology experiments: the MultiClamp 700A and 700B, and the AxoPatch 200. In addition, any device lacking computer control (for example, the AxoProbe 1A)  may be used as a generic analog device. 
ACQ4 records all remotely accessible parameters from the MultiClamp Commander software (Molecular Devices) or from the analog telegraph outputs on the AxoPatch 200. For the MultiClamp, several parameters such as the VC/CC mode, gain, and signal selection may also be controlled from the user interface. ACQ4 automatically applies the appropriate scaling constants for input and output to the analog channels.

Switching between voltage and current clamp is handled automatically by the device, first switching to I=0 mode before changing the holding commands sent to the analog output. This allows ACQ4 to rapidly and safely switch between recording modes without user interaction. The AxoPatch 200 lacks computerized control; in this case ACQ4 prompts the user to switch modes when necessary. 

Amplifier devices:
    
.. toctree::
    :maxdepth: 1
    
    MultiClampDevice
    AxoPatch200Device
    MockClampDevice

See also: :ref:`AxoProbe1A example <userDevicesDAQGenericAxoProbeExample>` in DAQGeneric.


