.. _userDevicesCoherentLaser:
    
Coherent ultrafast lasers
=========================

ACQ4 supports Coherent laser devices with all of the features provided by the generic Laser device class.
Additionally, serial commuication to the laser driver is supported with the following features:
    
* Monitoring of onboard output power reporting
* Wavelength control
* Dispersion correction control



Configuration Options
---------------------

Example configuration:

::
    
    Laser-2P:
        driver: 'CoherentLaser'
        port: 9
        baud: 19200
        scope: 'Microscope'
        pulseRate: 90*MHz                      ## Laser's pulse rate
        pCell:
            device: 'DAQ'
            channel: '/Dev1/ao1'
            type: 'ao'
        shutter:
            device: 'DAQ'
            channel: '/Dev1/line31'           ## channel for triggering shutter
            type: 'do'
            delay: 30*ms                      ## how long it takes the shutter to fully open
        defaultPowerMeter: 'NewportMeter'
        calibrationWarning: 'Filter in?'
        alignmentMode:
            pCell: 100*mV
        #pCell:
            #channel: 'DAQ', 'Dev1/ao2'

Manager Interface
-----------------


Task Runner Interface
---------------------
