.. _devUnitSymbols:

Unit Symbols
============

All physical values in ACQ4 are expressed internally without any SI scale prefix. For example, a value of 100 mV is always expressed as 1e-3, 20 um is expressed as 20e-6, and so on. This is done to avoid ambiguities when it is not clear what the intended scaling of any particular variable should be. 

This added clarity initially comes at a cost: numerical values are expressed in a system of units that may be counterintuitive to those accustomed to always thinking in terms of mV, um, pA, and so on. To alleviate this cost, ACQ4 defines a very simple library of 'cosmetic' symbols that are used to apply correct scaling to values expressed in more natural units. These are nothing more than scale factors assigned to scaled unit names::

    V = 1.0
    mV = 1e-3
    uV = 1e-6
    mm = 1e-3
    um = 1e-6
    nA = 1e-9
    pA = 1e-12
    ...etc...

To use these symbols, simply multiply any physical values by the appropriate unit symbols. The scale factor applies a correction to convert the given value into unscaled units. Note that the physical unit suffix (V, m, A, etc.) has no effect other than as an annotation to make the source code more readable.

For example, say we wish to set the voltage on a DAQ channel to 100 mV::

    daq.setChannelVoltage('/Dev1/ao0', 0.1)

This example can be expressed equivalently with more natural units::

    daq.setChannelVoltage('/Dev1/ao0', 100*mV)  # 100*mV eveluates to 0.1

More complex unit specifications are also possible. For example, :ref:`DAQGeneric channels <userDevicesDAQGeneric>` often include a calibrated scale factor that indicates how volts recorded by the DAQ should be interepreted as some other physical units. The following example :ref:`device configuration <userConfigurationDevices>` demonstrates this::
    
    Thermometer:
        device: 'DAQ'
        channel: '/Dev1/ai13'
        type: 'ai'
        units: 'C'
        scale: (10*mV) / (1.25*C)  # calibrated at 10 mV per 1.25 deg. C

Unit symbols are available throughout ACQ4, including in configuration files, waveform specifications, and all parts of the source code (wherever acq4.util.units is imported).


