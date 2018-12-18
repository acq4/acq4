# -*- coding: utf-8 -*-
from __future__ import print_function
import sys
sys.path.append('C:\\cygwin\\home\\Experimenters\\luke\\acq4\\lib\\util')
import ctypes
import struct, os, threading, time, weakref
from acq4.util.clibrary import *


DEBUG = False
if DEBUG:
    print("MultiClampTelegraph Debug:", DEBUG)
__all__ = ['MultiClampTelegraph', 'wmlib']

## Load windows definitions
windowsDefs = winDefs() #verbose=True)

d = os.path.dirname(__file__)

# Load telegraph definitions
teleDefs = CParser(
    #os.path.join(d, 'MultiClampBroadcastMsg.hpp'),
    copyFrom=windowsDefs,
    cache=os.path.join(d, 'MultiClampBroadcastMsg.hpp.cache'),
    verbose=DEBUG
) 

##  Windows Messaging API 
#   provides RegisterWindowMessageA, PostMessageA, PeekMessageA, GetMessageA
#   See: http://msdn.microsoft.com/en-us/library/dd458658(VS.85).aspx
wmlib = CLibrary(windll.User32, teleDefs, prefix='MCTG_')

## Naturally we can't use the same set of definitions for the 700A and 700B.
ax700ADefs = CParser(
    #os.path.join(d, 'MCTelegraphs.hpp'),
    copyFrom=windowsDefs,
    cache=os.path.join(d, 'MCTelegraphs.hpp.cache'),
    verbose=DEBUG
)

