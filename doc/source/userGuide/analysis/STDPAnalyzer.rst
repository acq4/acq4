STDP Analyzer
=============

The STDP Analyzer is designed to do analysis of spike-timing-dependent plasticity experiments collected in ACQ4. It includes support for:
    
    * viewing traces over the timecourse of an experiment
    * averaging across individual traces
    * measuring the maximal slope of a PSP in a given region
    * measuring cell health parameters such as Rm and Vm
    * measuring the time between the PSP and action potential during the conditioning protocol
    * storing analysis results to an analysis database
    * creating summary sheets both with and without plasticity information

Data must be collected using the TaskRunner module with protocols similar to those included in the example configuration under `acq4/config/example/protocols/STDP/`.

Overview
--------

The STDP Analyzer includes tools for analyzing both PSP stimulations and conditioning stimulations. The user specifies which category a particular task sequence falls into when loading the data. Data about PSP stimulations over the course of the experiment will be stored in an "STDP_Trials" table in the analysis database, while overall data about the cell will be stored in an "STDP_Cell" table. 

Workflow
--------

#. Load data using the :ref:`File Loader<userAnalysisFileLoader>` located on the left. This module assumes that PSP stimulations and the conditioning stimulations were recorded as separate task sequences. Load PSP stimulations using the 'Load EPSP File' button, and load conditioning stimulations using the 'Load Pairing File' button. 

#. Set the time interval used for the pairing protocol. In the Pairing Plots tab, the user will see any data loaded with the 'Load Pairing File' button, and an average trace of all the pairing data that has been loaded. There are also two adjustable vertical lines used to mark the time of the PSP and the action potential. Adjust these lines such that the blue line marks the time of the PSP and the red line marks the time of the action potential. When analysis is saved to the database, the positions of these lines will be included. These positions are displayed and can be adjusted in the Control Panel tab. 

#. Set up PSP analysis. Data loaded using the 'Load EPSP File' button will appear in the EPSP plots tab. The top plot (the ExptPlot) in this tab displays timepoints for each of the traces loaded. This plot includes an adjustable region that determines which traces appear in the Traces Plot, located immediately below it. Traces can be averaged together over time using the controls to the left. Adjustable analysis regions appear in the Traces Plot. By default these include a baseline region, which measures the resting membrane potential, a PSP region, which measures the maximal slope of the PSP, and a Cell Health region, which measures the input resistance in response to a current pulse. 

#. Analyze. Once the regions are set, press the 'Analyze' button to make measurements on each trace. Values from these measurements are displayed in the remaining plots. In addition, the time when the maximal slope was found is marked with a dot on each trace. 

#. If analysis is appropriate you can save data in 3 ways:
        * Save to the database using the 'Store to DB' button. This will save analysis about each trace (or averaged trace) to a table called 'STDP_Trials', and analysis about the cell to a table called 'STDP_Cell'. 
        * Save a summary sheet using the "Create Summary Sheet" button. This will pull up a new window with graphs of the PSP, pairing, and analyses of over time, as well as notes about the cell that can then be exported and saved as a png file. This sheet includes plasticity information.
        * Save a blind summary sheet using the "Create Blind Summary Sheet" button. This pulls up a window much like 'Create Summary Sheet', but without any plasticity information. This is useful for screening cells due to resistance or membrane potential changes, or other concerns. 



