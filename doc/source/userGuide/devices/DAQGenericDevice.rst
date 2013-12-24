Generic DAQ Devices
===================

Any device that simply requires direct access to one or more DAQ channels may be configured as a 'DAQGeneric' device. 


Configuration Options
---------------------

Example configuration for controlling a laser Q-switch and shutter via two digital output lines:
    
::

    LaserControl:
        driver: 'DAQGeneric'
        config:
            shutter:
                device: 'DAQ'
                channel: '/Dev1/line30'
                type: 'do'
                holding: 0
            qSwitch:
                device: 'DAQ'
                channel: '/Dev1/line29'
                type: 'do'
                holding: 0
    

Example AxoProbe 1A configuration:

::

    AxoProbe1A:
        driver: 'DAQGeneric'
        config:
            Command:
                device: 'DAQ' 
                channel: '/Dev1/ao0'
                type: 'ao'
                units: u'A' 
                scale: 0.5*1e9 ## scale is for headstage H = 0.1L, I = 20H nA/V = 2nA/V : 1V/2nA
                userScale: 1e-12  ## tells scale for output to be in units of pA
            ScaledSignalV:
                device: 'DAQ' 
                channel: '/Dev1/ai3'
                type: 'ai'
                units: u'V'
                scale: 10 ## net gain is fixed at 10 (if f1 switch is set to 10V1): 1V/0.1V
            ScaledSignalI:
                device: 'DAQ' 
                channel: '/Dev1/ai4'
                type: 'ai'
                units: u'A'
                scale: 1e8 ## scale is H = 0.1, gain = 10/H mV/nA = 100 mV/nA: 1V/10nA

Example configuration for a calibrated photodiode:
    
::
    
    Photodiode-UV:
        driver: 'DAQGeneric'
        config:
            Photodiode:
                device: 'DAQ'
                channel: '/Dev1/ai7'
                type: 'ai'
                scale: 49.1*mW/V  ## calibrated 2011.11.09
                offset: 0.0*mV
                units: 'W'
                settlingTime: 2*ms
                measurementTime: 50*ms
    


Manager Interface
-----------------


Protocol Runner Interface
-------------------------
