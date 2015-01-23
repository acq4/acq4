/*
PMT Monitor/controller with Arduino Due.
1. Read and display PMT currents (peak or mean) on analog ports (ADC0, ADC1)
2. Provide and display command voltages to the PMT by reding ADC10 and ADC11.
  -- The DACs on the Due put out 0.55 (1/6 of 3.3V) to about 2.6 (5/6 of 3.3V). This
  means that the outputs have to be level shifted to reach 0, which requires at least
  a dual op-amp for the two channels, and a handful of resistors.
  A simpler solution is to provide manual control of the PMT voltage with a 10-turn
  potentiometer, such that the proper voltage range for the PMT is acheived. We then
  can read the command voltage on additional DACs to report to the host if needed (and,
  display on the display). In the future, we can provide an option for either manual
  control or computer control by building the appropriate control circuitry.
  UPDATE: Command voltages will be provided by a potentiometer, and read on the ADCs.
  The DACs are not useful for this purpose.
  UPDATE: using a LM324 as a single-supply op amp, the potentiometer readings don't go
  below ~0.42 V. Unknown why.
3. Monitor tube trip status (Hamamatsu H7422P-40 with M9012 controller), and provide
  a signal to reset the PS.
  For the H10721-020, the tube status is provided by a signal line derived
  from an LM339 comparator in the
  headstage amplifier. This comparator identifies when the voltage exceeds
  the trip point, then turns off the tube power. A low-going transistion on the reset input
  will re-enable the power. This transistion triggers a brief pulse for the reset, so
  that if the current is exceeded, then the circuit will trip immediately again.
  

Designed to be used with a basic serial LCD display (16x2, Hitachi command set)
connected to TX on Serial3.

Paul B. Manis, Ph.D.
UNC Chapel Hill
This work was supported by NIH/NIDCD grant DC0099809
8/3/2014 Initial commit
8/4/2014 Major changes to structure, using arrays so that a large number of PMTs could
(in theory) be controlled. This also simplifies the coding.
Added peak/mean measurement of PMT current, and ability to control the time interval over
which the measurements are made.

This software is free to use and modify under the MIT License (see README.md on github site).

*/

#include <stdio.h>
#include <stdlib.h>

const float controller_version  = 0.3;  // a number for the version of this controller code.

// assign hardware ports
const unsigned PMT_monitor[] = {1, 0};   // ADCs to read PMT current from current amp
const unsigned CMD_monitor[] = {11, 10}; // ADCs for command voltage monitor
// const unsigned PMT_cmd[]  = {DAC0, DAC1}; // note, not using dac455s...
const int PMT_ERR_TTL_IN[]   = {25, 29};  // digital line to monitor for status from H7422P-40/M9012
const int PMT_RESETPOWER_TTL_OUT[]  = {27, 31};  // if using using 7422, digital command to reset
// Definitions for the LCD:
#define lcdCmd             0xFE   //command prefix
#define lcdCmdSpecial      0x7C   //special command prefix
#define clearLCD           0x01   //Clear entire LCD screen
#define displayOff         0x08   //Display off
#define displayOn          0x0C   //Display on
#define hideCursor         0x0C   //Make cursor invisible
#define ulCursor           0x0E   //Show underline cursor
#define blkCursor          0x0D   //Show blinking block cursor
#define cursorPos          0x80   //OR with cursor position  (row 1=0 to 15, row 2 = 64 to 79, row3 = 16-31, row4 = 80-95)
#define scrollRight        0x1C
#define scrollLeft         0x18
#define cursorRight        0x14
#define cursorLeft         0x10
#define lcdLine1           0x80 // LCD line start addressing (instead of cursorPos)
#define lcdLine2           0xC0
#define lcdLine3           0x94
#define lcdLine4           0xD4

const int lcdBacklight[] = {};

char str[121];  // general scratch space to build print strings.

/*  Parameters for our specific PMTs and hardware */

