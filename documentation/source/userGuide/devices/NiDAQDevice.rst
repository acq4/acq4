NiDAQ Devices
=============

National Instruments data acquisition devices are often the central hub of control and synchronization in experiments run by ACQ4. Any devices which make use of the NI DAQmx library should work. However, this has only been tested with E- and M-series boards. The PCI-6259 is a good board with 4 analog outputs that supports most current uses for ACQ4.

Configuration Options
---------------------

Configuration for this device is very simple. Note that a single 'NiDAQ' device in ACQ4 can be used to control *all* devices which are available for DAQmx using the proper resource strings like '/DevN/channelM'.

::
    
    DAQ:  # The name of this device (will be referenced in the configs of other devices)
        driver: 'NiDAQ'
        config:
            # Specifies the default mode to use for all AI ports.
            # Options are 'RSE', 'NRSE', and 'DIFF'
            defaultAIMode: 'NRSE'


TaskRunner Interface
--------------------

