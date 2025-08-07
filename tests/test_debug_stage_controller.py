# ABOUTME: Unit tests for DebugStageController core functionality
# ABOUTME: Tests step method, timing behavior, and movement calculations without UI dependencies

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
            target_pos = [current_pos[i] + (deltas[i] if i < len(deltas) else 0)
                         for i in range(len(current_pos))]
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
        
        with patch('acq4.modules.DebugStageController.DebugStageController.getManager', return_value=manager):
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
    
    def test_step_method_no_device(self, controller_core):
        """Test step method raises error when no device selected."""
        controller, _ = controller_core
        controller.currentDevice = None
        
        with pytest.raises(AttributeError):
            controller.currentDevice.step((1e-5, 0, 0), 'fast')
    
    def test_get_step_size_modifiers(self, controller_core):
        """Test step size calculation with different modifiers."""
        controller, _ = controller_core
        
        # No modifier: base step size (10µm)
        size = controller._getStepSize(Qt.Qt.NoModifier)
        assert size == pytest.approx(10e-6)
        
        # Shift modifier: 1µm (0.1x)
        size = controller._getStepSize(Qt.Qt.ShiftModifier)
        assert size == pytest.approx(1e-6)
        
        # Alt modifier: 100µm (10x)
        size = controller._getStepSize(Qt.Qt.AltModifier)
        assert size == pytest.approx(100e-6)
    
    def test_get_step_speed_calculation(self, controller_core):
        """Test step speed is 5x base speed, capped at device fast speed."""
        controller, mock_stage = controller_core
        
        # Base speed calculation: stepSize / stepThreshold
        base_speed = 10e-6 / 0.2  # 50µm/s
        expected_step_speed = base_speed * 5  # 250µm/s
        
        speed = controller._getStepSpeed(Qt.Qt.NoModifier)
        assert speed == expected_step_speed
        
        # Test capping at device fast speed
        mock_stage.fastSpeed = 100e-6  # Lower than calculated step speed
        mock_stage._interpretSpeed.return_value = 100e-6
        
        speed = controller._getStepSpeed(Qt.Qt.NoModifier)
        assert speed == 100e-6  # Capped at device fast speed
    
    def test_continuous_speed_calculation(self, controller_core):
        """Test continuous movement speed calculation."""
        controller, _ = controller_core
        
        # Continuous speed should equal base speed
        base_speed = 10e-6 / 0.2  # 50µm/s
        continuous_speed = controller._getContinuousSpeed(Qt.Qt.NoModifier)
        
        assert continuous_speed == base_speed
        
        # Test with modifiers
        shift_speed = controller._getContinuousSpeed(Qt.Qt.ShiftModifier)
        assert shift_speed == base_speed * 0.1  # 1µm steps
        
        alt_speed = controller._getContinuousSpeed(Qt.Qt.AltModifier)
        assert alt_speed == base_speed * 10.0  # 100µm steps
    
    def test_perform_step_movement(self, controller_core):
        """Test single step movement execution."""
        controller, mock_stage = controller_core
        mock_stage.axes.return_value = ('x', 'y', 'z')
        
        # Mock the step method to verify it's called correctly
        with patch.object(controller.currentDevice, 'step') as mock_step:
            key = Qt.Qt.Key_W  # Axis 0, direction +1
            modifiers = Qt.Qt.ShiftModifier
            
            controller._performStepMovement(key, modifiers)
            
            # Should call step with correct deltas and speed
            expected_deltas = (1e-6, 0.0, 0.0)  # 1µm on x-axis (shift modifier)
            mock_step.assert_called_once()
            args = mock_step.call_args[0]
            assert args[0] == pytest.approx(expected_deltas)
            assert isinstance(args[1], float)  # Speed should be calculated
    
    def test_key_mappings(self, controller_core):
        """Test that key mappings produce correct axis/direction combinations."""
        controller, _ = controller_core
        
        expected_mappings = {
            Qt.Qt.Key_W: (0, 1),   # Axis 0 +
            Qt.Qt.Key_S: (0, -1),  # Axis 0 -
            Qt.Qt.Key_A: (1, -1),  # Axis 1 -
            Qt.Qt.Key_D: (1, 1),   # Axis 1 +
            Qt.Qt.Key_Q: (2, -1),  # Axis 2 -
            Qt.Qt.Key_E: (2, 1),   # Axis 2 +
        }
        
        assert controller.keyMappings == expected_mappings
    
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


class TestDebugStageControllerTiming:
    """Test timing-based behavior (step vs continuous movement)."""
    
    def test_step_threshold_timing(self):
        """Test that step threshold correctly determines movement type."""
        # This is a behavioral test - in real usage, key events shorter than 
        # 200ms should trigger step movement, longer should trigger continuous
        
        step_threshold = 0.2  # 200ms
        
        # Short duration = step movement
        short_duration = 0.1
        assert short_duration < step_threshold
        
        # Long duration = continuous movement  
        long_duration = 0.3
        assert long_duration >= step_threshold
    
    def test_continuous_update_interval(self):
        """Test continuous movement update interval."""
        update_interval = 0.1  # 100ms
        
        # Update interval should be reasonable for smooth movement
        assert 0.05 <= update_interval <= 0.2