float I_PMT[]    = {0., 0.};  // monitor currents from PMTs
float CMD_PMT[] = {0., 0.}; // monitor voltages to the PMTs
//float PMTAnode[] = {0., 0.};  // set to 90% of maximum
const float GI_PMT[]  = {3.6978/0.110, 3.6978/0.110};  // gain of each channel's current preamplifiers:
                                                        // 0.110 is pre amp gain, in V/uA
                                                        // 3.6978 is result of voltage divider on Due input for protection
const float cmdGainPMT[] = {0.875/0.888, 0.500/0.511}; // gain to scale the command voltage reading. (convert ADC to Volts).
    // values are taken from voltage measured at potentiometer versus voltage read by Due, with gain of 1.0
const float Thr_PMT[] = {1.0, 50.0}; // Threshold for PMT1, microamperes (H7422P-40) and PMT2
const float PMTmin[]  = {0.5, 0.5};
const float PMTmax[]  = {0.8, 1.1};   // command voltage range, H7422P-40
char PMTId[2][12] = {"H7422P-40\0", "H10721020\0"};
char modestr[2][6] = {"mean\0", "peak\0"};

float Imeas[]   = {0., 0.};  // measures of current over time (peak or average, in tmeas msec blocks; holds intermediate values)
float lastMeas[] = {0., 0.}; // result of most recent calculation of measured value
float cmdMeas[] = {0., 0.};
float lastCmdMeas[] = {0., 0.};  // result of mean value of last pmt measurement.
float tmeas     = 200.; // millisecond to integrate over
float nsamp     = 0.0;
float time_zero = 0.;
char mode       = 'p';  // single character for data sampling mode: m for mean, p for peak

const float DACscale = 4096 / 3.3; // 3.3V max output = 4096, 4096 = 1000V
const float ADCscale = 3.30 / 4096.; // 3.3.V yields 4096 A-D units, so ADCscale * A-D units is V
const int NPMT = 2;  // number of PMTs supported by this code
int serial_avail = 0; // flag for serial usb availability
int serial_chk_count = 200;  // check for serial port avaiability every 200 samples
int loop_count = 0;

void setup() {
  int i;
  /* initialize variables */
  //  for (i=0; i < NPMT; i++) {
  //    PMTAnode[i] = PMTmax[i]*0.9;  // Set to 90% of maximum
  //  }

  /* set up digital ports */
  for (i = 0; i < NPMT; i++) {
    pinMode(PMT_ERR_TTL_IN[i], INPUT);
    pinMode(PMT_RESETPOWER_TTL_OUT[i], OUTPUT);
    digitalWrite(PMT_RESETPOWER_TTL_OUT[i], LOW);
  }
  // Set up serial port to display, USB port, and hardware configuration
  Serial3.begin(9600); // Connection to display: set up serial port for 9600 baud
  SerialUSB.begin(0);  // back to host computer - speed irrelevant.
  delay(500); // wait for display and USB serial connection to complete
  if (!SerialUSB) {
    serial_avail = 0;  // no serial USB, so do not try to receive or send info to it
    LCD_Notify_NoSerial();
  } else {
    serial_avail = 1;  // ok, have a connection, so pay attention.
    LCD_Notify_Serial();
  }
  SerialUSB.setTimeout(20);  // faster timeout to improve response time
  Serial3.write(lcdCmd);
  Serial3.write(clearLCD);
  Serial3.write(lcdCmd);
  Serial3.write(hideCursor);  // clear LCD and hide cursor
  analogReadResolution(12);  // use max resolution on all ADC/DAC
  // analogWriteResolution(12);
  for (i = 0; i < NPMT; i++) {
    // setAnode(i, 0.);  // set initial voltages to 0
    resetPMT(i);
    //   digitalWrite(PMT_RESETPOWER_TTL[i], HIGH); // enable PMT1
  }
  delay(1000.); // give a second to power up
  for (i = 0; i < NPMT; i++) {
    // setAnode(i, PMTAnode[i]);  // set voltages to 90% of maximum
    LCD_Notify_Reset(i);
  }
  time_zero = millis();
}

