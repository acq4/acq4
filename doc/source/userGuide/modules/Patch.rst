.. _userModulesPatch:

The Patch module
================

This module is used to assist in patching cells and to monitor cell health throughout the experiment. It provides a few basic functions:
    
* Emits small current (ic mode) or voltage (vc mode) pulses repeatedly and estimates the input resistance and access resistance to the electrode or patched neuron.
* Can periodically monitor the cell's status after patching. It is expected that a Patch module may be running concurrently with other modules making use of the same hardware; in this case the modules are automatically synchronizes to avoid resource collisions.
* Plots estimates of input resistance, access resistance, holding values, and capacitance over time. This aids the experimenter in seeing the effects of manipulations on seal resistance, access resistance, and the general health of the cell over the course of the experiment.
* Stores a record of estimate data as it is collected (Note that the Patch module currently does *not* store raw recording data)

    .. figure:: images/patch.svg

The patch module acquires data from a single patch clamp device, which is specified in the :ref:`modules section <userConfigurationModules>` of the configuration file. The following example configuration defines *two* different patch module instances, each of which will use a different clamp device::

    modules:
        Patch 1:
            module: 'Patch'
            config:
                clampDev: 'Clamp1'
        Patch 2:
            module: 'Patch'
            config:
                clampDev: 'Clamp2'

For an example of a typical patch experiment using this module, see the :ref:`patching tutorial <userTutorialsPatching>`.


Stimulus controls
-----------------

When the Patch module is running, it repeatedly outputs a square pulse waveform to the patch clamp amplifier while recording from its electrode signal. The clamp mode, pulse shape, and timing are all configured in the set of controls labeled "Stimulus control" in the figure above.

* **VC/IC** radio buttons set the recording mode of the amplifier to voltage clamp or current clamp, respectively. Note that the amplifier's mode will not change until immediately before a recording is about to be made.
* **Pulse** check boxes determine whether a square pulse should be present in the stimulus waveform, while the adjacent spin boxes select the amplitude of the pulse.
* **Hold** check boxes determine whether any holding potential or current is applied, and the adjacent spin boxes select the value. 
* **Delay Length** sets the amount of time in the stimulus waveform before and after the square pulse.
* **Pulse Length** sets the duration of the square pulse in the stimulus waveform.
* **Cycle Time** sets the desired amount of time from between the onset of consecutive recordings.
* **Average** sets the number of pulse recordings to average together before displaying and analyzing the result.

Typically, the experimenter will want to change these settings multiple times over the course of patching a cell. For convenience, there are four buttons which immediately apply pre-set values to the stimulus controls described above:
    
* **Bath** is used to measure the electrode resistance while the electrode is in the bath, away from a cell.
    * Mode = VC
    * Holding = disabled
    * Pulse = enabled (default amplitude is -10 mV)
    * Delay Length = 10 ms
    * Pulse Length = 10 ms
    * Cycle Time = 200 ms
    * Averages = 1
* **Patch** is used to measure the seal resistance while the electrode is forming a gigaohm seal. It may also be used to measure the input and access resistance of the cell after rupturing the cell membrane.
    * Mode = VC
    * Holding = enabled (default is -65 mV)
    * Pulse = enabled (default amplitude is -10 mV)
    * Delay Length = 10 ms
    * Pulse Length = 10 ms
    * Cycle Time = 200 ms
    * Averages = 1
* **Cell** is a current-clamp pulse used to measure the state of the cell.
    * Mode = IC
    * Pulse = enabled (default amplitude is -30 pA)
    * Delay Length = 30 ms
    * Pulse Length = 150 ms
    * Cycle Time = 250 ms
    * Averages = 1
* **Monitor** is used to periodically monitor the health of the cell and status of the access resistance during the course of an experiment.
    * Cycle Time = 40 s
    * Averages = 5

To begin recording, click the **Start** button. The command waveform and electrode recording signals are displayed in the right-side panels. Any of the settings described above may be changed at any time during the experiment. 


Patch analysis
--------------

For each recording, the Patch module calculates the access resistance, input resistance, resting membrane potential (or holding current), and cell capacitance. This is done by fitting the decay of the charging transient to a single-exponential function [1]_. To see the fit that is being computed for each recording, check the **Draw fit** box. 

To display a time plot of each analysis parameter, click the check box adjacent to the parameter name (see the 'Analysis control' section in the figure above). These plots are used to monitor seal resistance during patching and to monitor access resistance, resting membrane potential, and other cell health-related parameters during the course of an experiment. To clear this plot data in between cells, click **Reset History**.

As long as the **Record** button is depressed, all analyzed parameters are stored to a 'Patch' folder in the currently selected :ref:`storage directory <userModulesDataManagerStorageDirectory>`. Note that when **Record** is first clicked, the entire history of analysis results is written into this folder; thus it is important to click **Reset History** between cells to avoid recording patch data from one cell into the storage directory for another cell.


.. [1] Santos-Sacchi, 1993. Voltage-dependent Ionic Conductances of Type I Spiral Ganglion Cells from the Guinea Pig Inner Ear. J Neurosci. 1993 Aug;13(8)


