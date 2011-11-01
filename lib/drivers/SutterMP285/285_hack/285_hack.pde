#include <EEPROM.h>

//Ports are connected as follows:
//
// ROE buttons:
//PA0 - 22 - Home In  (from ROE)
//PA1 - 23 - Home Out (to MP285)
//PA2 - 24 - Coarse In
//PA3 - 25 - Coarse Out
//PA4 - 26 - Cont In
//PA5 - 27 - Cont Out
//PA6 - 28 - Diag In
//PA7 - 29 - Diag Out
//
// ROE inputs (from ROE):
//PC5 - 32 - Z CCW
//PC4 - 33 - Z CW
//PC3 - 34 - Y CCW
//PC2 - 35 - Y CW
//PC1 - 36 - X CCW
//PC0 - 37 - X CW
//
// ROE outputs (to MP285):
//PL5 - 44 - Z CCW
//PL4 - 45 - Z CW
//PL3 - 46 - Y CCW
//PL2 - 47 - Y CW
//PL1 - 48 - X CCW
//PL0 - 49 - X CW

               
//long iter = 0;
//long quietCount = 0;
long pos[3];
byte gotNewTicks = 0;  // if ROE ticks have been received since last call to getPos()
unsigned long disableROE = 0; // ROE is disabled until millis() reads this time
int fineStep;
int coarseStep;

unsigned long lastUpdateTime = 0; // Last time a serial update was run
unsigned long lastStatusTime = 0; // Last time the MP285's status was requested
unsigned long lastRoeTick = 0;    // Last time a tick was received from the ROE
unsigned long lastInputTime = 0; // Last time when serial input was seen from PC

byte bytesLeftInPacket = 0; // number of bytes remaining until the expected end of a command packet from the PC

// Holds current status info for the MP285
struct {
  unsigned int xspeed;
  unsigned int step_div;
  unsigned int step_mul;
  unsigned int roe_vari;
  unsigned int resolution;
  unsigned int step_mode;
  byte udir[3];   // X, Y, Z; each value specifies the ROE bit (0-5) that drives the axis in the negative direction.
} stat;

byte directionMask[6]; // masks the ROE bits used for +X, -X, +Y, -Y, +Z, -Z

long limits[6] = {0,0,0,0,0,0};  // +X, -X, +Y, -Y, +Z, -Z
byte useLimit[6] = {0,0,0,0,0,0};  // by default, all limits are disabled

long char4ToLong(char* str) {
  union {long val; char string[4];} x;
  x.string[0] = str[0];
  x.string[1] = str[1];
  x.string[2] = str[2];
  x.string[3] = str[3];
  return x.val;
}

long char2ToInt(char* str) {
  union {unsigned int val; char string[2];} x;
  x.string[0] = str[0];
  x.string[1] = str[1];
  return x.val;
}






void printHex(char* str, int len) {
  for (int i=0; i<len; i++) {
    Serial.print((unsigned char)str[i], DEC);
    Serial.print(" ");
  }
  Serial.print("\n");
}

int readInput(char* target, int len, int timeout=2000) {
  // read command data from computer
  for( int i=0; i<len; i++ ) {
    int t = millis();
    int t2;
    while ( Serial.available() == 0 ) {
      t2 = millis();
      if (t2 - t > timeout) {
//        Serial.print("Serial timeout. Data so far: ");
//        printHex(target, i+1);
//        Serial.println(target);
        return -(i+1);
      }
    }
    target[i] = Serial.read();
  }
  return len;
}
    
