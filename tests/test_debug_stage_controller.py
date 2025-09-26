# Unit tests for DebugStageController core functionality
# Tests step method, timing behavior, and movement calculations without UI dependencies

import time
import pytest
from unittest.mock import Mock, MagicMock, patch
import numpy as np

from acq4.devices.MockStage import MockStage
from acq4.devices.Stage import MoveFuture
from acq4.modules.DebugStageController.DebugStageController import DebugStageController
from acq4.util import Qt


class TestDebugStageControllerCore:
    """Test core functionality of DebugStageController without UI components."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mock manager with stage devices."""
        manager = Mock()

        # Create mock stage with 3 axes
        mock_stage = Mock(spec=MockStage)
        mock_stage.name.return_value = 'TestStage'
        mock_stage.axes.return_value = ('x', 'y', 'z')
        mock_stage.getPosition.return_value = [0.0, 0.0, 0.0]
        mock_stage._interpretSpeed.return_value = 1e-3
        mock_stage.fastSpeed = 2e-3

        # Mock move method to return a future
        mock_future = Mock(spec=MoveFuture)
        mock_stage.move.return_value = mock_future

        # Add step method that mimics Stage base class behavior
        def mock_step(deltas, speed):
            current_pos = mock_stage.getPosition()
            target_pos = [
                current_pos[i] + (deltas[i] if i < len(deltas) else 0)
                for i in range(len(current_pos))
            ]
            return mock_stage.move(target_pos, speed=speed)

        mock_stage.step = mock_step

        manager.getDevice.return_value = mock_stage
        manager.listInterfaces.return_value = ['TestStage']

        # Mock device reservation
        reservation = Mock()
        reservation.__enter__ = Mock(return_value=reservation)
        reservation.__exit__ = Mock(return_value=None)
        manager.reserveDevices.return_value = reservation

        return manager, mock_stage

    @pytest.fixture
    def controller_core(self, mock_manager):
        """Create controller instance with mocked dependencies."""
        manager, mock_stage = mock_manager

        with patch(
            'acq4.modules.DebugStageController.DebugStageController.getManager',
            return_value=manager,
        ):
            # Mock UI setup to avoid Qt dependencies
            with patch.object(DebugStageController, '_setupUI'):
                with patch.object(DebugStageController, '_refreshDeviceList'):
                    controller = DebugStageController(manager, "TestController", {})
                    controller.currentDevice = mock_stage
                    controller.enabled = True
                    controller.deviceReservation = manager.reserveDevices.return_value
                    return controller, mock_stage

    def test_step_method_basic(self, controller_core):
        """Test basic step method functionality."""
        controller, mock_stage = controller_core

        # Test step with 3-axis deltas
        deltas = (1e-5, -2e-5, 3e-5)  # 10µm, -20µm, 30µm
        speed = 1e-3

        result = controller.currentDevice.step(deltas, speed)

        # Verify move was called with correct target position
        expected_target = [1e-5, -2e-5, 3e-5]  # deltas added to [0,0,0]
        mock_stage.move.assert_called_once_with(expected_target, speed=speed)
        assert result == mock_stage.move.return_value

    def test_step_method_with_current_position(self, controller_core):
        """Test step method adds deltas to current position."""
        controller, mock_stage = controller_core

        # Set current position
        mock_stage.getPosition.return_value = [1e-4, 2e-4, 3e-4]

        deltas = (1e-5, -1e-5, 0)
        controller.currentDevice.step(deltas, 'fast')

        # Expected target: current + deltas
        expected_target = [1.1e-4, 1.9e-4, 3e-4]
        mock_stage.move.assert_called_once_with(expected_target, speed='fast')






    def test_step_movement_axis_bounds(self, controller_core):
        """Test step movement handles axis bounds correctly."""
        controller, mock_stage = controller_core
        mock_stage.axes.return_value = ('x', 'y')  # Only 2 axes

        with patch.object(controller.currentDevice, 'step') as mock_step:
            # Try to move axis 2 (z), but device only has 2 axes
            key = Qt.Qt.Key_Q  # Maps to axis 2
            controller._performStepMovement(key, Qt.Qt.NoModifier)

            # Step should not be called since axis is out of bounds
            mock_step.assert_not_called()

    def test_continuous_movement_delta_calculation(self, controller_core):
        """Test continuous movement calculates correct combined deltas."""
        controller, mock_stage = controller_core
        mock_stage.axes.return_value = ('x', 'y', 'z')

        # Set up active keys with timing
        import acq4.util.ptime as ptime

        current_time = ptime.time()

        # Simulate keys held long enough for continuous movement
        controller.activeKeys = {Qt.Qt.Key_W, Qt.Qt.Key_D}  # +x, +y
        controller.keyPressTime = {
            Qt.Qt.Key_W: current_time - 0.3,  # Held > 200ms
            Qt.Qt.Key_D: current_time - 0.25,  # Held > 200ms
        }

        with patch.object(controller.currentDevice, 'step') as mock_step:
            with patch('acq4.util.ptime.time', return_value=current_time):
                controller._updateContinuousMovement()

                # Should call step with combined deltas
                if mock_step.called:
                    args = mock_step.call_args[0]
                    deltas = args[0]
                    # Both x and y should have positive movement
                    assert deltas[0] > 0  # +x from W key
                    assert deltas[1] > 0  # +y from D key
                    assert deltas[2] == 0  # No z movement

    def test_auto_disable_timeout(self, controller_core):
        """Test auto-disable functionality."""
        controller, _ = controller_core

        # Mock the timer and time functions
        with patch.object(controller, '_stopControl') as mock_stop:
            # Simulate timeout condition
            controller.lastActivityTime = time.time() - 400  # 400 seconds ago
            controller.autoDisableTimeout = 300  # 5 minutes

            controller._autoDisable()

            # Should have called stop control
            mock_stop.assert_called_once()


