MultiClamp Devices
==================

MultiClamp 700A/B devices support:
    
* Simultaneous input/output on one or both electrode channels.
* Recording all MultiClamp state parameters along with physiological data.
* Controlled mode switching VC <--> I=0 <--> IC



Configuration Options
---------------------

Multiclamp 700A/B, single channel. 
To use two channels, simply define a second device with the appropriate 
device string. Note: if an incorrect device string is used, an error message
will be pronted which lists the available device strings.

::

    Clamp1:
        driver: 'MultiClamp'
        config:
            channelID: 'model:MC700A,com:3,dev:0,chan:1'
            commandChannel: 
                device: 'DAQ'
                channel: '/Dev1/ao0'
                type: 'ao'
            primaryChannel: 
                device: 'DAQ'
                channel: '/Dev1/ai10'
                mode: 'NRSE'
                type: 'ai'
            secondaryChannel: 
                device: 'DAQ'
                channel: '/Dev1/ai9'
                mode: 'NRSE'
                type: 'ai'
            vcHolding: -50e-3
            icHolding: 0.0
            settings:  # Default amplifier state. The amplifier will be 
                    # reconfigured with these options every time ACQ4 is 
                    # started. 
                IC:
                    HoldingEnable: False
                    Holding: 0.0
                    TestSignalEnable: False
                    #SlowCurrentInjEnable: False
                    NeutralizationEnable: True
                    #OscKillerEnable: True
                    PrimarySignalGain: 2
                    PrimarySignalLPF: 20e3
                    PrimarySignalHPF: 0
                    OutputZeroEnable: False
                    BridgeBalEnable: True
                    BridgeBalResist: 15e6
                VC:
                    HoldingEnable: False
                    Holding: 0.0
                    TestSignalEnable: False
                    #SlowCurrentInjEnable: False
                    #NeutralizationEnable: False
                    WholeCellCompEnable: False
                    RsCompEnable: False
                    #OscKillerEnable: True
                    PrimarySignalGain: 2
                    PrimarySignalLPF: 20e3
                    PrimarySignalHPF: 0
                    OutputZeroEnable: False
                    LeakSubEnable: False

Manager Interface
-----------------


Protocol Runner Interface
-------------------------
