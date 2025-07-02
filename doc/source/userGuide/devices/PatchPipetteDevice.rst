PatchPipette
============

.. currentmodule:: acq4.devices.PatchPipette

.. autoclass:: PatchPipette
    :members:
    :undoc-members:
    :show-inheritance:

The PatchPipette device represents a single patch pipette, manipulator, and headstage combination with automated patching capabilities. It extends the Pipette device to provide automation and visual feedback on patch status.

Features
--------

* **Automated Patching**: State-based patch automation with configurable parameters
* **Real-time Monitoring**: Input resistance, access resistance, and holding level tracking  
* **Visual Feedback**: Integration with camera systems for visual pipette control
* **Pressure Control**: Automated pressure regulation during patching procedures
* **State Management**: Comprehensive state tracking (bath, approach, seal, break-in, etc.)

Configuration
-------------

The PatchPipette device requires careful configuration of multiple components:

* **parentDevice**: The manipulator/stage device controlling pipette position
* **clampDevice**: The patch clamp amplifier device
* **pressureDevice**: The pressure control device
* **cameraDevice**: Camera for visual feedback (optional)

Example configuration::

    PatchPipette1:
        driver: 'PatchPipette'
        parentDevice: 'Manipulator1'
        clampDevice: 'Clamp1'
        pressureDevice: 'PressureController1'
        cameraDevice: 'Camera1'
        
        # Approach parameters
        approachDistance: 100e-6  # meters
        approachSpeed: 10e-6      # m/s
        
        # Seal parameters
        sealThreshold: 1e9        # ohms
        sealVoltage: -70e-3       # volts
        
        # Break-in parameters
        breakInVoltage: -1.0      # volts
        breakInDuration: 0.1      # seconds

State Management
----------------

The PatchPipette uses a comprehensive state management system with the following states:

**Basic States:**

* **Out**: Pipette is withdrawn from solution and not actively patching
  - Test pulse disabled, atmospheric pressure
  - Finishes current patch record
  
* **Bath**: Pipette is immersed in bath solution
  - Monitors resistance for bath entry detection
  - Auto pipette offset and initial resistance recording
  - Detects pipette breaks or clogs
  - *Parameters*: bathThreshold (50 MΩ), bathPressure (1.5 kPa)

* **Approach**: Pipette is approaching target cell
  - Moves to approach position with auto pipette offset
  - Resets test pulse history
  - *Default next state*: cell detect

**Detection and Attachment:**

* **Cell Detect**: Pipette monitors for cell contact
  - Real-time resistance analysis for obstacle/cell detection
  - Fast and slow detection algorithms
  - *Parameters*: Various thresholds for detection sensitivity

* **Seal**: Pipette is forming gigaseal
  - Monitors resistance increase toward gigaseal formation
  - Pressure and voltage control for seal optimization
  - Success/failure analysis with configurable thresholds
  - *Parameters*: sealThreshold, pressure protocols

* **Cell Attached**: Pipette in cell-attached configuration
  - Monitors for spontaneous break-in or cell loss
  - Optional automatic transition to break-in after delay
  - *Parameters*: autoBreakInDelay, capacitanceThreshold (10 pF), minimumBreakInResistance (1 GΩ)

**Whole Cell Recording:**

* **Break In**: Active membrane rupture for whole-cell access
  - Applies sequence of pressure pulses with increasing strength
  - Monitors capacitance for successful break-in
  - *Parameters*: nPulses, pulseDurations, pulsePressures, capacitanceThreshold

* **Whole Cell**: Successful whole-cell recording configuration
  - Voltage clamp mode with auto bias enabled
  - Continuous monitoring for cell health
  - Records whole-cell start time and position
  - *Default settings*: -70 mV holding, auto bias to -70 mV

* **Reseal**: Attempting to reseal from whole-cell to cell-attached
  - Monitors resistance recovery
  - Stretch and tearing threshold analysis

**Error and Maintenance States:**

* **Broken**: Pipette tip is physically damaged
  - Sets tip broken flag, disables patching
  - Atmospheric pressure, 0 mV holding
  - Finishes current patch record

* **Fouled**: Pipette tip is blocked/contaminated
  - Sets tip clean flag to false
  - Maintains test pulse for resistance monitoring
  - *Next action*: Usually transition to cleaning

* **Blowout**: High-pressure cleaning attempt
  - Retracts from surface and applies high pressure pulse
  - *Parameters*: blowoutPressure (65 kPa), blowoutDuration (2.0 s)

**Specialized States:**

* **Clean**: Automated pipette cleaning protocol
  - Cycles positive/negative pressure in cleaning bath
  - Optional rinse sequence and sonication
  - *Parameters*: cleanSequence, rinseSequence, sonicationProtocol

* **Collect**: Nucleus collection protocol
  - Pressure cycling for nucleus extraction
  - Specialized for single-cell nuclear collection
  - *Parameters*: pressureSequence, approachDistance, sonicationProtocol

* **Move Nucleus to Home**: Returns nucleus to home position after collection

Integration with MultiPatch
---------------------------

For use with the MultiPatch module, the device name must end with a number (e.g., 'PatchPipette1', 'PatchPipette2').

Dependencies
------------

* PatchClamp device (amplifier)
* Stage device (manipulator) 
* PressureControl device (optional but recommended)
* Camera device (optional, for visual feedback)
* Sonicator device (optional, for tip cleaning)