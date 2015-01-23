## PMTController


Controller for Photomultiplier Tubes using an Ardinuino Due

This project is designed to read voltages back from PMT's, possibly detecting a "trip point" when the
anode current exceeds some threshold, and providing an action to shut the tube down (drop the HV) for
protection.
An additional goal is to provide digital control of the voltage to the tube - however this depends on the tube.
Board/software designed to run independently, but communication with host computer via USB port available to query state
and receive information.

The Due provides 6 ADC with 12 bit resolution, reading 0-3.3 V. The Due also provides 2 DACs with 12 bit precision,
putting out 0-3.3 V, and a host of digital i/o lines.

The controller monitors PMT currents via ADC0 and ADC1, and provides control of the plate voltages via DAC0 an DAC1.
Information about tube voltage (command), status, and anode current is displayed on a 16x2 LCD display.

Tubes considered:

PMT0: Hamamatsu H7422P-40: 
  * Control voltage 0.5-0.8 or 0.9V - full range (DAC0), supplied to
M9012 controller unit. 
  * Trip signal (PMT Error) detected on digital line 22. Max anode current 2 uA; built-in detection.
  * Program must detect and provide for reset when requested (requires user intervention).
  * Computer control of fan shutoff if needed.

PMT1: Hamamatsu H10721-20:
  * Control voltage: 0.5-1.1V for full range. 
  * No controller unit.
  * Read current output, compute gain. Max safe output current
is listed at 100 microamps; set trip for 10 microamps. 


## License

The MIT License (MIT)

Copyright (c) 2014 Paul B. Manis, Ph.D.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

