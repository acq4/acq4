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

These features require the availability of a camera (or other supported imaging setup), motorized XY stage and focus, motorized micromanipulators, and pressure controllers. ACQ4 supports stages and manipulators made by `Sensapex <http://sensapex.com>`_, `Scientifica <https://www.scientifica.uk.com>`_, and `Sutter Instrument <https://www.sutter.com/>`_. A wider range of stage hardware may also be used via μManager, although this is less well tested. It is also strongly recommended to use a motorized objective changer or modify your microscope to report its currently-used objective to ACQ4.

    .. figure:: images/auto_patch.svg

    Example hardware configuration for fully- or semi-automated patch clamp experiments.

For streamlined operation in semi-automated patch clamp experiments (especially with multiple pipettes), we recommend using an XKE-128 programmable keyboard.

Stage and Manipulator Accuracy
------------------------------

The accuracy of your stage and manipulator hardware can significantly affect ACQ4's ability to perform automated tasks. Note that most vendors report accuracy based on either their minimum step size or their measured *repeatability*. Neither of these metrics is a good indicator of the accuracy that you can expect when asking ACQ4 to place a pipette tip on a target it has not yet visited. Furthermore, accuracy is strongly affected by room temperature fluctuations and cable management. In practice, this means it is up to each lab to determine whether a particular model stage/manipulator will work for their purposes.

As a rough guide, we have found:

- For fully manual operation where it is only necessary to *record* the approximate position of stage/manipulator (say, within 20-50 μm), any of the supported hardware are sufficient.
- For semi-automated operation, accuracy in the range of 5-15 μm is typically sufficient to get a pipette tip close to its target, with the remaining gap handled by manual control. Sensapex and Scientifica both offer products that can achieve this level of accuracy.
- For fully automated operation, precise, closed-loop accuracy in the range of 1-3 μm is more important, and so far we have only achieved this with Sensapex products. In some cases this level of accuracy can be achieved with closed-loop machine vision, but that approach is only reliable in limited cases.

(Disclosure: ACQ4, including this documentation, is developed with partial support from Sensapex. For any new project that requires high accuracy, we recommend testing and comparing your options -- most vendors will ship you demo hardware.)


Basic Microscopy Imaging
------------------------

At a minimum, ACQ4 can be used to display live video from any camera supported by μManager, regardless of any other hardware available in the system. However, most of ACQ4's more advanced imaging features depend on access to motorized XY stage, focus, and objective changers. These allow images to be recorded along with metadata describing their position and size, and thus allow them to be reassembled later. This position and scale feedback is also essential for calibrating other devices in the system such as micromanipulators and laser scan mirrors. Products from both Scientifica and Sensapex have been extensively tested in this context. Support for some other systems exists (in particular via μManager), but is less well tested.

ACQ4 also supports a variety of hardware for controlling illumination and filter selection. This is primarily used to store metadata about imaging conditions, but can also be used in automated acquisition procedures.


    .. figure:: images/imaging.svg

For synchronized imaging and electrophysiology, we use digital I/O lines on National Instruments boards for triggering. This requires that your camera have a digital output that reports the timing of exposed frames, and optionally a digital input to trigger the camera. Note: National Instruments offers some inexpensive DAQ devices that have DIO lines but are *not* capable of recording the timing of TTL pulses. We recommend selecting DAQ devices that support buffered DIO operation if imaging synchronization is important for your experiments.

Laser Scanning Imaging
----------------------

ACQ4 supports imaging via laser scanning (2-photon, confocal, etc.) mainly through National Instruments DAQ control over scan mirrors, shutters, Pockels cells, photodiodes, and photomultiplier tubes. Support exists for some lasers (Chameleon, MaiTai), but is generally not necessary. The primary purpose of scanning imaging in ACQ4 is to offer seamless integration of fluorescent indicator imaging with electrophysiology experiments. This has most often been accomplished with NI DAQ boards that have 4 analog outputs (2 for scan mirrors and 1-2 for electrophysiology), although other configurations are possible.

Like with camera-based imaging, ACQ4's more advanced features related to 2p imaging require motorized stage, focus, and objective changers. It is also recommended to use a camera on the same system for calibrating scan mirror voltages and a power meter for calibrating laser power levels.

ACQ4 does not currently support resonant scanning, and integration with ScanImage is a frequently discussed topic waiting to be implemented.

Photostimulation
----------------

ACQ4 supports focal photostimulation mapping via the same types of hardware as for laser scanning imaging (and in many cases, both imaging and photostimulation are achieved via a single set of hardware). These usually include scan mirrors, shutters, Pockels cells, and photodiodes. Focal photostimulation is operated by graphically specifying stimulus locations and patterns relative to tissue images; in this case a complete imaging setup is required, including motorized stage, focus, and objective changers. Simple full-field photostimulation can be achieved with a DAQ controlling LED or shuttered illumination.

    .. figure:: images/photostimulation.svg

    Example hardware configuration for photostimulation experiments.
