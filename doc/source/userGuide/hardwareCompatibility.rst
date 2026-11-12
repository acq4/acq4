.. _userHardwareCompatibility:

.. index::
    single: hardware compatibility

Hardware Compatibility
======================

This page lists hardware commonly found in patch clamp and imaging rigs, and whether ACQ4 supports it. Use it to check whether an existing rig will work with ACQ4, or to confirm that new hardware will be supported before you buy it. For recommendations on which hardware to choose for a particular type of experiment, see :doc:`hardware`.

Each entry is marked with one of the following support levels:

.. list-table::
    :widths: 25 75
    :header-rows: 0

    * - 🟢 **Supported**
      - Actively maintained and in regular use on ACQ4 developer systems.
    * - 🟡 **Untested**
      - Supported, but not currently tested on developer systems. Expect it to work, but minor fixes may be needed; please report problems.
    * - 🟠 **Legacy**
      - Code exists but has not been used in a long time. It will most likely need to be updated before it works with the current version of ACQ4.
    * - 🔴 **Unsupported**
      - No support in ACQ4.

Hardware that is not listed here may still work:

* Many cameras and stages are usable through `μManager <https://micro-manager.org>`_ (see :doc:`devices/MicroManagerCameraDevice` and :doc:`devices/MicroManagerStageDevice`).
* Any device that is controlled by, or reports its state through, analog or digital signals can be operated by a DAQ board using :doc:`devices/DAQGenericDevice`.
* New devices can be added by writing a device class; see :doc:`the developer guide </devGuide/deviceDrivers>`.