int readPacket(char* target, int maxLen, int timeout=2000) {
  // Read until maxLen, feeding bytes into target.
  // Returns the number of bytes read, including the \r
  // Returns negative values if no \r was read or in case of timeout.
  int i = 0;
  while (true) {
    int t = millis();
    int t2;
    while ( Serial1.available() == 0 ) {
      t2 = millis();
      if (t2 - t > timeout) {
//        Serial.print("Serial timeout. Data so far: ");
//        printHex(target, i+1);
//        Serial.println(target);
//        Serial.print("start: ");
//        Serial.println(t);
//        Serial.print("stop: ");
//        Serial.println(t2);
        
        return -(i+1);
      }
    }
    target[i] = Serial1.read();
    if (target[i] == '\r' and i+1 == maxLen) {
      return i+1;
    }  
    i++;
    if (i >= maxLen) {
//      Serial.println("Error: no carriage return");
//      printHex(target, i);
      return -i;
    }
  }
} 

int checkError(int timeout=2000) {
  int t = millis();
  int t2;
  while ( Serial1.available() == 0 ) {
    t2 = millis();
    if (t2 - t > timeout) {
//      Serial.println("Serial timeout");
//      Serial.print("start: ");
//      Serial.println(t);
//      Serial.print("stop: ");
//      Serial.println(t2);
      
      return -1;
    }
  }

  char v = Serial1.read();
  if( v == '\r' ) {
//    Serial.println("OK");
    return 0;     // no error; return 0
  }
  
  t = millis();
  while ( Serial1.available() == 0 ) {
    if (millis() - t > timeout) {
//      Serial.println("Serial timeout");
      return -1;
    }
  }

  char v2 = Serial1.read();
  if( v2 == '\r' ) {
//    Serial.print("MP285 error: ");
//    Serial.println((int)v);
    return (int)v;  // return error code
  }
  
  Serial1.flush();
//  Serial.println("Expected CR; got junk.");
  return -2;   // Got two non-CR bytes; something is wrong.
  
}  

void setLimits() {
  // Read limit-setting data from serial port, write into eeprom
  
  char data[31];
  int len = readInput(data, 31);
  if( len != 31 ) {
    Serial.write((byte)16);
    Serial.write('\r');
    return;
  }
  
  for( int i=0; i<6; i++ ) {
    limits[i] = char4ToLong(data + i*4);
    useLimit[i] = data[i+24];
  }
  Serial.write('\r');
  
  for( int i=0; i<30; i++ ) {
    EEPROM.write(i, data[i]);
  }
}

void loadLimits() {
  char data[30];
  for( int i=0; i<30; i++ ) {
    data[i] = EEPROM.read(i);
  }
  for( int i=0; i<6; i++ ) {
    limits[i] = char4ToLong(data + i*4);
    useLimit[i] = data[i+24];
  }
}

int getPos() {
  Serial1.flush();
  Serial1.write("c\r");
  
  char resp[13];
  int len = readPacket(resp, 13);
  if (len != 13) {
    return -1;
  }
  
//  Serial.print("Correct position:  ");
  for (int i=0; i<3; i++) {
    long x = char4ToLong(resp +i*4);
//    Serial.print(x-pos[i]);
//    Serial.print("  ");
    pos[i] = x;  // record position globally
//    p[i] = pos[i];
//    Serial.println(pos[i]);
  }
//  Serial.println("");
  gotNewTicks = 0;
  disableROE = millis() + 1000;  // don't allow any ROE ticks for 1 second after requesting position.
  return 1;
}  

