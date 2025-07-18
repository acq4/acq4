# ABOUTME: A module for calibrating latency between light source activation and camera detection
# ABOUTME: Provides UI for selecting camera/light source and running calibration measurements

from __future__ import annotations

import time
import numpy as np
import pyqtgraph as pg
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.InterfaceCombo import InterfaceCombo
from acq4.util.future import future_wrap


class CameraCalibrator(Module):
    """Module for calibrating latency between light source activation and camera detection.
    
    This module provides a UI for selecting a camera and light source, then running
    a calibration sequence where the camera records while the light source is turned
    on at a known time. The resulting video is displayed with a timeline marker
    showing when the light activation was requested.
    """
    
    moduleDisplayName = "Camera Latency Calibrator"
    moduleCategory = "Utilities"
    
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        
        self.win = Qt.QMainWindow()
        self.win.setWindowTitle('Camera Latency Calibrator')
        
        # Create main widget and layout
        self.mainWidget = Qt.QWidget()
        self.win.setCentralWidget(self.mainWidget)
        self.layout = Qt.QVBoxLayout(self.mainWidget)
        
        # Create control panel
        self.controlPanel = Qt.QWidget()
        self.controlLayout = Qt.QHBoxLayout(self.controlPanel)
        self.layout.addWidget(self.controlPanel)
        
        # Camera selection
        self.controlLayout.addWidget(Qt.QLabel("Camera:"))
        self.cameraCombo = InterfaceCombo(types=['camera'])
        self.controlLayout.addWidget(self.cameraCombo)
        
        # Light source selection
        self.controlLayout.addWidget(Qt.QLabel("Light Source:"))
        self.lightSourceCombo = InterfaceCombo(types=['lightSource'])
        self.controlLayout.addWidget(self.lightSourceCombo)
        
        # Calibrate button
        self.calibrateBtn = Qt.QPushButton("Calibrate Latency")
        self.calibrateBtn.clicked.connect(self.startCalibration)
        self.controlLayout.addWidget(self.calibrateBtn)
        
        # Add stretch to push controls to the left
        self.controlLayout.addStretch()
        
        # Create image view for displaying acquired frames
        self.imageView = pg.ImageView()
        self.layout.addWidget(self.imageView)
        
        # Timeline marker for light activation
        self.activationMarker = None
        
        self.win.show()
        
    def startCalibration(self):
        """Start the latency calibration sequence in a thread."""
        
        # Get selected devices
        camera = self.cameraCombo.getSelectedObj()
        lightSourceInterface = self.lightSourceCombo.currentText()
        
        if camera is None:
            Qt.QMessageBox.warning(self.win, "Error", "Please select a camera.")
            return
            
        if not lightSourceInterface:
            Qt.QMessageBox.warning(self.win, "Error", "Please select a light source.")
            return
        
        # Parse the light source interface name to get device and source
        if ':' not in lightSourceInterface:
            Qt.QMessageBox.warning(self.win, "Error", "Invalid light source selection.")
            return
            
        deviceName, sourceName = lightSourceInterface.split(':', 1)
        lightSource = self.manager.getDevice(deviceName)
        
        if lightSource is None:
            Qt.QMessageBox.warning(self.win, "Error", f"Could not find light source device: {deviceName}")
            return
            
        # Disable the calibrate button during acquisition
        self.calibrateBtn.setEnabled(False)
        self.calibrateBtn.setText("Calibrating...")
        
        # Start the threaded calibration
        future = self._runCalibration(camera, lightSource, sourceName)
        future.sigFinished.connect(self._calibrationFinished)
        
    @future_wrap
    def _runCalibration(self, camera, lightSource, sourceName, _future=None):
        """Run the calibration sequence in a thread."""
        
        try:
            with camera.ensureRunning():
                # Start frame acquisition (no specific number - will run until stopped)
                frameAcquisition = camera.acquireFrames()
                
                # Wait 1 second, then note timestamp and turn on light
                time.sleep(1.0)
                activationTime = time.time()
                lightSource.setSourceActive(sourceName, True)
                
                # Wait another second, then turn off light and stop acquisition
                time.sleep(1.0)
                lightSource.setSourceActive(sourceName, False)
                
                # Stop frame acquisition
                frameAcquisition.stop()
                
                # Get the acquired frames
                frames = frameAcquisition.getResult()
            
            return {'frames': frames, 'activationTime': activationTime}
            
        except Exception as e:
            # Make sure to clean up on error
            try:
                lightSource.setSourceActive(sourceName, False)
            except:
                pass
            raise e
            
    def _calibrationFinished(self, future):
        """Handle completion of calibration."""
        
        # Re-enable the calibrate button
        self.calibrateBtn.setEnabled(True)
        self.calibrateBtn.setText("Calibrate Latency")
        
        try:
            result = future.getResult()
            self._displayFrames(result['frames'], result['activationTime'])
            
        except Exception as e:
            Qt.QMessageBox.critical(self.win, "Error", f"Calibration failed: {str(e)}")
                
    def _displayFrames(self, frames, activationTime):
        """Display the acquired frames in the image view with activation marker."""
        
        if not frames:
            Qt.QMessageBox.warning(self.win, "Warning", "No frames were acquired.")
            return
            
        # Extract frame data and timestamps
        frameData = []
        timestamps = []
        
        for frame in frames:
            frameData.append(frame.data())
            timestamps.append(frame.info()['time'])
            
        # Convert to numpy array
        frameArray = np.array(frameData)
        timestamps = np.array(timestamps)
        
        # Find the earliest timestamp to use as reference
        startTime = timestamps[0]
        relativeActivationTime = activationTime - startTime
        
        # Set the image data with time axis
        self.imageView.setImage(frameArray, xvals=timestamps - startTime)
        
        # Add activation marker to timeline
        if self.activationMarker is not None:
            self.imageView.view.removeItem(self.activationMarker)
            
        self.activationMarker = pg.InfiniteLine(
            pos=relativeActivationTime,
            angle=90,
            pen=pg.mkPen('r', width=2),
            movable=False
        )
        
        # Add marker to the timeline plot (ROI plot)
        self.imageView.ui.roiPlot.addItem(self.activationMarker)