What is ACQ4?
=============

ACQ4 means "Acquisition program, variation 4". ACQ4 is the fourth in a lineage of electrophysiology applications developed and used in the Manis Lab. ACQ4 is a complete software system for data acquisition and analysis in neurophysiology research. The system is currently most suited for patch clamp electrophysiology, photostimulation and fluorescence imaging experiments.

Features:

* Protocol design interface allows easy creation of stimulation / recording protocols combining and synchronizing any number of devices
* Live camera viewing geared toward slice imaging for patch clamp and online analysis of calcium imaging
* Easy photostimulation mapping control
* Sophisticated data analysis system
* Integrated data manager allows easy, customizable data storage, browsing, and export.
* Designed to be a flexible, general-purpose experiment acquisition and analysis interface.
* Highly modular and scalable design--easy to expand support for new hardware and experiments
* Open source and cross-platform. Runs in Windows, Linux, and OSX (acquisition may be limited depending on your hardware, though)

A bit more history about the lineage of this program:

* ACQ3 (2000-present): A MATLAB-based program, developed in 2000 by Scott Molitor and Paul Manis. ACQ3 only supported patch clamp electrophysiology (imaging was handled by another program and synchronization in hardware), but was designed to allow the generation of arbitrary stimuli and an exploration of multidimensional stimulus space. It was also designed to be easily used by simplifying the user interface so that most acquisition during experiments could be performed with only a few button presses and minimal command line interaction. The program is still in use in the lab for some experiments, but has largely been replaced by ACQ4, which has an integrated approach to handling hardware and a wider feature set. A separate MATLAB program, mat_datac, handles the data analysis for ACQ3. ACQ2 (1999,2000) was short-lived early version of ACQ3, while ACQ (no number) was a much earlier program written in C and Fortran. [The conversion to MATLAB was driven in part by the availability of drivers for NI boards, and because MATLAB provided core resources for handling data arrays similar to those in DATAC. A limitation of MATLAB is that the graphics, relative to the previous platforms and ACQ4, are slow.]
* DATAC (1986-1999). This was a program written in C (not even C++), that ran under DOS. It was originally written by Daniel Bertrand and Charles Bader, CMU Geneva (Bertrand D, Bader CR. DATAC: a multipurpose biological data analysis program based on a mathematical interpreter. Int J Biomed Comput. 1986 18:193-202.). In collaboration with Daniel Bertrand, the Manis lab heavily modified and extended this program to include data acquisition for intracellular (sharp electrode, current clamp), field potential, and patch-clamp (current and voltage clamp) recordings, and to work with the PharLab memory management for DOS to handle larger data sets. DATAC provided a command line interpreter, handling of data arrays ("strips") similar to MATLAB, curve fitting and signal processing functions, on-line data display and figure generation, and macros (including semi-automated data acquisition using multiple protocols, and semi-automated analysis).
* RATAVG, ACQ and variants (1977-1985) were written in PDP-11 assembler, and in a mixture of assembler and Fortran, under RT-11 and RSX-11 on DEC 11/40 and 11/23 systems at the Univ. of Florida and Vanderbilt. The programs included a command-line interpreter to control stimulus parameters, a data acquisition subsystem, and real-time display of incoming data on vector-based graphics terminals. Pretty basic, but blazingly fast. We're almost back to that speed…