int getStatus() {
  Serial1.flush();
  Serial1.write("s\r");
  
  char resp[33];
  int len = readPacket(resp, 33);
  if (len != 33) {
//    Serial.print("wrong packet size ");
//    Serial.println(len);
    return -1;
  }
  
//  Serial.println("Got status:");
  unsigned int spd = char2ToInt(resp+28);
  stat.xspeed = spd & 0x7FFF;
  stat.resolution = spd & 0x8000 > 0 ? 50 : 10;
  stat.step_div = char2ToInt(resp+24);    // step scale is 1um / step_div
  stat.step_mul = char2ToInt(resp+26);
  stat.roe_vari = char2ToInt(resp+4);
  stat.step_mode = resp[15] & 0x4 > 0 ? 50 : 10;
  stat.udir[0] = resp[1];
  stat.udir[1] = resp[2];
  stat.udir[2] = resp[3];
  
  for( int i=0; i<3; i++ ) {
    byte v = ((byte)1) << resp[i+1];  // the ROE bit that moves this axis in the negative direction
    stat.udir[i] = v;
    byte v2;             // the ROE bit that moves this axis in the negative direction
    if( v == 1 || v == 4 || v == 16 )
      v2 = v << 1;
    else
      v2 = v >> 1;
      
    directionMask[2*i] = v2;    // For example, directionMask[0] = 4 means that ROE bit 4 moves X in the + direction
    directionMask[2*i+1] = v;
//    Serial.print("Stat X dir: ");
//    Serial.println(v, BIN);
  }
//  Serial.print("  speed: ");
//  Serial.println(s.xspeed);
//  Serial.print("  resolution: ");
//  Serial.println(s.resolution);
//  Serial.print("  step_mode: ");
//  Serial.println(s.step_mode);
//  Serial.print("  step_div: ");
//  Serial.println(s.step_div);
//  Serial.print("  step_mul: ");
//  Serial.println(s.step_mul);
//  Serial.print("  roe_vari: ");
//  Serial.println(s.roe_vari);   // number of steps per click. 0.1um per step/fine; 0.5um per step/coarse.
  
  fineStep = stat.roe_vari;
  coarseStep = stat.roe_vari * 5;
  lastStatusTime = millis();
  return 1;
}

//void setSpeed(unsigned int spd, unsigned int fine) {
//  Serial1.flush();
//  charInt c;
//  c.val = spd;
//  if( fine > 0 ) {
//   c.val = spd | 0x8000;
//  }
//  else {
//   c.val = spd & 0x7FFF;
//  } 
//  Serial.print("Set speed:");
//  Serial.println(c.val);
//  Serial.println(c.val,BIN);
//  
//  Serial1.print('V');
////  Serial1.write(c.val);
//  Serial1.print(c.string[0]);
//  Serial1.print(c.string[1]);
//  Serial1.print('\r');
//  checkError();
//}

void printPos() {
  // print the estimated position immediately without consulting the MP285
  union {long val; char string[4];} chl;
  for( int i=0; i<3; i++ ) {
    chl.val = pos[i];
    for( int j=0; j<4; j++ ) {
      Serial.write(chl.string[j]);
    }
  }
  Serial.write('\r');
}

void flashLights() {
  DDRA = B11111111;  // all button lines become inputs, which causes them to draw current through the button lights
  delay(1);
  DDRA = B10101010;  // 0 == input; 1 == output
}  


void runSerial() {
  // Forward serial data between PC and MP285, catch any commands intended for the arduino.
  
  // first flush any junk coming from the 285:
  while( Serial1.available() ){
    Serial.write(Serial1.read());
  }
  
  if( ! Serial.available() )
    return;
    
  unsigned long now = millis();
  if( now - lastInputTime > 500 ) {  // long time since anything was received; assume any unfinished packets are dead.
    bytesLeftInPacket = 0;
  }
  while( Serial.available() ){
    unsigned char b = Serial.read();
    if( bytesLeftInPacket == 0 ) {  // this is the beginning of a packet; see if we need to handle it or forward it to the MP285
      if( b == 'p' ) {
        printPos();
        return;
      }
      if( b == 'l' ) {
        setLimits();
        return;
      }
      else if( b == 0xF0 ) {
        // This is junk sent by the PC when it connected; ignore.
        return;
      }
      else if( b != 0x3 ) {  // 0x3 is stop command; pass through immediately.
//        if( b == 'm' )  // schedule position request
//          gotNewTicks = True;
          
        byte lens[] = {1,13,3,1,100,3,3,1,1,1,1,1,1};  // all other commands, we guess how many more bytes to expect before the end of the packet.
        char cmds[] = {"cmVodkuabenrs"};
        for( int i=0; i<13; i++ ) {
          if( b == cmds[i] ) {
            bytesLeftInPacket = lens[i];
            break;
          }
        }
      }
    }
    else {
        bytesLeftInPacket--;
    }  
    Serial1.write(b);
  }
  lastInputTime = now;
    
  // Disable ROE for 1 second after any serial data is sent to the controller.
  disableROE = millis() + 1000;
}


