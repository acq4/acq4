.. _userTutorialsTroubleshootingVibration:

Troubleshooting Table Vibration
===============================

1. Run camera at high frame rate--use binning, restricted region, etc. (remember nyquist)
2. Create ROIs at the edges of a dark/light boundary
3. Enable ROI plot, switch to FFT mode

OR if your table already has accelerometer outputs, just make recordings in protocol runner and display in FFT mode.


Common causes of vibration
--------------------------

* table not floating correctly (pressure incorrect, not level, pistons too high or too low, pistons off-center)
* fans (including the camera fan)
* cables pulling against table
* room air currents 
