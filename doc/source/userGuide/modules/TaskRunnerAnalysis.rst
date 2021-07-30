.. _userModulesTaskRunnerAnalysis:

Task Runner online analysis modules
===================================

The :ref:`Task Runner <userModulesTaskRunner>` module, in addition to configuring devices for data acquisition, also allows online analysis modules to be added to each task. These modules provide immediate access to analysis during data acquisition, and communicate with the Task Runner via a simple plugin interface. To begin developing custom Task Runner analysis modules, see the :ref:`developer documentation <devModulesTaskRunnerAnalysis>`.

ACQ4 currently includes two online analysis modules:

Imaging
-------

The imaging analysis module provides a simple interface for viewing image data from laser scanning tasks. This module reads the laser scanning configuration from a :ref:`scanner device <userDevicesScanner>` and a sensor signal from a photodiode or photomultiplier tube. These two data sources are combined to generate images that are displayed within the module.

Photostimulation
----------------

The photostimulation module provides online analysis for photostimulation mapping experiments. It requires access to a :ref:`scanner device <userDevicesScanner>` for reading laser position information and a :ref:`clamp device <userDevicesClamp>` for detecting evoked events from an electrode. Analysis results are displayed as colored spots in a camera module (which, ideally, also displays imagery of the sample being tested). Two analyses are performed:
    
#. The amplitude of the electrode recording immediately after photostimulation ("test" period) is compared to the period immediately prior ("baseline" period).
#. The electrode recording is searched for threshold crossings inside the test period and the number of "spikes" is returned.
    
This analysis module does not store any data to disk.

Controls:

* **Enable** Determines whether the analysis is enabled. If checked, then every task that is executed will be recorded (in memory) and analyzed for evoked events. This analysis is represented as a spot displayed in a :ref:`camera module <userModulesCamera>`, and as a new entry in the list below.
* **Camera Module** Selects the camera module in which to display analysis results.
* **Scanner Device** Selects the scanner device that determines the location of photostimulation flashes during the task.
* **Clamp Device** Selects the electrode amplifier that will be used to measure evoked events.
* **Delete** Causes the currently selected analysis result to be deleted from memory and removed from the camera module.
* **Clamp Baseline** sets the beginning and end times of the baseline period to measure from the clamp trace. Typically this should be defined from t=0 until immediately before the photostimulation.
* **Clamp Test** sets the begining and end times of the test period to measure from the clamp trace. Typically this is defined from a few ms following the photostimulation until 10-50 ms later. 
* **Spike Threshold** The recording amplitude required to be considered a "spike". 
* **Abs / Rel** Determines whether the spike threshold is *absolute* (in volts relative to ground), or *relative* to the median value of the baseline period.
* **Color Mapper**
* **Recompute** 