void setup() {
  Serial.begin(115200);
  Serial1.begin(19200);
  Serial.println("Good morning.");

  DDRA = B10101010;  // 0 == input; 1 == output
  DDRL = B11111111;
  DDRC = B00000000;
  PORTA = (PINA << 1) & B10101010;
  PORTC = B11000000;  // pull first two bits up--they're not connected and we don't want them to change at random.
  PORTL = B11111111;
  
  getPos();
  getStatus();
  loadLimits();
}


void loop() {
  unsigned long now = millis();
  byte pinc = PINC;  // make a copy of pinc since it could change while we're here.
  
  if( now > disableROE ) {
    // pass buttons through
    // TODO: catch cont/pulse and diag buttons here for other purposes..
    PORTA = (PINA << 1) & B10101010;
    
    // check limits before copying ROE state
    byte mask = 0;
    if( useLimit[0] && pos[0] > limits[0] )
      mask |= directionMask[0];
    if( useLimit[1] && pos[0] < limits[1] )
      mask |= directionMask[1];
    if( useLimit[2] && pos[1] > limits[2] )
      mask |= directionMask[2];
    if( useLimit[3] && pos[1] < limits[3] )
      mask |= directionMask[3];
    if( useLimit[4] && pos[2] > limits[4] )
      mask |= directionMask[4];
    if( useLimit[5] && pos[2] < limits[5] )
      mask |= directionMask[5];
    
    byte maskedPINC = pinc | mask;  // Note: PINC bits 0-5 are normally high, and drop low during an ROE click.
    if( maskedPINC != pinc ) {
      flashLights();   // inform user if ROE ticks were ignored due to limits
    }
    unsigned char diff = (~maskedPINC & PORTL) ;
    
    PORTL = maskedPINC;
    
    if( diff > 0 ) {
//      Serial.println("------------");
//      Serial.println(diff,BIN);
//      Serial.println(directionMask[0],BIN);
//      Serial.println(directionMask[1],BIN);
//      Serial.println(directionMask[2],BIN);
//      Serial.println(directionMask[3],BIN);
//      Serial.println(directionMask[4],BIN);
//      Serial.println(directionMask[5],BIN);
      lastRoeTick = now;
      gotNewTicks = 1;
      unsigned int steps = PINA & 0x4 ? coarseStep : fineStep;
      if( diff & directionMask[0] )
        pos[0] += steps;
      if( diff & directionMask[1] )
        pos[0] -= steps;
        
      if( diff & directionMask[2] )
        pos[1] += steps;
      if( diff & directionMask[3] )
        pos[1] -= steps;
        
      if( diff & directionMask[4] )
        pos[2] += steps;
      if( diff & directionMask[5] )
        pos[2] -= steps;
    }
  }

  if (now-lastUpdateTime > 100 && (pinc == 0xFF || pinc == B11000000)) {  // only run serial loop if no ROE lines are active OR the ROE is disconnected.
    lastUpdateTime = now;
    runSerial();
    if( gotNewTicks && now - lastRoeTick > 500 )  // NOTE: it's ok to get the position within 500ms of an ROI tick, but not 
                                                  // between 500ms and 1s.
      getPos();  // sets gotNewTicks to 0 if successful.
    if( now - lastStatusTime > 5000 && now - lastRoeTick > 5000 ) {
      getStatus();
      getPos();
    }
      
  }
  if( now < lastUpdateTime ) {  // clock rolled over; reset all times
    lastUpdateTime = 0;
    lastRoeTick = 0;
    lastInputTime = 0;
    disableROE = now+1000;
  }  
}


