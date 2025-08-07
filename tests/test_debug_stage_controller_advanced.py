# ABOUTME: Advanced tests for DebugStageController including non-orthogonal axes and complex scenarios
# ABOUTME: Tests multi-key combinations, edge cases, and specialized stage configurations

import pytest
from unittest.mock import Mock, patch
import numpy as np

from acq4.devices.MockStage import MockStage
from acq4.modules.DebugStageController.DebugStageController import DebugStageController
from acq4.util import Qt


class TestDebugStageControllerAdvanced:
    """Advanced tests for complex stage scenarios."""
    
    @pytest.fixture
    def non_orthogonal_stage(self):
        """Create a mock stage with non-orthogonal axes."""
        mock_stage = Mock(spec=MockStage)
        mock_stage.name.return_value = 'NonOrthogonalStage'
        mock_stage.axes.return_value = ('u', 'v', 'w')  # Non-standard axis names
        mock_stage.getPosition.return_value = [0.0, 0.0, 0.0]
        mock_stage._interpretSpeed.return_value = 1e-3
        mock_stage.fastSpeed = 2e-3
        
        mock_future = Mock()
        mock_stage.move.return_value = mock_future
        
        return mock_stage
    
    @pytest.fixture 
    def two_axis_stage(self):
        """Create a mock stage with only 2 axes."""
        mock_stage = Mock(spec=MockStage)
        mock_stage.name.return_value = 'TwoAxisStage'
        mock_stage.axes.return_value = ('x', 'y')  # Only 2 axes
        mock_stage.getPosition.return_value = [0.0, 0.0]
        mock_stage._interpretSpeed.return_value = 1e-3
        mock_stage.fastSpeed = 2e-3
        
        mock_future = Mock()
        mock_stage.move.return_value = mock_future
        
        return mock_stage
    
    def test_non_orthogonal_axes_step(self, non_orthogonal_stage):
        """Test step movement works with non-orthogonal axis names."""
        manager = Mock()
        manager.getDevice.return_value = non_orthogonal_stage
        manager.reserveDevices.return_value = Mock()
        
        with patch('acq4.modules.DebugStageController.DebugStageController.getManager', return_value=manager):
            with patch.object(DebugStageController, '_setupUI'):
                with patch.object(DebugStageController, '_refreshDeviceList'):
                    controller = DebugStageController(manager, "TestController", {})
                    controller.currentDevice = non_orthogonal_stage
                    
                    # Step on first axis (u)
                    deltas = (1e-5, 0.0, 0.0)
                    
                    # Add step method to mock
                    def mock_step(deltas, speed):
                        current_pos = non_orthogonal_stage.getPosition()
                        target_pos = [current_pos[i] + (deltas[i] if i < len(deltas) else 0)
                                     for i in range(len(current_pos))]
                        return non_orthogonal_stage.move(target_pos, speed=speed)
                    non_orthogonal_stage.step = mock_step
                    
                    controller.currentDevice.step(deltas, 'fast')
                    
                    # Should still call move with correct target
                    expected_target = [1e-5, 0.0, 0.0]
                    non_orthogonal_stage.move.assert_called_once_with(expected_target, speed='fast')
    
    def test_two_axis_stage_handling(self, two_axis_stage):
        """Test controller works with 2-axis stages."""
        manager = Mock()
        manager.getDevice.return_value = two_axis_stage
        manager.reserveDevices.return_value = Mock()
        
        with patch('acq4.modules.DebugStageController.DebugStageController.getManager', return_value=manager):
            with patch.object(DebugStageController, '_setupUI'):
                with patch.object(DebugStageController, '_refreshDeviceList'):
                    controller = DebugStageController(manager, "TestController", {})
                    controller.currentDevice = two_axis_stage
                    
                    # Step on both available axes
                    deltas = (1e-5, 2e-5)
                    
                    # Add step method to mock
                    def mock_step(deltas, speed):
                        current_pos = two_axis_stage.getPosition()
                        target_pos = [current_pos[i] + (deltas[i] if i < len(deltas) else 0)
                                     for i in range(len(current_pos))]
                        return two_axis_stage.move(target_pos, speed=speed)
                    two_axis_stage.step = mock_step
                    
                    controller.currentDevice.step(deltas, 'slow')
                    
                    # Should call move with 2-element target
                    expected_target = [1e-5, 2e-5]
                    two_axis_stage.move.assert_called_once_with(expected_target, speed='slow')
    
    def test_z_axis_key_with_two_axis_stage(self, two_axis_stage):
        """Test that Z-axis keys are ignored on 2-axis stages."""
        manager = Mock()
        manager.getDevice.return_value = two_axis_stage
        manager.reserveDevices.return_value = Mock()
        
        with patch('acq4.modules.DebugStageController.DebugStageController.getManager', return_value=manager):
            with patch.object(DebugStageController, '_setupUI'):
                with patch.object(DebugStageController, '_refreshDeviceList'):
                    controller = DebugStageController(manager, "TestController", {})
                    controller.currentDevice = two_axis_stage
                    
                    with patch.object(controller.currentDevice, 'step') as mock_step:
                        # Try to use Q key (axis 2, z) on 2-axis stage
                        controller._performStepMovement(Qt.Qt.Key_Q, Qt.Qt.NoModifier)
                        
                        # Step should not be called since axis 2 doesn't exist
                        mock_step.assert_not_called()
    
    def test_multi_key_combination_deltas(self):
        """Test that multiple simultaneous keys combine deltas correctly."""
        # Create controller with 3-axis stage
        mock_stage = Mock(spec=MockStage)
        mock_stage.name.return_value = 'TestStage'
        mock_stage.axes.return_value = ('x', 'y', 'z')
        mock_stage.getPosition.return_value = [0.0, 0.0, 0.0]
        mock_stage._interpretSpeed.return_value = 1e-3
        mock_stage.fastSpeed = 2e-3
        mock_stage.move.return_value = Mock()
        
        manager = Mock()
        manager.getDevice.return_value = mock_stage
        manager.reserveDevices.return_value = Mock()
        
        with patch('acq4.modules.DebugStageController.DebugStageController.getManager', return_value=manager):
            with patch.object(DebugStageController, '_setupUI'):
                with patch.object(DebugStageController, '_refreshDeviceList'):
                    controller = DebugStageController(manager, "TestController", {})
                    controller.currentDevice = mock_stage
                    
                    # Simulate continuous movement with multiple keys
                    import acq4.util.ptime as ptime
                    current_time = ptime.time()
                    
                    # W (+x), D (+y), E (+z) all held
                    controller.activeKeys = {Qt.Qt.Key_W, Qt.Qt.Key_D, Qt.Qt.Key_E}
                    controller.keyPressTime = {
                        Qt.Qt.Key_W: current_time - 0.3,  # +x
                        Qt.Qt.Key_D: current_time - 0.3,  # +y  
                        Qt.Qt.Key_E: current_time - 0.3,  # +z
                    }
                    
                    with patch.object(controller.currentDevice, 'step') as mock_step:
                        with patch('acq4.util.ptime.time', return_value=current_time):
                            controller._updateContinuousMovement()
                            
                            if mock_step.called:
                                deltas = mock_step.call_args[0][0]
                                # All three axes should have positive movement
                                assert deltas[0] > 0  # +x
                                assert deltas[1] > 0  # +y 
                                assert deltas[2] > 0  # +z
    
    def test_opposing_key_cancellation(self):
        """Test that opposing keys (e.g., W and S) cancel each other out."""
        mock_stage = Mock(spec=MockStage)
        mock_stage.name.return_value = 'TestStage'
        mock_stage.axes.return_value = ('x', 'y', 'z')
        mock_stage.getPosition.return_value = [0.0, 0.0, 0.0]
        mock_stage._interpretSpeed.return_value = 1e-3
        mock_stage.fastSpeed = 2e-3
        mock_stage.move.return_value = Mock()
        
        manager = Mock()
        manager.getDevice.return_value = mock_stage
        manager.reserveDevices.return_value = Mock()
        
        with patch('acq4.modules.DebugStageController.DebugStageController.getManager', return_value=manager):
            with patch.object(DebugStageController, '_setupUI'):
                with patch.object(DebugStageController, '_refreshDeviceList'):
                    controller = DebugStageController(manager, "TestController", {})
                    controller.currentDevice = mock_stage
                    
                    import acq4.util.ptime as ptime
                    current_time = ptime.time()
                    
                    # W (+x) and S (-x) held simultaneously
                    controller.activeKeys = {Qt.Qt.Key_W, Qt.Qt.Key_S}
                    controller.keyPressTime = {
                        Qt.Qt.Key_W: current_time - 0.3,  # +x
                        Qt.Qt.Key_S: current_time - 0.3,  # -x
                    }
                    
                    with patch.object(controller.currentDevice, 'step') as mock_step:
                        with patch('acq4.util.ptime.time', return_value=current_time):
                            controller._updateContinuousMovement()
                            
                            if mock_step.called:
                                deltas = mock_step.call_args[0][0]
                                # X-axis movement should be near zero (cancelled)
                                assert abs(deltas[0]) < 1e-10
                                # Other axes should be zero
                                assert deltas[1] == 0
                                assert deltas[2] == 0
    
    def test_step_with_partial_deltas(self):
        """Test step method with fewer deltas than available axes."""
        mock_stage = Mock(spec=MockStage)
        mock_stage.name.return_value = 'TestStage'
        mock_stage.axes.return_value = ('x', 'y', 'z')
        mock_stage.getPosition.return_value = [1e-4, 2e-4, 3e-4]
        mock_stage.move.return_value = Mock()
        
        manager = Mock()
        manager.reserveDevices.return_value = Mock()
        
        with patch('acq4.modules.DebugStageController.DebugStageController.getManager', return_value=manager):
            with patch.object(DebugStageController, '_setupUI'):
                with patch.object(DebugStageController, '_refreshDeviceList'):
                    controller = DebugStageController(manager, "TestController", {})
                    controller.currentDevice = mock_stage
                    
                    # Provide only 2 deltas for 3-axis stage
                    deltas = (1e-5, 2e-5)  # Missing z delta
                    
                    # Add step method to mock
                    def mock_step(deltas, speed):
                        current_pos = mock_stage.getPosition()
                        target_pos = [current_pos[i] + (deltas[i] if i < len(deltas) else 0)
                                     for i in range(len(current_pos))]
                        return mock_stage.move(target_pos, speed=speed)
                    mock_stage.step = mock_step
                    
                    controller.currentDevice.step(deltas, 'fast')
                    
                    # Should fill in missing axes with current position
                    expected_target = [1.1e-4, 2.2e-4, 3e-4]  # z unchanged
                    mock_stage.move.assert_called_once_with(expected_target, speed='fast')
    
    def test_device_error_handling(self):
        """Test error handling when device operations fail."""
        mock_stage = Mock(spec=MockStage)
        mock_stage.name.return_value = 'FailingStage'
        mock_stage.axes.return_value = ('x', 'y', 'z')
        mock_stage.getPosition.return_value = [0.0, 0.0, 0.0]
        
        # Make move method raise an exception
        mock_stage.move.side_effect = RuntimeError("Stage communication failed")
        
        manager = Mock()
        manager.reserveDevices.return_value = Mock()
        
        with patch('acq4.modules.DebugStageController.DebugStageController.getManager', return_value=manager):
            with patch.object(DebugStageController, '_setupUI'):
                with patch.object(DebugStageController, '_refreshDeviceList'):
                    controller = DebugStageController(manager, "TestController", {})
                    controller.currentDevice = mock_stage
                    
                    # Add step method to mock
                    def mock_step(deltas, speed):
                        current_pos = mock_stage.getPosition()
                        target_pos = [current_pos[i] + (deltas[i] if i < len(deltas) else 0)
                                     for i in range(len(current_pos))]
                        return mock_stage.move(target_pos, speed=speed)
                    mock_stage.step = mock_step
                    
                    # Step should raise the underlying error
                    with pytest.raises(RuntimeError, match="Stage communication failed"):
                        controller.currentDevice.step((1e-5, 0, 0), 'fast')
    
    def test_large_step_sizes(self):
        """Test behavior with very large step sizes."""
        mock_stage = Mock(spec=MockStage)
        mock_stage.name.return_value = 'TestStage'
        mock_stage.axes.return_value = ('x', 'y', 'z')
        mock_stage.getPosition.return_value = [0.0, 0.0, 0.0]
        mock_stage.move.return_value = Mock()
        
        manager = Mock()
        manager.reserveDevices.return_value = Mock()
        
        with patch('acq4.modules.DebugStageController.DebugStageController.getManager', return_value=manager):
            with patch.object(DebugStageController, '_setupUI'):
                with patch.object(DebugStageController, '_refreshDeviceList'):
                    controller = DebugStageController(manager, "TestController", {})
                    controller.currentDevice = mock_stage
                    
                    # Very large step (1mm)
                    large_delta = 1e-3
                    deltas = (large_delta, 0, 0)
                    
                    # Add step method to mock
                    def mock_step(deltas, speed):
                        current_pos = mock_stage.getPosition()
                        target_pos = [current_pos[i] + (deltas[i] if i < len(deltas) else 0)
                                     for i in range(len(current_pos))]
                        return mock_stage.move(target_pos, speed=speed)
                    mock_stage.step = mock_step
                    
                    controller.currentDevice.step(deltas, 'fast')
                    
                    # Should still work (stage limits should be enforced elsewhere)
                    expected_target = [large_delta, 0.0, 0.0]
                    mock_stage.move.assert_called_once_with(expected_target, speed='fast')
    
    def test_zero_deltas(self):
        """Test step method with all zero deltas."""
        mock_stage = Mock(spec=MockStage)
        mock_stage.name.return_value = 'TestStage'
        mock_stage.axes.return_value = ('x', 'y', 'z')
        mock_stage.getPosition.return_value = [1e-4, 2e-4, 3e-4]
        mock_stage.move.return_value = Mock()
        
        manager = Mock()
        manager.reserveDevices.return_value = Mock()
        
        with patch('acq4.modules.DebugStageController.DebugStageController.getManager', return_value=manager):
            with patch.object(DebugStageController, '_setupUI'):
                with patch.object(DebugStageController, '_refreshDeviceList'):
                    controller = DebugStageController(manager, "TestController", {})
                    controller.currentDevice = mock_stage
                    
                    # All zero deltas
                    deltas = (0, 0, 0)
                    
                    # Add step method to mock
                    def mock_step(deltas, speed):
                        current_pos = mock_stage.getPosition()
                        target_pos = [current_pos[i] + (deltas[i] if i < len(deltas) else 0)
                                     for i in range(len(current_pos))]
                        return mock_stage.move(target_pos, speed=speed)
                    mock_stage.step = mock_step
                    
                    controller.currentDevice.step(deltas, 'fast')
                    
                    # Should move to current position (no-op move)
                    expected_target = [1e-4, 2e-4, 3e-4]
                    mock_stage.move.assert_called_once_with(expected_target, speed='fast')