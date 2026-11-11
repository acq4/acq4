.. _userDevicesMIESPatchPipette:

MIES Patch Pipette
==================

The ``MIESPatchPipette`` device lets ACQ4 work alongside `MIES <https://github.com/AllenInstitute/MIES>`_, the multichannel electrophysiology package for Igor Pro. In this setup, MIES owns the acquisition hardware (the DAQ, such as an Instrutech ITC-16 / ITC-18 or NI board; the amplifiers; and the pressure regulators) and ACQ4 controls them through MIES. This lets labs with an existing MIES rig use ACQ4's pipette automation (motion, calibration, cleaning, and autopatch state management) without replacing their acquisition setup.

What ACQ4 can do through MIES
-----------------------------

* **Test pulse**: MIES acquires the test pulse and streams the raw data to ACQ4, where it is analyzed (resistance, capacitance, etc.) just as with a natively controlled amplifier. Enabling or disabling the test pulse from ACQ4 starts or stops it in MIES.
* **Amplifier control**: clamp mode (VC / IC / I=0), holding potential and bias current, auto bias enable and target, auto pipette offset, auto bridge balance, and auto capacitance compensation. Changes made in the MIES GUI are reported back to ACQ4.
* **Pressure control**: pressure and pressure source are read and set through MIES's pressure hardware. Alternatively, ACQ4 can use a separately configured pressure device (see ``pressureDevice`` below).
* **Headstage activation**: activating a pipette in ACQ4 activates the corresponding headstage in MIES.

Limitations
-----------

* **No ACQ4 acquisition protocols.** ACQ4 has no access to the DAQ channels, so the :ref:`Task Runner <userModulesTaskRunner>` and other modules that run DAQ tasks cannot record from or stimulate through MIES headstages. Stimulus sets must be run from MIES, and that data is stored in MIES's NWB files rather than in ACQ4's data storage.
* **Single headstage.** Holding, auto bias, and the auto-compensation functions currently only work for headstage 0.
* **Test pulse is global.** Starting or stopping the test pulse affects all active headstages in MIES, not just the selected pipette.
* **Windows only.** MIES runs in Igor Pro on Windows, and ACQ4 must run on the same machine.

Requirements
------------

* MIES running in Igor Pro on the same computer, with its ZeroMQ interface enabled. ACQ4 connects to ``tcp://localhost:5670`` for requests and ``tcp://localhost:5770`` for published events (test pulse data, amplifier changes).
* A device locked in the MIES DA_Ephys panel before ACQ4 starts. ACQ4 uses the first locked device.
* The ``pyzmq`` and ``pywin32`` Python packages.

Configuration
-------------

Each ``MIESPatchPipette`` corresponds to one MIES headstage. It automatically creates two internal devices:

* ``{name}_clamp``: a patch clamp device that controls the amplifier through MIES.
* ``{name}_pressure``: a pressure control device that uses MIES's pressure hardware. This is not created if ``pressureDevice`` is given.

Configuration options:

* **headstage** (int, required): MIES headstage number for this pipette.
* **pipetteDevice** (str, optional): Name of the :doc:`PipetteDevice` used for tip tracking and motion.
* **pressureDevice** (str, optional): Name of a separately configured :doc:`PressureControlDevice` to use instead of MIES pressure control.
* **sonicatorDevice** (str, optional): Name of a :doc:`SonicatorDevice` used for pipette cleaning.
* All other options of :doc:`PatchPipetteDevice` are supported, except ``clampDevice``, which is always the internal MIES clamp.

Example configuration using MIES-managed pressure::

    PatchPipette1:
        driver: 'MIESPatchPipette'
        headstage: 0
        pipetteDevice: 'Pipette1'
        sonicatorDevice: 'Sonicator1'

Example configuration using a separately configured pressure device::

    Pressure1:
        driver: 'SensapexPressureControl'
        ...

    PatchPipette1:
        driver: 'MIESPatchPipette'
        headstage: 0
        pipetteDevice: 'Pipette1'
        pressureDevice: 'Pressure1'
