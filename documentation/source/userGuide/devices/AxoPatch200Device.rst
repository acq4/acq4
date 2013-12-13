AxoPatch Devices
================




Configuration Options
---------------------

::

    AxoPatch200:
        driver: 'AxoPatch200'
        config:
            ModeChannel: 
                device: 'DAQ' 
                channel: '/Dev1/ai13'
                type: 'ai'
            GainChannel: 
                device: 'DAQ' 
                channel: '/Dev1/ai14'
                type: 'ai'
            LPFChannel: 
                device: 'DAQ' 
                channel: '/Dev1/ai15'
                type: 'ai'
            Command: 
                device: 'DAQ' 
                channel: '/Dev1/ao0'
                type: 'ao'
            ScaledSignal: 
                device: 'DAQ' 
                channel: '/Dev1/ai5'
                type: 'ai'
            icHolding: 0.0
            vcHolding: -50e-3

Manager Interface
-----------------


Protocol Runner Interface
-------------------------