class MultiClampTelegraph:
    """Class for receiving 'telegraph' packets from MultiClamp commander. 
    This class is automatically invoked by MultiClamp."""

    def __init__(self, channels, callback, debug=DEBUG):
        """Create a telegraph thread that opens connections to the devices listed in 
        'channels' and reports changes to the devices through 'callback'. 
        """
        self.debug = debug
        if self.debug:
            print("Initializing MultiClampTelegraph")

        ## remember index of each device for communicating through callback
        self.channels = channels
        self.devIndex = dict([(self.mkDevId(channels[k]), k) for k in channels])  
        #print "DEV index:", self.devIndex
        self.callback = callback
        self.lock = threading.RLock(verbose=debug)
        self.thread = threading.Thread(name="MultiClampTelegraph", target=self.messageLoop)
        self.thread.daemon = True
        self.startMessageThread()
        
    def mkDevId(self, desc):
        """Create a device ID used for communicating via telegraph"""
        #print "mkDevId", desc
        if self.debug:
            print("MultiClampTelegraph.mkDevId called.")
        if desc['model'] == 0:
            return desc['com'] | (desc['dev'] << 8) | (desc['chan'] << 16)
        elif desc['model'] == 1:
            return (int(desc['sn']) & 0x0FFFFFFF) | (desc['chan'] << 28)
        else:
            raise Exception('Device type not supported:', desc)
        
    def __del__(self):
        self.quit()
        
    def quit(self):
        if self.debug:
            print("MultiClampTelegraph.quit called.")
        if self.thread.isAlive():
            self.stopMessageThread()
            self.thread.join(5.0)
        if self.thread.isAlive():
            print("WARNING: Failed to stop MultiClamp telegraph thread.")
        
    def startMessageThread(self):
        if self.debug:
            print("MultiClampTelegraph.startMessageThread called.")
        with self.lock:
            self.stopThread = False
            self.thread.start()

    def stopMessageThread(self):
        if self.debug:
            print("MultiClampTelegraph.stopMessageThread called.")
        with self.lock:
            self.stopThread = True

    def updateState(self, devID, state):
        #with self.lock:
            #self.devices[devID][1] = state
        #print("update state:", devID, self.devIndex[devID])
        if self.debug:
            print("MultiClampTelegraph.updateState called.")
        self.emit('update', self.devIndex[devID], state)
        
    def emit(self, *args):
        """Send a message via the registered callback function"""
        if self.debug:
            print("MultiClampTelegraph.emit called.")
        with self.lock:
            self.callback(*args)
        
    def messageLoop(self):

        if self.debug:
            print("MultiClampTelegraph.messageLoop called.")
        # create hidden window for receiving messages (how silly is this?)
        self.createWindow()
        self.registerMessages()
        #print "window handle:", self.hWnd
        #print "messages:", self.msgIds
        
        # request connection to MCC
        for d in self.devIndex:
            #print "Open:", d
            self.post('OPEN', d)
        
        # listen for changes / reconnect requests / stop requests
        
        while True:
            while True:  ## pull all waiting messages
                ## wndProc will be called during PeekMessage if we have received any updates.
                ## reconnect messages are received directly by PeekMessage
                ret = wmlib.PeekMessageA(None, self.hWnd, 0, 0, wmlib.PM_REMOVE)
                if ret() == 0:
                    break
                else:
                    msg = ret[0].message
                    if msg == self.msgIds['RECONNECT']:
                        devID = ret[0].lParam
                        if devID in self.devIndex:
                            self.emit('reconnect')
                            self.post('OPEN', devID)  ## reopen connection to device
                    elif msg == self.msgIds['COMMAND']:
                        print("Peeked command.")
                
            with self.lock:
                if self.stopThread:
                    for d in self.devIndex:
                        self.post('CLOSE', d)
                    break
        
            time.sleep(0.1)

    def createWindow(self):
        if self.debug:
            print("MultiClampTelegraph.createWindow called.")
        self.wndClass = wmlib.WNDCLASSA(0, wmlib.WNDPROC(self.wndProc), 0, 0, wmlib.HWND_MESSAGE, 0, 0, 0, "", "AxTelegraphWin")
        ret = wmlib.RegisterClassA(self.wndClass)
        #print "Register class:", ret()
        if ret() == 0:
            raise Exception("Error registering window class.")
        cwret = wmlib.CreateWindowExA(
            0, self.wndClass.lpszClassName, "title", 
            wmlib.WS_OVERLAPPEDWINDOW,
            wmlib.CW_USEDEFAULT,
            wmlib.CW_USEDEFAULT,
            wmlib.CW_USEDEFAULT,
            wmlib.CW_USEDEFAULT,
            0, 0, wmlib.HWND_MESSAGE, 0)
        if cwret() == 0:
            raise Exception("Error creating window.", self.getWindowsError())

        self.hWnd = cwret.rval
        #print "Create window:", self.hWnd
        

    def wndProc(self, hWnd, msg, wParam, lParam):
        """Callback function executed by windows when a message has arrived."""
        #print "Window event:", msg
        if self.debug:
            print("MultiClampTelegraph.wndProc called.")

        if msg == wmlib.WM_COPYDATA:
            data = cast(lParam, POINTER(wmlib.COPYDATASTRUCT)).contents
            if data.dwData == self.msgIds['REQUEST']:
                if self.debug:
                    print("    COPYDATASTRUCT.dwData (ULONG_PTR, a memory address):", data.dwData) ### ULONG_PTR should be a 64-bit number on 64-bit machines, and a 32-bit number on 32-bit machines
                    print("    COPYDATASTRUCT.cbData (DWORD, the size (in bytes) of data pointed to by lpData):", data.cbData)
                    print("    COPYDATASTRUCT.lpData (PVOID, a pointer to the data to be passed): ", data.lpData)

                data  = cast(data.lpData, POINTER(wmlib.MC_TELEGRAPH_DATA)).contents
                #### Make sure packet is for the correct device!
                devID = self.mkDevId({'com': data.uComPortID, 'dev': data.uAxoBusID, 'chan': data.uChannelID, 'model': data.uHardwareType, 'sn': data.szSerialNumber})
                if not devID in self.devIndex:
                    return False
                
                #for f in data._fields_:
                    #print "    ", f[0], getattr(data, f[0])
                #global d
                #state = dict([(f[0], getattr(data, f[0])) for f in data._fields_])
                
                ## translate state into something prettier
                #print "units:", data.uScaleFactorUnits, data.uRawScaleFactorUnits
                mode = ['VC', 'IC', 'I=0'][data.uOperatingMode]
                
                if data.uHardwareType == wmlib.MCTG_HW_TYPE_MC700A:
                    if self.debug:
                        print("  processing MC700A mode", mode)
                    if mode == 'VC':
                        priSignal = ax700ADefs.defs['values']['MCTG_OUT_MUX_VC_LONG_NAMES'][data.uScaledOutSignal]
                        secSignal = ax700ADefs.defs['values']['MCTG_OUT_MUX_VC_LONG_NAMES_RAW'][data.uRawOutSignal]
                        priUnits = UNIT_MAP[data.uScaleFactorUnits]
                        secUnits = UNIT_MAP[data.uRawScaleFactorUnits]
                    else:
                        priSignal = ax700ADefs.defs['values']['MCTG_OUT_MUX_IC_LONG_NAMES'][data.uScaledOutSignal]
                        secSignal = ax700ADefs.defs['values']['MCTG_OUT_MUX_IC_LONG_NAMES_RAW'][data.uRawOutSignal]
                        priUnits = UNIT_MAP[data.uScaleFactorUnits]
                        secUnits = UNIT_MAP[data.uRawScaleFactorUnits]
                else:
                    try:
                        priSignal = wmlib.MCTG_OUT_GLDR_LONG_NAMES[data.uScaledOutSignal]
                    except IndexError:
                        priSignal = "Auxiliary"  # some amps give signal=44 here, which is not in the list..

                    try:
                        secSignal = wmlib.MCTG_OUT_GLDR_LONG_NAMES[data.uRawOutSignal]
                    except IndexError:
                        secSignal = "Auxiliary"  # some amps give signal=44 here, which is not in the list..

                    priUnits = UNIT_MAP[data.uScaleFactorUnits]
                    secUnits = UNIT_MAP[data.uRawScaleFactorUnits]
                
                # Scale factors are 0 for aux signals.
                sf = data.dScaleFactor if data.dScaleFactor != 0 else 1
                rsf = data.dRawScaleFactor if data.dRawScaleFactor != 0 else 1

                state = {
                    'mode': mode,
                    'primarySignal': priSignal,
                    'primaryGain': data.dAlpha,
                    'primaryUnits': priUnits[0],
                    'primaryScaleFactor': priUnits[1] / (sf * data.dAlpha),
                    'secondarySignal': secSignal,
                    'secondaryGain': 1.0,
                    'secondaryUnits': secUnits[0],
                    'secondaryScaleFactor': secUnits[1] / (rsf * 1.0),
                    'membraneCapacitance': data.dMembraneCap,
                    'LPFCutoff': data.dLPFCutoff,
                    'extCmdScale': data.dExtCmdSens,
                }
                #print "EXT:", data.dExtCmdSens
                self.updateState(devID, state)
            elif data.dwData == self.msgIds['COMMAND']:
                print("Caught command!")
                return False
            #else:
                ##print "  unknown message type", data.dwData
        return True


    def getWindowsError(self):
        if self.debug:
            print("MultiClampTelegraph.getWindowsError called.")
        return windll.kernel32.GetLastError()


    def registerMessages(self):
        if self.debug:
            print("MultiClampTelegraph.registerMessages called.")
        self.msgIds = {}
        for m in ['OPEN', 'CLOSE', 'REQUEST', 'BROADCAST', 'RECONNECT', 'ID']:
            self.msgIds[m] = wmlib.RegisterWindowMessageA(wmlib('values', 'MCTG_' + m + '_MESSAGE_STR'))()
        self.msgIds['COMMAND'] = wmlib.RegisterWindowMessageA(wmlib('values', 'MC_COMMAND_MESSAGE_STR'))()

    def post(self, msg, val):
        if self.debug:
            print("MultiClampTelegraph.post called.")
            print("      msg:", msg, "    val:", val)
        ret = wmlib.PostMessageA(wmlib.HWND_BROADCAST, self.msgIds[msg], self.hWnd, val)
        if ret() == 0:
            raise Exception("Error during post.", self.getWindowsError())
    
  
