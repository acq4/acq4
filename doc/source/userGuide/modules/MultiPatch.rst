.. _userModulesMultiPatch:

The MultiPatch Module
=====================

The MultiPatch module provides a unified interface for controlling multiple patch-clamp pipettes simultaneously. It is designed for both single- and multi-electrode patch-clamp experiments, providing access to tools that support the entire patching workflow from positioning pipettes in the bath solution through gigaohm seal formation, break-in, and whole-cell recording.

    .. figure:: images/multipatch.png

The module integrates with :ref:`PatchPipette <userDevicesPatchPipette>` devices to automate many stages of the patching process. 

Overview
--------

The MultiPatch module provides the following key features:

* **Per-pipette controls** for managing the state of each patch pipette -- amplifier settings, pressure control, enabling/disabling, selecting for solo control, locking out of group operations, and manual state overrides.
* **Global workflow actions** that apply to all selected pipettes simultaneously, including automated routines for common patching steps such as coarse/fine search, cell detection, seal formation, and break-in.
* **Real-time test pulse monitoring** with customizable plots showing the latest test pulse waveforms and resistance estimates for each pipette.
* **Configurable patch profiles** that allow specification of parameters for each stage of the patching process. This allows a fulll spectrum from manual control to fully automated patching with user-defined parameters.
* **Event recording** that logs patching events, state transitions, and test pulse data for later review and analysis.

Manual workflow
---------------

1. Attach new pipettes to headstages
2. Under low-magnification, perform coarse search to bring pipettes near the center of view
3. Set tip position for each pipette
4. Send all pipettes home to clear the way for objective switch
5. Under high-magnification, find cells to patch and set a target for each pipette
6. Perform fine search to bring pipettes close together under the objective
7. Set tip positions again if necessary
8. Move to above target position or approach (diagonal) position
9. Manually move each pipette to its cell and seal
10. Perform break-in for each pipette

Automated workflow
------------------

1. Attach new pipettes to headstages
2. Find a cell and set the pipette target
3. Use "new pipette" under high-magnification to automatically locate the new pipette tip
4. Go to "above target" position, then "auto find tip" to update the tip position
5. Use "approach" to initiate automated patch sequence (cycles through approach, contact cell, seal, and break-in states)


Configuration
-------------

The MultiPatch module must appear in the :ref:`modules section <userConfigurationModules>` of the configuration::

    modules:
        MultiPatch:
            module: 'MultiPatch'
            shortcut: 'F7'
            config:
                enableMockPatch: False
                useStacksForSavedTipImages: True
                coarseSearchDistance: 400e-6
                fineSearchDistance: 50e-6
                xkeysDevice: 'XKeys'  # optional keyboard control

The optional configuration keys are:

* **enableMockPatch** When True, adds mock patching controls to each pipette panel. Useful for testing without hardware.
* **useStacksForSavedTipImages** When True (default), z-stacks are collected when saving pipette tip position images.
* **coarseSearchDistance** Distance (in meters) for the Coarse Search move. Defaults to 400 µm.
* **fineSearchDistance** Distance (in meters) used when multiple pipettes perform a Fine Search. Defaults to 50 µm. Ignored when only a single pipette is selected.
* **xkeysDevice** Name of an optional XKeys hardware device for button-based control of the module.


Pipette controls
----------------

    .. figure:: images/multipatchPipette.png

Each row of the MultiPatch window represents one :ref:`PatchPipette <userDevicesPatchPipette>` device. Pipettes are sorted numerically by name and stacked vertically. Each pipette row contains:

* **Active button** (numbered, top-left) - Enables or disables the pipette. Active pipettes participate in all group operations. Inactive pipettes are ignored.
* **Select button** - Selects this pipette for solo control. Only one pipette may be selected at a time. When a pipette is selected, group actions apply only to it.
* **Lock button** - Temporarily locks the pipette out of group operations. This is useful when one pipette has achieved whole-cell access and you want to continue working with the others.
* **State display** - Shows the current state of the patch pipeline (e.g., *bath*, *cell detect*, *seal*, *whole cell*). Click on the state label to open a menu for manually forcing the pipette into any state.
* **Tip / Target buttons** - Click **Tip** to center the camera on the pipette tip. Click **Target** to center the camera on the pipette's current target position.
* **New Pipette button** - Resets the pipette state machine as if a fresh pipette had been mounted.
* **Cancel button** - Halts any ongoing automated state transition for this pipette.
* **Fouled / Broken checkboxes** - Mark the pipette tip as fouled or broken. This informs the state machine and is recorded in the event log.

Clamp controls
~~~~~~~~~~~~~~

For pipettes with an associated clamp amplifier, the following controls appear:

* **VC / IC / I=0 mode buttons** - Switch the clamp amplifier between voltage-clamp, current-clamp, and zero-current modes.
* **Holding potential / current spinner** - Set the holding command for the currently active mode.
* **Auto Offset** - Run the amplifier's automatic pipette offset correction.
* **Auto Pipette Capacitance** - Run the amplifier's automatic fast pipette capacitance compensation.
* **Auto Bridge Balance** - Run the amplifier's automatic bridge balance (current-clamp mode only).
* **Auto Bias** - When enabled, the holding current is automatically adjusted to maintain the membrane potential near the target value (set in the adjacent spinner).
* **Auto Bias VC** - When enabled, the bias voltage is determined from the holding voltage.

