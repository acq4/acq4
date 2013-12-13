Simulated Patch Clamp Amplifier
================================


Configuration Options
---------------------

Example configuration:


::
    
    Clamp1:
        driver: 'MockClamp'
        config:
            simulator: 'builtin'  # Also supports 'neuron' if you have neuron+python
                                # installed. See lib/devices/MockClamp/neuronSim.py.
                                
            # Define two connections to the DAQ:
            Command:
                device: 'DAQ'
                channel: '/Dev1/ao0'
                type: 'ao'
            ScaledSignal:
                device: 'DAQ'
                channel: '/Dev1/ai5'
                mode: 'NRSE'
                type: 'ai'
                
            # Default holding values.
            icHolding: 0.0
            vcHolding: -50e-3
  

Manager Interface
-----------------


Protocol Runner Interface
-------------------------
