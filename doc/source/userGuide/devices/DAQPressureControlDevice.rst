.. _userDevicesDAQPressureControl:

DAQ Pressure Control
====================

.. currentmodule:: acq4.devices.DAQPressureControl.pressurecontrol

.. autoclass:: DAQPressureControl
    :members:
    :undoc-members:
    :show-inheritance:

Pressure controller using a DAQGeneric device: an analog output sets regulator pressure and digital outputs select the source via valves.

Configuration
-------------

* ``daqDevice`` (required): name of the DAQGeneric device
* ``sources`` (required): dict of source name to ``{channel: 0/1}`` valve states
* ``maximum``, ``minimum``, ``regulatorSettlingTime``: inherited from PressureControl

The DAQGeneric device must define an analog output channel named ``pressure_out``.

Example configuration::

    PressureChannels:
        driver: 'DAQGeneric'
        channels:
            valve_1: {device: 'DAQ', channel: '/Dev2/line0', type: 'do'}
            valve_2: {device: 'DAQ', channel: '/Dev2/line1', type: 'do'}
            pressure_out: {device: 'DAQ', channel: '/Dev2/ao0', type: 'ao'}

    PressureController:
        driver: 'DAQPressureControl'
        daqDevice: 'PressureChannels'
        sources:
            regulator: {valve_1: 1, valve_2: 0}
            atmosphere: {valve_1: 0, valve_2: 0}
            user: {valve_1: 0, valve_2: 1}

Features
--------

* Pressure set by writing the ``pressure_out`` holding value
* Source switching by writing valve channel holding values
* Current source inferred by matching channel states to ``sources``

Dependencies
------------

* DAQGeneric device and a DAQ with analog and digital outputs
