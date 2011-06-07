Troubleshoot Electrical Noise
=============================

1. create protocol with clamp device
2. configure daq to run at maximum rate possible (500kHz for MIO-6259)
3. set protocol to loop and start
4. switch plot to FFT mode
5. turn off *and unplug* everything, turn back on one at a time.
6. check for noise first with a model cell on the headstage, wrapped in foil
7. next, remove the foil and check again
8. remove the model cell, replace with an ACSF-loaded pipette, check again
9. place the pipette in the recording chamber with ACSF flowing
10. experiment with different grounding conditions


Common noise sources
--------------------

* some MultiClamps produce a wide band of HF noise that is not attenuated by the bessel filter. The best way around this is to oversample (>300kHz) and then downsample.
* most cameras produce noise. The noise may vary depending on the state of the camera (initialized/not, acquiring/not, frame rate...). Camera noise can be addressed by making sure the scope is grounded, and the firewire connection uses a 'quality' interface. 
* fluid management (pumps, aspirators, drips) is often the cause of random spiky noise
* temperature probes in the recording chamber
* brush motor pumps
* any cables running parallel to the headstage cables
* cell phones. just turn 'em off.
* 60Hz. It's everywhere; use a faraday cage. Sutter MP-285s can be particularly bad; I keep them separated from all the other equipment by ~5 feet.


In general, noise can be reduced significantly by oversampling and then downsampling. See the DAQ interface in the prorocol runner [link]. 