void loop() {
  // 1. Read PMT current ports, and also display PMT command voltages.
  int i, n;
  float tmp;
  char cmd;
  nsamp += 1.0; // count times through loop for mean calculation
  for (i = 0; i < NPMT; i++) {
    delayMicroseconds(200.); // add a short delay before switching
    tmp = analogRead(PMT_monitor[i]);  // get voltage
    I_PMT[i] = tmp * ADCscale * GI_PMT[i]; // convert to voltage, then current in microamps
    delayMicroseconds(200.); // add a short delay before switching
    tmp = analogRead(CMD_monitor[i]);  // get command voltages
    CMD_PMT[i] = tmp * ADCscale * cmdGainPMT[i]; // convert to voltage, then current in microamps

    // Here, should read digital input line that corresponds to the "over current" signal, and
    // do the notification.

    //    if (I_PMT[i] > Thr_PMT[i]) {
    //      digitalWrite(PMT_POW_TTL[i], LOW);  // turn off power to PMT
    //      LCD_Notify_Over(i);
    //    }
    if (mode == 'm') {  // keep running sum and count
      Imeas[i] = Imeas[i] + I_PMT[i];
    }
    if (mode == 'p') { // keep track of peak current
      if (I_PMT[i] > Imeas[i]) {
        Imeas[i] = I_PMT[i];
      }
    }
    cmdMeas[i] = cmdMeas[i] + CMD_PMT[i];
  }
  // check if time to update display
  if ((millis() - time_zero) >= tmeas) {
    time_zero = millis();  // reset time count
    for (i = 0; i < NPMT; i++) {
      if (mode == 'm') {
        Imeas[i] = Imeas[i] / nsamp; // compute mean
      }
      cmdMeas[i] = cmdMeas[i] / nsamp; // compute mean of command also
      LCD_I_Update(i, Imeas[i]);
      LCD_Cmd_Update(i, cmdMeas[i]);
      lastMeas[i] = Imeas[i];
      lastCmdMeas[i] = cmdMeas[i];

      Imeas[i] = 0.0; // reset values
      cmdMeas[i] = 0.0;
    }
    nsamp = 0.0;
  }
  delayMicroseconds(600);  // don't need to sample super fast...
  loop_count += 1;
  if (loop_count > serial_chk_count && serial_avail == 0) {
    loop_count = 0;
    if (SerialUSB) {
      serial_avail = 1;  // ok, have a connection, so pay attention.
      LCD_Notify_Serial();
    }
    else {
      serial_avail = 0;
      LCD_Notify_NoSerial();
    }
  }
  // process incoming commands from computer over usb port - if there are any!
  if (serial_avail == 1 && SerialUSB.available() > 0) {
    cmd = SerialUSB.read();
    processCmd(cmd);
  }
  // read the error lines from the devices
  for (i = 0; i < NPMT; i++) {
    readERR(i);
  }
}

int parseInt(char cmd) {
  if (cmd == '0') {
    return(0);
  }
  else if (cmd == '1') {
    return(1);
  }
  else if (cmd == '2') {
    return (2);
  }
  else {
    return(-1);
  }
}
  