Pressure controls
~~~~~~~~~~~~~~~~~

* **Pressure display** - If a pressure device is associated with the pipette, a pressure control widget appears showing and allowing adjustment of the current pressure.
* **Pressure source selector** - Allows selection between regulator, atmosphere, and user pressure sources (if supported by the pressure device).

Test pulse plots
~~~~~~~~~~~~~~~~

Each pipette row contains two scrolling plots that display data extracted from periodic test pulses applied by the clamp amplifier. Plots may be configured to show any of the following data types:

* **Test pulse plot** - Shows the raw current or voltage waveform from the most recent test pulses.
* **Test pulse with analysis** - Shows the test pulse waveform overlaid with the results of an automated analysis (e.g., exponential fit to the charging transient).
* **SS Resistance plot** - Shows the steady-state resistance (in logarithmic scale by default) over the history of test pulses.
* **Peak Resistance plot** - Shows the peak resistance (in logarithmic scale by default) over the history of test pulses.
* **Input Resistance plot** - Shows the input resistance (in logarithmic scale by default) over the history of test pulses.
* **Access Resistance plot** - Shows the access resistance (in logarithmic scale by default) over the history of test pulses.
* **Capacitance plot** - Shows the estimated capacitance over the history of test pulses.


Global controls
---------------

The left section of the MultiPatch window contains controls that apply to all selected (or all active) pipettes simultaneously.

Profile selection
~~~~~~~~~~~~~~~~~

* **Profile selector** - Select a patch profile, which determines the parameters used during each automated patching state. Profiles are defined in the PatchPipette configuration and can be created or edited using the **Edit Profile** button.


Workflow buttons
~~~~~~~~~~~~~~~~

The following buttons execute automated workflow steps on the currently selected pipettes. If no pipette is explicitly selected, the action applies to all active pipettes. Buttons that trigger long-running operations show a progress indicator and may be stopped mid-way.

* **Home** - Move all selected pipettes to their home position outside the bath.
* **Nucleus Home** - Move pipettes home while attempting to retain an extracted nucleus (used after outside-out patch or nucleus extraction experiments).
* **Coarse Search** - Move pipettes to the bath surface and begin a coarse search for the preparation.
* **Fine Search** - Move pipettes close together for fine approach to the target region.
* **Above Target** - Move pipettes to a position directly above their assigned targets, ready to descend.
* **Auto Find Tip** - Use the camera image to automatically locate the pipette tip and update the stored tip offset.
* **Cell Detect** - Enter automated cell detection mode. The pipette will descend slowly while monitoring resistance for a cell contact signature.
* **To Target** - Move pipettes to their assigned target coordinates.
* **Approach** - Move pipettes into approach position just above the cell surface.
* **Seal** - Attempt gigaohm seal formation by applying negative pressure and adjusting holding voltage.
* **Reseal** - Attempt to re-seal a previously lost gigaohm seal.
* **Break In** - Apply brief pressure pulses or voltage steps to rupture the membrane patch and achieve whole-cell access.
* **Clean** - Move the pipette to a cleaning position and run the configured cleaning routine.
* **Collect** - Collect the cell nucleus (for nucleus-extraction experiments).

Speed controls
~~~~~~~~~~~~~~

* **Fast** - When clicked (momentary), the next movement command will use maximum speed.
* **Slow** - When clicked (momentary), the next movement command will use minimum speed.

If neither button is active, the default speed for each operation is used.

Tip and target setting
~~~~~~~~~~~~~~~~~~~~~~

* **Set Tip** - Click to enter tip-setting mode. Subsequently click in the Camera module window to assign the pipette tip position. For multiple selected pipettes, click once per pipette in order.
* **Set Target** - Click to enter target-setting mode. Subsequently click in the Camera module window to assign the target position for each selected pipette.
* **Save Tip Image** - When checked, an image (or z-stack) of the pipette tip is saved to disk each time a tip position is set manually.

Marker visibility
~~~~~~~~~~~~~~~~~

* **Hide Markers** - Toggle visibility of pipette position and target markers in the Camera module.


Recording
~~~~~~~~~

* **Record** - When toggled on, experiment events (state transitions, resistance measurements, surface depth changes, etc.) are written to a ``MultiPatch.log`` file in the current storage directory. Events are stored as a JSON-lines file.
* **Record Test Pulses** - When toggled on, full test pulse waveform data is written to a ``TestPulses.hdf5`` file in the current storage directory.
* **Reset** - Clears the in-memory event history and resets the test pulse history for each clamp device.


XKeys hardware controller
--------------------------

On rigs equipped with an XKeys programmable keypad, the MultiPatch module can be linked to it via the ``xkeysDevice`` configuration option. The XKeys device maps physical keys to the major workflow actions and pipette selection buttons, allowing hands-free control of the patching workflow during experiments.
