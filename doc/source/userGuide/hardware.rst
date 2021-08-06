.. index::
    single: hardware configuration

Hardware Recommendations and Requirements
=========================================

ACQ4 works with a wide range of devices commonly used in neurophysiology experiments. Below, we organize these devices based on the types of experiments being performed and discuss the models and configurations supported by ACQ4.

Basic Patch Clamp Electrophysiology
-----------------------------------

For basic patch clamp experiments (with little or no automation), we recommend MultiClamp 700A/B amplifiers coupled with National Instruments DAQ for digitization. In this approach, we use the DAQ analog input/outputs to command and record from the amplifier, while communicating with the MultiClamp Commander software to configure the device and record its state. A few other amplifiers are supported such as the AxoPatch 200 and AxoProbe; however these have more limited features that make them less appealing for use with ACQ4. We have also used ACQ4 coupled to `MIES <https://github.com/AllenInstitute/MIES>`_ to support systems using ITC 16x/18x devices.

    .. figure:: images/simple_patch_clamp.svg

Patch Clamp Automation
----------------------

ACQ4 supports two more advanced modes of patch clamp operation:

**Semi-automated patch:** In this mode, pipette motion is mostly automated and driven by clicking on target cells. Pipette pressure may also be automated for most or all of the patching process. Pipette cleaning is also possible in this mode. This mode is strongly recommended for multi-patch experiments, and a delight to use even in single patch experiments.

**Fully-automated patch:** In this mode, operators are responsible for initial pipette calibration and target identification, but all patching and protocol execution are handled automatically. This usually requires some amount of code development in order to define the procedure to take immediately after a successful cell patch.

These features require the availability of a camera (or other supported imaging setup), motorized XY stage and focus, and motorized micromanipulators. ACQ4 supports stages and manipulators made by `Sensapex <http://sensapex.com>`_, `Scientifica <https://www.scientifica.uk.com>`_, and `Sutter Instrument <https://www.sutter.com/>`_. A wider range of stage hardware may also be used via μManager, although this is less well tested. It is also strongly recommended to use a motorized objective changer or modify your microscope to report its currently-used objective to ACQ4.

    .. figure:: images/auto_patch.svg


For streamlined operation in semi-automated patch clamp experiments (especially with multiple pipettes), we recommend using an XKE-128 programmable keyboard.

Stage and Manipulator Accuracy
------------------------------

The accuracy of your stage and manipulator hardware can significantly affect ACQ4's ability to perform automated tasks. Note that most vendors report accuracy based on either their minimum step size or their measured _repeatability_. Neither of these metrics is a good indicator of the accuracy that you can expect when asking ACQ4 to place a pipette tip on a target it has not yet visited. Furthermore, accuracy is strongly affected by room temperature fluctuations and cable management. In practice, this means it is up to each lab to determine whether a particular model stage/manipulator will work for their purposes.

As a rough guide, we have found:

- For fully manual operation where it is only necessary to *record* the approximate position of stage/manipulator (say, within 20-50 μm), any of the supported hardware are sufficient.
- For semi-automated operation, accuracy in the range of 5-15 μm is typically sufficient to get a pipette tip close to its target, with the remaining gap handled by manual control. Sensapex and Scientifica both offer products that can achieve this level of accuracy.
- For fully automated operation, precise, closed-loop accuracy in the range of 1-3 μm is more important, and so far has only been achievable with Sensapex products. In some cases this level of accuracy can be achieved with closed-loop machine vision, but that approach is only reliable in limited cases.

(Disclosure: ACQ4, including this documentation, is developed with partial support from Sensapex. For any new project that requires high accuracy, we recommend testing and comparing your options -- most vendors will ship you demo hardware.)


Basic Microscopy Imaging
------------------------

At a minimum, ACQ4 can be used to display live video from any camera supported by μManager, regardless of any other hardware available in the system. However, most of ACQ4's more advanced imaging features depend on access to motorized XY stage, focus, and objective changers. These allow images to be recorded along with metadata describing their position and size, and thus allow them to be reconstructed later. This position and scale feedback is also essential for calibrating other devices in the system such as micromanipulators and laser scan mirrors. Products from both Scientifica and Sensapex have been extensively tested in this context. Support for some other systems exists (in particular via μManager), but is less well tested.

ACQ4 also supports a variety of hardware for controlling illumination and filter selection. This is primarily used to store metadata about imaging conditions, but can also be used in automated acquisition procedures.

For synchronized imaging and electrophysiology, we use digital I/O lines on National Instruments boards for triggering. This requires that your camera have a digital output that reports the timing of exposed frames, and optionally a digital input to trigger the camera. Note: National Instruments offers some inexpensive DAQ devices that have DIO lines but are *not* capable of recording the timing of TTL pulses. We recommend selecting DAQ devices that support buffered DIO operation if imaging synchronization is important for your experiments.

Laser Scanning Imaging
----------------------

ACQ4 supports imaging via laser scanning (2-photon, confocal, etc.) mainly through National Instruments DAQ control over scan mirrors, shutters, Pockels cells, photodiodes, and photomultiplier tubes. Support exists for some lasers (Chameleon, MaiTai), but is generally not necessary. The primary purpose of scanning imaging in ACQ4 is to offer seamless integration of fluorescent indicator imaging with electrophysiology experiments. This has most often been accomplished with NI DAQ boards that have 4 analog outputs (2 for scan mirrors and 1-2 for electrophysiology), although other configurations are possible.

