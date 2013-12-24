The Patch Module
================

This module is used to assist in patching cells and to monitor cell health throughout the experiment. It provides a few basic functions:
    
* Emits small current (ic mode) or voltage (vc mode) pulses repeatedly and estimates the input resistance to the patch electrode
* Can periodically monitor the cell's status after patching
* Plots estimates of input resistance, access resistance, holding values, and capacitance over time.
* Stores a record of estimate data as it is collected

Mode Shortcut Buttons and Controls
----------------------------------

First, click Start to start the module running. The command that you are sending to the electrode is displayed in the lower 
right plot, while the data coming back is displayed in the top right plot. Pre-programmed modes can be accessed by clicking second row of buttons:

* Bath: Bath mode is a voltage clamp mode where the holding voltage is 0 mV. A pulse is applied so that properties of the electrode can be monitored. 
* Patch: Patch mode is the same as bath, except that now a holding voltage is applied. The default is to hold at -50 mV, but this can be adjusted in the Hold spin box under VC.
* Cell: Cell mode is a current clamp mode. By default, no holding current is applied, but a negative pulse given.
* Monitor: Sets the cycle time to 30 seconds and average to 10.

The first three modes are meant to be used while actively patching a cell. Once a cell is patched you can click Monitor. This
leaves the patch in the configuration that it is in, but instead of sampling every 200 ms it now samples every 30 seconds.
This is meant to be used to monitor the cell health while you are doing your experiment and running protocols. 

You can also manually adjust all of the parameters of the modes. You can turn holding current/voltage and pulses on and off, 
and you can adjust their values. Changes that you make to the values may be reset by clicking one of the Mode shortcut
buttons.

* Delay Length: Determines how much baseline there is before the pulse is given.
* Pulse Length: Determines how long the pulse lasts (as you may have guessed...)
* Cycle Time: Determines how often samples are taken. This is what changes when you click Monitor.
* Average: Causes recordings to be rapidly repeated multiple times and averaged together before displaying.

Parameter Measurements
----------------------

The software automatically calculates a fit to the trace collected in each of the modes. From this fit it calulates 
parameters of the cell, electrode or patch. By default the fit that is calculated is displayed with the patch recording 
as a blue line. To speed things up you can turn off the drawing of this fit by unchecking Draw Fit. If you do this the 
fit and parameters will still be calculated, just not drawn.

All of the parameters will be calulated (and saved if record is pressed). You can plot one or more of the parameters in the
bottom plot window by selecting the check box next to the parameter. You can reset the plot by clicking Reset History. Whenever
you press record, data for all the time that is in the plot window is saved, and incoming data is also saved. 