//
// Handle commands coming in through the serial port.
// Commands ask for status information, request a reset of the PMT overcurrent circuit,
// and alter the display (mean, peak) and the measurement interval.
//
//
void processCmd(char cmd) {
  int device;
  int errFlag;
  float interval;
  float value;
  char str[81];
  int m = 0;
  char n;
  
  switch (cmd) {
    
    case 'v':  // return version of this controller software
      sprintf(str, "%5.2f", controller_version);
      SerialUSB.println(str);
      break;
      
    case 'd':  // return the device Id of the current pmt
      n = SerialUSB.read(); // SerialUSB.parseInt();
      device = parseInt(n);
      if (device >= 0 && device < NPMT) {
        sprintf(str, "PMT%1d: %s", device, PMTId[device]);
        SerialUSB.println(str);
      }
      break;

    case 'i':  // return the immediate pmt current: "r1" for pmt1, etc
      device = SerialUSB.parseInt();
      if (device >= 0 && device < NPMT) {
        value = analogRead(PMT_monitor[device]) * ADCscale * GI_PMT[device];
        sprintf(str, "I%1d %6.3f uA", device, value);
        SerialUSB.println(str);
      }
      break;

    case 'c':  // return the average (or peak) pmt current on the specified PMT
      device = SerialUSB.parseInt();
      if (device >= 0 && device < NPMT) {  // note the return value indicates 'p' or 'm' depending on mode
        sprintf(str, "%c%1d %8.3f uA", mode, device, lastMeas[device]);
        SerialUSB.println(str);
      }
      break;

    case 'a':  //return the current anode voltage setting on the specified PMT
      device = SerialUSB.parseInt();
      if (device >= 0 && device < NPMT) {
        sprintf(str, "V%1d %5.3f V", device, CMD_PMT[device]);
        SerialUSB.println(str);
      }
      break;

    case 'r':  // reset a port
      device = SerialUSB.parseInt();
      if (device >= 0 && device < NPMT) {
        resetPMT(device);
      }
      break;

    case 'o':  // return the "over current" flag if it has been detected.
      device = SerialUSB.parseInt();
      if (device >= 0 && device < NPMT) {
        errFlag = digitalRead(PMT_ERR_TTL_IN[device]);
        sprintf(str, "E%1d %d", device, errFlag);
        SerialUSB.println(str);
      }
      break;

    case 'p': //set peak reading mode
      mode = 'p';
      LCD_PeakMean(0, mode);
      LCD_PeakMean(1, mode);
      break;

    case 'm': // set mean reading mode
      mode = 'm';
      LCD_PeakMean(0, mode);
      LCD_PeakMean(1, mode);
      break;

    case 't': // get a measurement interval (default set above)
      interval = SerialUSB.parseFloat();
      if (interval > 10. && interval < 10000.) {  // only accept reasonable values
        tmeas = interval;
      }
      break;

    case 's':  // get overall status for all listed PMTs
      for (device = 0; device < NPMT; device++) {
        sprintf(str, "PMT %1d %s", device, PMTId[device]);  // ID
        SerialUSB.print(str);
        SerialUSB.print("; ");
        value = analogRead(PMT_monitor[device]) * ADCscale * GI_PMT[device]; // instant current
        sprintf(str, "I %6.3f uA", value);
        SerialUSB.print(str);
        SerialUSB.print("; ");
        if (mode == 'm') {
          m = 0;
        }
        else {
          m = 1;
        }
        sprintf(str, "%s %8.3f uA", modestr[m], lastMeas[device]);  // peak or mean current (and mode)
        SerialUSB.print(str);
        SerialUSB.print("; ");
        sprintf(str, "cmd %5.3f V", CMD_PMT[device]);  // command voltage
        SerialUSB.print(str);
        SerialUSB.print("; ");
        errFlag = digitalRead(PMT_ERR_TTL_IN[device]);  // status of the Error siganl
        sprintf(str, "Err %d", errFlag);
        SerialUSB.print(str);
        SerialUSB.print("; ");
        SerialUSB.println("");  // end the string
      }
      break;
      
    case '?': // print a list of commands
      sprintf(str, "v       : Report Controller Firmware Version");
      SerialUSB.println(str);
      sprintf(str, "d#      : Print ID of the selected PMT #");
      SerialUSB.println(str);
      sprintf(str, "i#      : Read the current from the selected PMT #");
      SerialUSB.println(str);
      sprintf(str, "c#       : Read the mean or peak current");
      SerialUSB.println(str);
      sprintf(str, "m       : Select Mean reading mode");
      SerialUSB.println(str);
      sprintf(str, "p       : Select Peak reading mode");
      SerialUSB.println(str);
      sprintf(str, "a#      : Read the command voltage to the PMT #");
      SerialUSB.println(str);
      sprintf(str, "r#      : Reset the power to the selected PMT #");
      SerialUSB.println(str);
      sprintf(str, "o#      : Read the Overcurrent status of the selected PMT #");
      SerialUSB.println(str);
      sprintf(str, "t###.   : Set the reading/averaging period for mean/peak mode (msec, float)");
      SerialUSB.println(str);
      sprintf(str, "s       : Report overall status");
      SerialUSB.println(str);
      break;
   }
}