If you have hardware that works (or doesn't) and is listed incorrectly here, please let us know by opening an issue on `GitHub <https://github.com/acq4/acq4/issues>`_.


Data Acquisition (DAQ)
----------------------

.. list-table::
    :widths: 15 35 20 30
    :header-rows: 1

    * - Status
      - Hardware
      - Device class
      - Notes
    * - 🟢
      - National Instruments DAQmx devices (M-series, X-series; PCIe, PXIe, USB)
      - :doc:`devices/NiDAQDevice`
      - Recommended. Choose a board with buffered (hardware-timed) digital I/O if you need to synchronize with camera exposures.
    * - 🟡
      - Instrutech ITC-16 / ITC-18, NI DAQ via `MIES <https://github.com/AllenInstitute/MIES>`_
      - :doc:`devices/MIESPatchPipetteDevice`
      - MIES (Igor Pro) owns the DAQ. ACQ4 gets test pulse, amplifier, and pressure control through MIES, but cannot run its own acquisition protocols.
    * - 🔴
      - Molecular Devices Digidata series
      -
      -
    * - 🔴
      - HEKA / Instrutech ITC (direct control, without MIES)
      -
      -
    * - 🔴
      - Measurement Computing, LabJack, Arduino-based DAQ
      -
      -


Patch Clamp Amplifiers
----------------------

.. list-table::
    :widths: 15 35 20 30
    :header-rows: 1

    * - Status
      - Hardware
      - Device class
      - Notes
    * - 🟢
      - Molecular Devices MultiClamp 700A / 700B
      - :doc:`devices/MultiClampDevice`
      - Recommended. Requires an NI DAQ for signals and MultiClamp Commander for amplifier state.
    * - 🟡
      - Molecular Devices AxoPatch 200 / 200A / 200B
      - :doc:`devices/AxoPatch200Device`
      - Amplifier state is read from telegraph outputs.
    * - 🟡
      - Molecular Devices AxoProbe 1A and similar analog amplifiers
      - :doc:`devices/DAQGenericDevice`
      - See the :ref:`AxoProbe example <userDevicesDAQGenericAxoProbeExample>`. No automatic gain/mode tracking.
    * - 🟡
      - Amplifiers controlled by MIES (e.g. MultiClamp 700B)
      - :doc:`devices/MIESPatchPipetteDevice`
      - Mode, holding, auto bias, and auto compensation are set through MIES. See the DAQ section above.
    * - 🔴
      - HEKA EPC 10, EPC 800
      -
      -
    * - 🔴
      - Molecular Devices Axoclamp 900A
      -
      -
    * - 🔴
      - Dagan amplifiers
      -
      -


Cameras
-------

.. list-table::
    :widths: 15 35 20 30
    :header-rows: 1

    * - Status
      - Hardware
      - Device class
      - Notes
    * - 🟢
      - Allied Vision cameras (Vimba X SDK; e.g. Alvium, Mako, Manta)
      - :doc:`devices/VimbaXCameraDevice`
      -
    * - 🟢
      - Hamamatsu ORCA-Flash4.0
      - :doc:`devices/MicroManagerCameraDevice`
      - Via μManager.
    * - 🟢
      - Photometrics cameras (e.g. Prime, Evolve, CoolSNAP)
      - :doc:`devices/MicroManagerCameraDevice`
      - Via μManager.
    * - 🟢
      - QImaging cameras (e.g. Retiga)
      - :doc:`devices/MicroManagerCameraDevice`
      - Via μManager.
    * - 🟢
      - USB webcams (via OpenCV)
      - :doc:`devices/CameraDevice` (``WebcamCamera``)
      - Useful for low-cost rigs and auxiliary views; no hardware triggering.
    * - 🟡
      - Other cameras supported by μManager (e.g. Andor, Basler, FLIR, other Hamamatsu models)
      - :doc:`devices/MicroManagerCameraDevice`
      - Many μManager cameras work immediately, but not all: some will require code adjustments in ACQ4 to handle their particular properties.
    * - 🟠
      - Photometrics cameras via the native PVCAM driver
      - :doc:`devices/PVCamDevice`
      - Use μManager instead (see above).
    * - 🟠
      - QImaging cameras via the native QCam driver
      - :doc:`devices/QCamDevice`
      - Use μManager instead (see above).


Motorized Stages and Focus
--------------------------

.. list-table::
    :widths: 15 35 20 30
    :header-rows: 1

    * - Status
      - Hardware
      - Device class
      - Notes
    * - 🟢
      - Sensapex uMs motorized stage and focus
      - :doc:`devices/SensapexDevice`
      -
    * - 🟢
      - Scientifica SliceScope, MMTP, motorized movement platforms and focus
      - :doc:`devices/ScientificaDevice`
      -
    * - 🟢
      - Dover Motion SmartStage
      - :doc:`devices/StageDevice` (``DoverStage``)
      - Requires the Dover MotionSynergy API.
    * - 🟡
      - Sutter MPC-200 / ROE-200 controlled stages (e.g. MP-78, MT-800)
      - :doc:`devices/SutterMPC200Device`
      -
    * - 🟡
      - Thorlabs MFC1 motorized focus controller
      - :doc:`devices/ThorlabsMFC1Device`
      -
    * - 🟡
      - Stages supported by μManager (e.g. ASI, Prior, Märzhäuser, Ludl)
      - :doc:`devices/MicroManagerStageDevice`
      -
    * - 🔴
      - Luigs & Neumann stages
      -
      -


Micromanipulators
-----------------

.. list-table::
    :widths: 15 35 20 30
    :header-rows: 1

    * - Status
      - Hardware
      - Device class
      - Notes
    * - 🟢
      - Sensapex uMp micromanipulators (3- and 4-axis)
      - :doc:`devices/SensapexDevice`
      - Recommended for fully automated patching.
    * - 🟢
      - Scientifica PatchStar, MicroStar, IVM
      - :doc:`devices/ScientificaDevice`
      -
    * - 🟡
      - Sutter MPC-200 / ROE-200 controlled manipulators (e.g. MP-225, MP-285 on MPC-200)
      - :doc:`devices/SutterMPC200Device`
      -
    * - 🟡
      - New Scale Technologies MPM (Multi-Probe Micromanipulator)
      - :doc:`devices/NewScaleMPMDevice`
      -
    * - 🟠
      - Sutter MP-285 (standalone controller)
      - :doc:`devices/SutterMP285Device`
      -
    * - 🔴
      - Sutter MPC-385, MP-285A, QUAD
      -
      -
    * - 🔴
      - Luigs & Neumann SM-5, SM-10
      -
      -
    * - 🔴
      - Siskiyou, Burleigh / Thorlabs PCS, Narishige manipulators
      -
      -


Objective Changers and Microscopes
----------------------------------

ACQ4 needs to know which objective is in use in order to correctly scale images and calibrate other devices. See :doc:`devices/MicroscopeDevice`.

.. list-table::
    :widths: 15 35 20 30
    :header-rows: 1

    * - Status
      - Hardware
      - Device class
      - Notes
    * - 🟢
      - Sensapex motorized objective changer
      - :doc:`devices/MicroscopeDevice` (``SensapexObjectiveChanger``)
      -
    * - 🟢
      - Scientifica SliceScope objective changer
      - :doc:`devices/ScientificaDevice` (``StageSwitch``)
      - The objective changer axis is read through the Scientifica stage interface.
    * - 🟢
      - Any objective changer or position sensor that reports its state via digital lines
      - :doc:`devices/DIOSwitchDevice`
      - Can also be used to retrofit a manual objective changer with switches.
    * - 🟡
      - Zeiss motorized microscopes via MTB (objective turret, reflector turret, lamps, shutters; e.g. Axio Examiner)
      - :doc:`devices/MicroscopeDevice` (``ZeissMicroscope``, ``ZeissTurret``)
      -
    * - 🔴
      - Olympus, Nikon, Leica motorized microscopes
      -
      -


Pressure Controllers
--------------------

.. list-table::
    :widths: 15 35 20 30
    :header-rows: 1

    * - Status
      - Hardware
      - Device class
      - Notes
    * - 🟢
      - Sensapex pressure controller
      - :doc:`devices/PressureControlDevice` (``SensapexPressureControl``)
      -
    * - 🟢
      - DAQ-controlled pressure regulator and solenoid valves (custom builds)
      - :doc:`devices/PressureControlDevice` (``DAQPressureControl``)
      - Uses an analog output for the regulator and digital outputs for valves.
        Example: Proportion-Air PA2193 voltage-controlled electro-pneumatic pressure control valve, as used on the
        Allen Institute multipatch rigs (`Seeman et al. 2018 <https://doi.org/10.7554/eLife.37349>`_).
    * - 🟢
      - Pressure hardware controlled by MIES
      - :doc:`devices/MIESPatchPipetteDevice`
      -
    * - 🔴
      - Scientifica, Luigs & Neumann, ALA Scientific pressure controllers
      -
      -


Light Sources
-------------

.. list-table::
    :widths: 15 35 20 30
    :header-rows: 1

    * - Status
      - Hardware
      - Device class
      - Notes
    * - 🟢
      - LED drivers or lamps controlled by DAQ digital or analog outputs (e.g. Thorlabs LEDD1B)
      - :doc:`devices/Optomech` (``LEDLightSource``)
      -
    * - 🟢
      - Thorlabs DC4100 4-channel LED driver
      - :doc:`devices/Optomech` (``ThorlabsDC4100``)
      -
    * - 🟡
      - CoolLED pE series
      - :doc:`devices/Optomech` (``CoolLEDLightSource``)
      -
    * - 🟡
      - Zeiss microscope lamps via MTB
      - :doc:`devices/MicroscopeDevice` (``ZeissLamp``)
      -
    * - 🔴
      - Lumencor SPECTRA X
      -
      - A low-level driver exists, but no ACQ4 device class uses it.
    * - 🔴
      - Excelitas X-Cite, Sutter Lambda light sources
      -
      -


Filter Wheels and Turrets
-------------------------

.. list-table::
    :widths: 15 35 20 30
    :header-rows: 1

    * - Status
      - Hardware
      - Device class
      - Notes
    * - 🟢
      - Manual filter cubes / filter sets (metadata only)
      - :doc:`devices/FilterWheelDevice`
      -
    * - 🟢
      - Falcon Optics motorized filter turret
      - :doc:`devices/FilterWheelDevice` (``FalconTurret``)
      -
    * - 🟡
      - Thorlabs FW102C filter wheel
      - :doc:`devices/FilterWheelDevice` (``ThorlabsFilterWheel``)
      -
    * - 🟡
      - Zeiss reflector turret via MTB
      - :doc:`devices/FilterWheelDevice` (``ZeissTurret``)
      -
    * - 🔴
      - Sutter Lambda 10-3 / 10-B, Prior, Ludl filter wheels
      -
      - Some may be usable via μManager with a custom device class.


Laser Scanning and Photostimulation
-----------------------------------

.. list-table::
    :widths: 15 35 20 30
    :header-rows: 1

    * - Status
      - Hardware
      - Device class
      - Notes
    * - 🟢
      - Galvanometric scan mirrors driven by NI DAQ analog outputs
      - :doc:`devices/ScannerDevice`
      -
    * - 🟢
      - Pockels cells, shutters, and photodiodes driven by NI DAQ
      - :doc:`devices/LaserDevice`
      -
    * - 🟢
      - Photomultiplier tubes read by NI DAQ analog inputs
      - :doc:`devices/PMTDevice`
      -
    * - 🟠
      - Coherent Chameleon tunable lasers
      - :doc:`devices/CoherentLaserDevice`
      - Wavelength and power readout; not required for imaging.
    * - 🟠
      - Spectra-Physics Mai Tai tunable lasers
      - :doc:`devices/MaiTaiLaserDevice`
      - Wavelength, pump, and status control; not required for imaging. Ported from an older version of ACQ4 and not yet tested on hardware.
    * - 🔴
      - Spectra-Physics InSight
      -
      -
    * - 🔴
      - Resonant scanners; ScanImage integration
      -
      -


Input Devices
-------------

.. list-table::
    :widths: 15 35 20 30
    :header-rows: 1

    * - Status
      - Hardware
      - Device class
      - Notes
    * - 🟢
      - P.I. Engineering X-keys programmable keyboards (e.g. XKE-128)
      - (``XKeys``)
      - Recommended for multipatch experiments.
    * - 🟢
      - VSDInside Stream Dock
      - (``StreamDock``)
      - Requires the VSD Craft software.
    * - 🟡
      - USB / Bluetooth joysticks and game controllers
      - (``Joystick``)
      -
    * - 🟠
      - Serial mice used for manual stage control
      - :doc:`devices/SerialMouseDevice`
      -


Other Devices
-------------

.. list-table::
    :widths: 15 35 20 30
    :header-rows: 1

    * - Status
      - Hardware
      - Device class
      - Notes
    * - 🟢
      - Ultrasonic pipette cleaning driven by NI DAQ
      - :doc:`devices/SonicatorDevice` (``DAQSonicator``)
      -
    * - 🟢
      - Bath water-level sensor read by NI DAQ
      - (``WaterSensor``)
      -
    * - 🟡
      - ACCES I/O USB-DIO-96 odor delivery valves
      - :doc:`devices/OdorDeliveryDevice` (``AccesOdorDelivery``)
      -
