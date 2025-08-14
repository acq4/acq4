# Debug stage controller module for precise microscope control during debugging
# Provides keyboard-based control of stage/manipulator devices with timing-based step/continuous modes

from __future__ import annotations

from typing import Optional

from acq4 import getManager
from acq4.devices.Stage import Stage
from acq4.modules.Module import Module
from acq4.util import Qt, ptime
from acq4.util.Mutex import Mutex


class DebugStageController(Module):
    """Debug interface for remote-controlling microscope stages and micromanipulators.

    Provides a "game mode" style interface for precise control during debugging sessions.
    Features keyboard shortcuts with modifier-based scaling and timing-based step/continuous modes.
    """

    moduleDisplayName = "Debug Stage Controller"
    moduleCategory = "Debug"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)

        self.manager = getManager()
        self.currentDevice: Optional[Stage] = None
        self.enabled = False
        self.deviceReservation = None
        self.lastActivityTime = ptime.time()
        self.currentMoveFuture = None

        # Key press tracking
        self.keyPressTime = {}
        self.keyModifiers = {}  # Store modifiers for each key when pressed
        self.activeKeys = set()
        self.lock = Mutex(Qt.QMutex.Recursive)

        # Movement parameters
        self.baseStepSize = 10e-6  # 10µm
        self.modifierScales = {
            Qt.Qt.ShiftModifier: 0.1,  # 1µm
            Qt.Qt.AltModifier: 10.0,  # 100µm
        }

        # Key mappings for axes (w/s, a/d, q/e)
        self.keyMappings = {
            Qt.Qt.Key_W: (0, 1),  # Axis 0 +
            Qt.Qt.Key_S: (0, -1),  # Axis 0 -
            Qt.Qt.Key_A: (1, -1),  # Axis 1 -
            Qt.Qt.Key_D: (1, 1),  # Axis 1 +
            Qt.Qt.Key_Q: (2, -1),  # Axis 2 -
            Qt.Qt.Key_E: (2, 1),  # Axis 2 +
        }

        # Movement timing thresholds
        self.stepThreshold = 0.2  # 200ms
        self.continuousUpdateInterval = 0.05  # 50ms for faster continuous movement

        # Auto-disable timer (5 minutes)
        self.autoDisableTimeout = 300.0
        self.autoDisableTimer = Qt.QTimer()
        self.autoDisableTimer.timeout.connect(self._autoDisable)

        # Continuous movement timer
        self.continuousTimer = Qt.QTimer()
        self.continuousTimer.timeout.connect(self._updateContinuousMovement)

        # Timer to check if keys have been held long enough for continuous movement
        self.keyCheckTimer = Qt.QTimer()
        self.keyCheckTimer.timeout.connect(self._updateContinuousMovementState)
        self.keyCheckTimer.start(25)  # Check every 25ms for responsive transitions

        self._setupUI()
        self._refreshDeviceList()

    def _setupUI(self):
        """Set up the user interface."""
        self.ui = Qt.QWidget()
        layout = Qt.QVBoxLayout(self.ui)

        # Device selector
        deviceGroup = Qt.QGroupBox("Device Selection")
        deviceLayout = Qt.QVBoxLayout(deviceGroup)

        self.deviceCombo = Qt.QComboBox()
        self.deviceCombo.currentTextChanged.connect(self._deviceChanged)
        deviceLayout.addWidget(Qt.QLabel("Stage Device:"))
        deviceLayout.addWidget(self.deviceCombo)

        # Enable/disable toggle
        self.enableButton = Qt.QPushButton("Enable Control")
        self.enableButton.setCheckable(True)
        self.enableButton.toggled.connect(self._toggleControl)
        deviceLayout.addWidget(self.enableButton)

        layout.addWidget(deviceGroup)

        # Control hints
        hintsGroup = Qt.QGroupBox("Control Hints")
        hintsLayout = Qt.QVBoxLayout(hintsGroup)

        self.hintsLabel = Qt.QLabel()
        self.hintsLabel.setFont(Qt.QFont("monospace"))
        self.hintsLabel.setWordWrap(True)
        hintsLayout.addWidget(self.hintsLabel)

        layout.addWidget(hintsGroup)

        # Status
        statusGroup = Qt.QGroupBox("Status")
        statusLayout = Qt.QVBoxLayout(statusGroup)

        self.statusLabel = Qt.QLabel("Disabled")
        statusLayout.addWidget(self.statusLabel)

        layout.addWidget(statusGroup)

        # Set the widget as our window
        self.ui.show()

        self._updateHints()

    def _refreshDeviceList(self):
        """Refresh the list of available stage devices."""
        self.deviceCombo.clear()
        self.deviceCombo.addItem("Select device...")

        for deviceName in self.manager.listInterfaces('stage'):
            device = self.manager.getDevice(deviceName)
            if isinstance(device, Stage):
                self.deviceCombo.addItem(deviceName)

    def _deviceChanged(self, deviceName: str):
        """Handle device selection change."""
        if deviceName == "Select device...":
            self.currentDevice = None
        else:
            try:
                self.currentDevice = self.manager.getDevice(deviceName)
                if not isinstance(self.currentDevice, Stage):
                    self.currentDevice = None
            except Exception:
                self.currentDevice = None

        self._updateHints()

        # If currently enabled, restart with new device
        if self.enabled:
            self._stopControl()
            if self.currentDevice is not None:
                self._startControl()

    def _updateHints(self):
        """Update the control hints display."""
        if self.currentDevice is None:
            self.hintsLabel.setText("No device selected")
            return

        axes = self.currentDevice.axes()
        hints = []

        hints.append("Key Mappings:")
        if len(axes) > 0:
            hints.append(f"  w/s: {axes[0]} +/-")
        if len(axes) > 1:
            hints.append(f"  a/d: {axes[1]} -/+")
        if len(axes) > 2:
            hints.append(f"  q/e: {axes[2]} -/+")

        hints.append("")
        hints.append("Modifiers:")
        hints.append("  No modifier: 10µm steps/speeds")
        hints.append("  Shift: 1µm steps/speeds")
        hints.append("  Alt: 100µm steps/speeds")

        hints.append("")
        hints.append("Movement:")
        hints.append("  Quick press (<200ms): Single step at 5x speed")
        hints.append("  Hold (≥200ms): Continuous movement")

        self.hintsLabel.setText("\n".join(hints))

    def _toggleControl(self, enabled: bool):
        """Toggle the control mode on/off."""
        if enabled:
            if self.currentDevice is None:
                self.enableButton.setChecked(False)
                Qt.QMessageBox.warning(self.ui, "Error", "Please select a device first")
                return
            self._startControl()
        else:
            self._stopControl()

    def _startControl(self):
        """Start the control mode."""
        if self.currentDevice is None:
            return

        # Reserve the device
        try:
            self.deviceReservation = self.manager.reserveDevices([self.currentDevice])
            self.deviceReservation.__enter__()
        except Exception as e:
            Qt.QMessageBox.warning(self.ui, "Error", f"Could not reserve device: {e}")
            self.enableButton.setChecked(False)
            return

        # Install global event filter
        Qt.QCoreApplication.instance().installEventFilter(self)

        # Start auto-disable timer
        self.autoDisableTimer.start(int(self.autoDisableTimeout * 1000))

        # Start key check timer
        self.keyCheckTimer.start(25)

        self.enabled = True
        self.lastActivityTime = ptime.time()
        self.enableButton.setText("Disable Control")
        self.statusLabel.setText(f"Enabled - {self.currentDevice.name()}")

    def _stopControl(self):
        """Stop the control mode."""
        # Remove event filter
        try:
            Qt.QCoreApplication.instance().removeEventFilter(self)
        except Exception:
            pass

        # Stop timers
        self.autoDisableTimer.stop()
        self.continuousTimer.stop()
        self.keyCheckTimer.stop()

        # Release device reservation
        if self.deviceReservation is not None:
            try:
                self.deviceReservation.__exit__(None, None, None)
            except Exception:
                pass
            self.deviceReservation = None

        # Clear state
        self.enabled = False
        self.activeKeys.clear()
        self.keyPressTime.clear()
        self.keyModifiers.clear()
        self.currentMoveFuture = None

        self.enableButton.setChecked(False)
        self.enableButton.setText("Enable Control")
        self.statusLabel.setText("Disabled")

    def _autoDisable(self):
        """Auto-disable after timeout."""
        timeSinceActivity = ptime.time() - self.lastActivityTime
        if timeSinceActivity >= self.autoDisableTimeout:
            self._stopControl()
        else:
            # Restart timer for remaining time
            remaining = self.autoDisableTimeout - timeSinceActivity
            self.autoDisableTimer.start(int(remaining * 1000))

    def eventFilter(self, obj, event) -> bool:
        """Global event filter for key press/release events."""
        if not self.enabled or self.currentDevice is None:
            return False

        if event.type() in (Qt.QEvent.KeyPress, Qt.QEvent.KeyRelease):
            return self._handleKeyEvent(event)

        return False

    def _handleKeyEvent(self, event) -> bool:
        """Handle key press/release events."""
        if event.isAutoRepeat():
            return False

        key = event.key()
        if key not in self.keyMappings:
            return False

        currentTime = ptime.time()
        self.lastActivityTime = currentTime

        with self.lock:
            if event.type() == Qt.QEvent.KeyPress:
                if key not in self.activeKeys:
                    self.activeKeys.add(key)
                    self.keyPressTime[key] = currentTime
                    self.keyModifiers[key] = event.modifiers()  # Capture modifiers when pressed

            elif event.type() == Qt.QEvent.KeyRelease:
                if key in self.activeKeys:
                    self.activeKeys.remove(key)
                    pressTime = self.keyPressTime.get(key, currentTime)
                    holdDuration = currentTime - pressTime

                    # Handle step vs continuous movement
                    if holdDuration < self.stepThreshold:
                        # Use stored modifiers from when key was pressed
                        modifiers = self.keyModifiers.get(key, Qt.Qt.NoModifier)
                        self._performStepMovement(key, modifiers)

                    # Clean up stored data
                    if key in self.keyPressTime:
                        del self.keyPressTime[key]
                    if key in self.keyModifiers:
                        del self.keyModifiers[key]

            # Update continuous movement
            self._updateContinuousMovementState()

        return True

    def _updateContinuousMovementState(self):
        """Update the continuous movement timer based on active keys."""
        if self.activeKeys:
            # Check if any key has been held long enough for continuous movement
            currentTime = ptime.time()
            continuousKeys = False
            for key in self.activeKeys:
                pressTime = self.keyPressTime.get(key, currentTime)
                if currentTime - pressTime >= self.stepThreshold:
                    continuousKeys = True
                    break

            if continuousKeys and not self.continuousTimer.isActive():
                self.continuousTimer.start(int(self.continuousUpdateInterval * 1000))
            elif not continuousKeys and self.continuousTimer.isActive():
                self.continuousTimer.stop()
        else:
            self.continuousTimer.stop()

    def _performStepMovement(self, key: int, modifiers):
        """Perform a single step movement."""
        if self.currentDevice is None:
            return

        # Check if previous movement is still in progress
        if self.currentMoveFuture is not None and not self.currentMoveFuture.isDone():
            return  # Don't start new movement while one is in progress

        axis, direction = self.keyMappings[key]
        stepSize = self._getStepSize(modifiers)
        speed = self._getStepSpeed(modifiers)

        # Create delta array
        axes = self.currentDevice.axes()
        if axis >= len(axes):
            return

        deltas = [0.0] * len(axes)
        deltas[axis] = direction * stepSize

        self.currentMoveFuture = self.currentDevice.step(tuple(deltas), speed)

    def _updateContinuousMovement(self):
        """Update continuous movement based on currently active keys."""
        if not self.activeKeys or self.currentDevice is None:
            return

        # Check if previous movement is still in progress
        if self.currentMoveFuture is not None and not self.currentMoveFuture.isDone():
            return  # Don't start new movement while one is in progress

        currentTime = ptime.time()
        axes = self.currentDevice.axes()
        deltas = [0.0] * len(axes)

        # Calculate combined deltas from all active keys
        # For continuous movement, we need to determine which modifier to use
        # We'll use the most recent key's modifiers if multiple keys are active
        activeModifiers = Qt.Qt.NoModifier
        mostRecentTime = 0

        for key in self.activeKeys:
            pressTime = self.keyPressTime.get(key, currentTime)
            holdDuration = currentTime - pressTime

            # Only include keys held long enough for continuous movement
            if holdDuration >= self.stepThreshold:
                axis, direction = self.keyMappings[key]
                if axis < len(axes):
                    # Use modifiers from when this key was pressed
                    keyModifiers = self.keyModifiers.get(key, Qt.Qt.NoModifier)

                    # If this key was pressed more recently, use its modifiers
                    if pressTime > mostRecentTime:
                        mostRecentTime = pressTime
                        activeModifiers = keyModifiers

                    stepSize = self._getStepSize(keyModifiers)
                    # Use update interval for continuous speed
                    deltas[axis] += (
                        direction * stepSize * (self.continuousUpdateInterval / self.stepThreshold)
                    )

        # Perform movement if any deltas are non-zero
        if any(d != 0 for d in deltas):
            speed = self._getContinuousSpeed(activeModifiers)
            self.currentMoveFuture = self.currentDevice.step(tuple(deltas), speed)

    def _getStepSize(self, modifiers) -> float:
        """Get step size based on modifiers."""
        stepSize = self.baseStepSize

        if modifiers & Qt.Qt.ShiftModifier:
            stepSize *= self.modifierScales[Qt.Qt.ShiftModifier]
        elif modifiers & Qt.Qt.AltModifier:
            stepSize *= self.modifierScales[Qt.Qt.AltModifier]

        return stepSize

    def _getStepSpeed(self, modifiers):
        """Get step speed (5x base speed, capped at device fast speed)."""
        baseSpeed = self._getBaseSpeed(modifiers)
        stepSpeed = baseSpeed * 5

        # Cap at device fast speed
        if self.currentDevice:
            fastSpeed = self.currentDevice._interpretSpeed("fast")
            stepSpeed = min(stepSpeed, fastSpeed)

        return stepSpeed

    def _getContinuousSpeed(self, modifiers) -> float:
        """Get continuous movement speed."""
        return self._getBaseSpeed(modifiers)

    def _getBaseSpeed(self, modifiers) -> float:
        """Get base movement speed based on modifiers."""
        baseSpeed = self.baseStepSize / self.stepThreshold  # Speed for base step size

        if modifiers & Qt.Qt.ShiftModifier:
            baseSpeed *= self.modifierScales[Qt.Qt.ShiftModifier]
        elif modifiers & Qt.Qt.AltModifier:
            baseSpeed *= self.modifierScales[Qt.Qt.AltModifier]

        return baseSpeed

    def quit(self):
        """Clean up when module is closed."""
        self._stopControl()
        self.keyCheckTimer.stop()
        Module.quit(self)


def createWindow(manager, config):
    """Factory function for module creation."""
    return DebugStageController(manager, "DebugStageController", config)
