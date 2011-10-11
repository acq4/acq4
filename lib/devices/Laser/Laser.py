class Laser(DAQGeneric):
    """The laser device accomplishes a few tasks:
       - Calibration of laser power so that the power at the specimen can be controlled
         (via pockels cell or Q-switch PWM)
       - Immediate recalibration from photocell or internal measurements
       - integrated control of shutters, q-switches, and pockels cells
       - Pulse commands, allowing the user to specify the energy per pulse
       - Control of wavelength and dispersion tuning when available

    Configuration examples:
    
    Laser-UV:
        driver: 'Laser'
        config: 
            scope: 'Microscope'
            pulseRate: 100*kHz                      ## Laser's pulse rate
            powerIndicator: 'DAQ', '/Dev1/ai11'   ## photocell channel for immediate recalibration
            shutter:
                channel: 'DAQ', '/Dev1/line10'    ## channel for triggering shutter
                delay: 10*ms                      ## how long it takes the shutter to fully open
            qSwitch:
                channel: 'DAQ', '/Dev1/line11'    ## channel for triggering q-switch
            calibrationChannel: 'PowerMeter', 'Power [100mA max]'   ## a channel on a DAQGeneric device
            alignmentMode:
                qSwitch: False                    ## For alignment, shutter is open but QS is off
                shutter: True
            
    Laser-2p:
        driver: 'CoherentLaser'
        config: 
            serialPort: 6                         ## serial port connected to laser
            scope: 'Microscope'
            pulseRate: 100*kHz                      ## Laser's pulse rate; limits minimum pulse duration
            pCell:
                channel: 'DAQ', '/Dev2/ao1'       ## channel for pockels cell control
            calibrationChannel: 'PowerMeter', 'Power [100mA max]'   ## a channel on a DAQGeneric device
            namedWavelengths:
                UV uncaging: 710*nm
                AF488: 976*nm
            alignmentMode:
                power: 5*mW                        ## For alignment, reduce power to 5mW via pCell
                
    Notes: 
        must handle CW, QS, ML lasers
        
        
        
    Protocol examples:
    
    { 'wavelength': 780*nm, 'powerWaveform': array([...]) }  ## calibrated; float array in W
    { 'switchWaveform': array([...]) }                       ## uncalibrated; 0=off -> 1=full power
    { 'pulse': [(0.5*s, 100*uJ), ...] }                     ## (time, pulse energy) pairs
    """
    
    
    def __init__(self, manager, config, name):
        
        daqConfig = {}
        if 'powerIndicator' in config:
            self.hasPowerIndicator = True
            daqConfig['powerInd'] = {'channel': config['powerIndicator'], 'mode': 'ai'}
        else:
            self.hasPowerIndicator = False
            
            
        DAQGeneric.__init__(self, manager, daqConfig, name)
        
    def setAlignmentMode(self, b):
        """If true, configures the laser for low-power alignment mode. 
        Note: If the laser achieves low power solely through PWM, then
        alignment mode will only be available during protocols."""
        
        pass
    
    def setWavelength(self, wl):
        """Set the laser's wavelength (if tunable).
        Arguments:
          wl:  """
        
    def runCalibration(self):
        pass
    
    def createTask(self, cmd):
        return LaserTask(self, cmd)
        
    def protocolInterface(self, prot):
        return LaserProtoGui(self, prot)
        
    def deviceInterface(self, win):
        return LaserDevGui(self)
        
    def outputPower(self):
        """Return the current output power of the laser (excluding the effect of pockel cell, shutter, etc.)
        This information is determined in one of a few ways:
           1. The laser directly reports its power output
           2. A photodiode receves a small fraction of the beam and reports an estimated power
           3. The most recent calibration
           4. The output power is specified in the config file
        """
        pass


class LaserTask(DAQGenericTask):
    def __init__(self, dev, cmd):
        cmd['daqProtocol'] = {}
        if 'powerWaveform' in cmd:
            pass  ## convert power values using calibration data
        elif 'switchWaveform' in cmd:
            pass  ## convert range 0-1 to full voltage range of device
        elif 'pulse' in cmd:
            pass  ## generate pulse waveform
        
        DAQGenericTask.__init__(self, dev, cmd['daqProtocol'])
        
    def configure(self, tasks, startOrder):
        if 'wavelength' in self.cmd:
            self.dev.setWavelength(self.cmd['wavelength'])
        DAQGenericTask.configure(self, tasks, startOrder)

    def storeResult(self, dirHandle):
        pass