Like with camera-based imaging, ACQ4's more advanced features related to 2p imaging require motorized stage, focus, and objective changers. It is also recommended to use a camera on the same system for calibrating scan mirror voltages and a power meter for calibrating laser power levels.

ACQ4 does not currently support resonant scanning, and integration with ScanImage is a frequently discussed topic waiting to be implemented.

Photostimulation
----------------

Simple full-field photostimulation can be achieved with DAQ control over LED or shuttered illumination. ACQ4 supports focal photostimulation via the same types of hardware as for laser scanning imaging (and in many cases, both imaging and photostimulation are achieved via a single set of hardware). These usually include scan mirrors, shutters, Pockels cells, and photodiodes. Focal photostimulation is operated by grapically specifying stimulus locations and patterns relative to tissue images; in this case a complete imaging setup is required, including motorized stage, focus, and objective changers.


    .. figure:: images/hardware.svg

    Example hardware configuration for photostimulation experiments.
    
    This setup includes:
        
    #. DAQ (NI 6259) which communicates with and synchronizes most of the hardware
    #. Two-channel MultiClamp
    #. Camera (Photometrics QuantEM 512) with trigger input and exposure output connected to DIO lines on the DAQ
    #. Sutter MPC200 for reading the position of the microscope stage
    #. Scanning galvometric mirrors controlled by DAQ analog output
    #. Laser controlled by two DO lines: one to activate the Q-switch, and one to open a shutter
    #. Digitally controlled LEDs for fluorescence imaging
    #. Temperature recording from a Warner controller

.. index::
    pair: multiclamp; hardware configuration

MultiClamp 700A/B
-----------------

ACQ4 records data and outputs stimuli to the MultiClamp channels via the DAQ. At the same time, the state of the MultiClamp is controlled and recorded via serial or USB interface and the "Commander" software supplied by Molecular Devices. In a typical configuration, each channel of the MultiClamp will use one analog output and two analog inputs on the DAQ board, but each of these connections is optional.


.. index:: 
    pair: camera; hardware configuration

Cameras
-------

At a minimum, cameras will connect to the CPU via firewire, USB, frame grabber, etc. This will allow basic use of the camera for displaying and recording images/video. More complex behavior will usually require the camera to be synchronized with the DAQ. This can be accomplished in two different ways:

#. The DAQ triggers the camera, telling it when to record frames. This is only possible with cameras that have a TTL trigger input to be driven by a digital output port on the DAQ.
#. The camera triggers the DAQ, telling it when to start recording. This is only possible if the camera has a TTL output indicating that it has started acquiring frames. Most scientific cameras will at least have an output which indicates when frames are being acquired, which is sufficient for this purpose. This line should be connected to one of the PFI inputs on the DAQ to allow triggering.
    
That takes care of starting the DAQ and camera simultaneously. In addition, we ideally want to know the exact time that each frame is acquired so they can be aligned correctly with other signals recorded on the DAQ. To accomplish this, the camera's exposure TTL output must be connected to a buffered input on the DAQ board (digital input is recommended, but E-series boards do not have buffered digital I/O, so analog input would be required there). During synchronized acquisition, each camera frame will be automatically tagged with the exact time it was acquired.

.. note::
    
    In the diagram above, the exposure TTL signal is connected to both PFI and DI lines on the DAQ. Depending on your camera, this can cause trouble because if the PFI line is not in use, it goes into a low-impedance state which may prevent the exposure signal being recorded correctly on the DI line. Solutions to this are 1) disconnect the PFI line when it is not in use, 2) always make sure the PFI line is in use by requiring that the camera trigger the DAQ, or 3) add some electronics in between to properly isolate the two input lines.

.. index::
    pair: stage; hardware configuration
    
Scanning Galvanometric Mirrors
------------------------------

Scan mirrors may be used in conjunction with one or more laser sources to do scanning laser photostimulation and microscopy. These require only the availability of two analog outputs from the DAQ board and digital or analog control of a Pockels cell, shutter, Q-switch, or some combination of these. In the diagram above, a Zeiss Axioskop FS2 has been modified for use with scanning laser input. 
    
    
Stage Position Control
----------------------

ACQ supports the use of the Sutter MPC200 for stage control and position readout. This position information is used in several modules to track the movement of the sample relative to cameras and laser scanning systems. Stage control may also be used to automate the acquisition of tiled image mosaics.

The MP-285 is also supported for this purpose, but with one caveat: this device is often controlled by a 2 or 3-axis rotary input device. If the computer attempts to read the controller position at the same time the wheel input is in use, it will crash the controller. This is a limitation of the MP-285 which can be worked around with the addition of a custom microcontroller (see lib/drivers/SutterMP285/mp285_hack).

Another option exists for the intrepid-adventurer type (or for those looking for less expensive options). Many electrophysiology stages are controlled by manual micromanipulators. It is possible to read the position of the stage by attaching some variety of rotary encoder to the micromanipulators. A simple option is to use the hardware from a serial mouse to accomplish this task, and ACQ4 supports the use of serial mice as positioning devices. Similarly, an arduino board fitted with rotary encoders could be programmed to output serial mouse protocol.