UNIT_MAP = {
    wmlib.UNITS_VOLTS_PER_VOLT:       ('V', 1.0),
    wmlib.UNITS_VOLTS_PER_MILLIVOLT:  ('V', 1e-3),
    wmlib.UNITS_VOLTS_PER_MICROVOLT:  ('V', 1e-6),
    wmlib.UNITS_VOLTS_PER_AMP:        ('A', 1.0),
    wmlib.UNITS_VOLTS_PER_MILLIAMP:   ('A', 1e-3),
    wmlib.UNITS_VOLTS_PER_MICROAMP:   ('A', 1e-6),
    wmlib.UNITS_VOLTS_PER_NANOAMP:    ('A', 1e-9),
    wmlib.UNITS_VOLTS_PER_PICOAMP:    ('A', 1e-12)
}
  
  
#UNIT_MAP = {}
#for k in teleDefs.defs['values']:
    #if k[:17] == 'MCTG_UNITS_VOLTS_':
        #UNIT_MAP[teleDefs.defs['values'][k]] = k[11:].lower()


## poll for commander windows
#def peekMsg():
    #ret = wmlib.PeekMessageA(None, hWnd, 0, 0, wmlib.PM_REMOVE)
    #if ret() == 0:
        #return None
    #elif ret() == -1:
        #raise Exception("Error during peek", self.getWindowsError())
    #else:
        #msg = ret[0]
        #if msg.message in msgIds.values():
            #print "Peeked Message:", msgIds.keys()[msgIds.values().index(msg.message)]
        #else:
            #print "Peeked Message:", msg.message
        #return msg

#def getMsgs():
    #msgs = []
    #while True:
        #msg = peekMsg()
        #if msg is None:
            #return msgs
        #else:
            #msgs.append(msg)


#post(msgIds['OPEN'], packSignalIDs(3, 0, 1))

#post(msgIds['BROADCAST'], 0)
#time.sleep(1)


#msgs = getMsgs()
#ids = [m.lParam for m in msgs if m.message==msgIds['ID']]
#print "Devices available:", map(unpackID, ids)

#for i in ids:
    #post(msgIds['OPEN'], i)

#def msgLoop():
    #while True:
        #m = peekMsg()
        ##if m is not None:
            ##print "got message"
        #time.sleep(0.1)
    
#msgLoop()


#app._exec()

## start thread for receiving messages

## for each message:
#if msg.cbData == wmlib.MC_TELEGRAPH_DATA.size() and msg.dwData == msgIds['MCTG_REQUEST_MESSAGE_STR']:
    #data = wmlib.MC_TELEGRAPH_DATA(msg.lpData)
    #if data.uComPortID == 3 and data.uAxoBusID == 0 and data.uChannelID == 1:
        ### message is the correct type, and for the correct channel
        #pass


## watch for reconnect messages

## close connection
#wmlib.PostMessageA(wmlib.HWND_BROADCAST, msgIds['MCTG_CLOSE_MESSAGE_STR'], hWnd, packSignalIDs(3, 0, 1))



## request an update
## careful -- does this disable automatic notification of changes?
#wmlib.PostMessageA(wmlib.HWND_BROADCAST, msgIds['MCTG_REQUEST_MESSAGE_STR'], hWnd, packSignalIDs(3, 0, 1))