//*****************************************************************
// set anode voltages

// Note: we wet anode voltages using a potentiometer on the unit, not the
// DACs. The DACs have an odd output voltage range that would require additional
// hardware to implement, with no clear advantage over just reading the values.
// Therefore, this is kept as a comment in case we decide to change the configuration,
//
//void setAnode(int pmt, float v) {
//  char str[81];
//  float vf, vcmd;
//  PMTAnode[pmt] = v;
//  vf = v/PMTmax[pmt];  // vf if fraction of voltage range
//  vcmd = PMTmin[pmt] + vf*PMTmax[pmt];  // scale for command
//  analogWrite(PMT_cmd[pmt], int(DACscale*vcmd));
//  LCD_Anode_Update(pmt, v);
//}

// restore power and set the command to the previous value
void resetPMT(int pmt) {
  digitalWrite(PMT_RESETPOWER_TTL_OUT[pmt], HIGH); // enable PMT1
  delayMicroseconds(10);  // just a brief pulse, 10 usec or so.
  digitalWrite(PMT_RESETPOWER_TTL_OUT[pmt], LOW);
  //    setAnode(pmt, PMTAnode[pmt]);
  LCD_Notify_Reset(pmt);
}

void readERR(int pmt) {
 int err;
 err = digitalRead(PMT_ERR_TTL_IN[pmt]);  // read the error line
 if (err == true) {
   LCD_Notify_Over(pmt);  // this gets set once when error occurs
 }
// else {   // only do reset when reset command is given. That keeps the state correct
//   LCD_Notify_Reset(pmt);
// } 
}

//*****************************************************************
// Routine to display PMT information to the LCD
// Parameters that define display positions:
const int linecmd[] = {lcdLine1, lcdLine2, lcdLine3, lcdLine4};
const int cpos[] = {0, 64, 16, 80}; // initial numbers to offset cursor by
const int offset_over = 9;
const int offset_mode = 8;
const int offset_anode = 11; // leave space before...
const int offset_serial = 10;

// display most recent current reading
void LCD_I_Update(int pmt, float value) {
  char strV[21];
  Serial3.write(lcdCmd);
  Serial3.write(linecmd[pmt]);
  sprintf(strV, "%6.3fuA", value);
  Serial3.print(strV);
}

// indicate whether readings are peak or mean
void LCD_PeakMean(int pmt, char mode) {
  Serial3.write(lcdCmd);
  Serial3.write(cursorPos | (cpos[pmt] + offset_mode));
  if (mode == 'p') {
    Serial3.print("p");  // could use symbols instead...
  }
  if (mode == 'm') {
    Serial3.print("m");
  }
}

// display the command voltage (anode comman)
void LCD_Cmd_Update(int pmt, float value) {
  char strV[21];
  Serial3.write(lcdCmd);
  Serial3.write(cursorPos | (cpos[pmt] + offset_anode));
  sprintf(strV, "%5.3f", value);
  Serial3.print(strV);
}

// notify user of serial connection
void LCD_Notify_Serial() {
  Serial3.write(lcdCmd);
  Serial3.write(cursorPos | (cpos[0] + offset_serial));
  Serial3.print("S");
}

// notify user of serial absence
void LCD_Notify_NoSerial() {
  Serial3.write(lcdCmd);
  Serial3.write(cursorPos | (cpos[0] + offset_serial));
  Serial3.print("X");
}

// notify user of over-current condition
void LCD_Notify_Over(int pmt) {
  Serial3.write(lcdCmd);
  Serial3.write(cursorPos | (cpos[pmt] + offset_over));
  Serial3.print("*");
}

// reset the over-current condition notificationm

void LCD_Notify_Reset(int pmt) {
  Serial3.write(lcdCmd);
  Serial3.write(cursorPos | (cpos[pmt] + offset_over));
  Serial3.print(" ");   // clears the character in that position
}
