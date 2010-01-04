# -*- coding: utf-8 -*-
import sys
sys.path.append('C:\\cygwin\\home\\Experimenters\\luke\\acq4\\lib\\util')
import ctypes
import struct, os, threading, time, weakref
from clibrary import *

## Load windows definitions
windowsDefs = winDefs(verbose=True)

d = os.path.dirname(__file__)

# Load telegraph definitions
teleDefs = CParser(
    os.path.join(d, 'MCTelegraphs.hpp'),
    copyFrom=windowsDefs,
    cache=os.path.join(d, 'MCTelegraphs.hpp.cache'),
    verbose=True
) 

##  Windows Messaging API 
#   provides RegisterWindowMessageA, PostMessageA, PeekMessageA, GetMessageA
#   See: http://msdn.microsoft.com/en-us/library/dd458658(VS.85).aspx
wmlib = CLibrary(windll.User32, teleDefs, prefix='MCTG_')


class MultiClampTelegraph:
    """Class for receiving 'telegraph' packets from MultiClamp commander. 
    This class is automatically invoked by MultiClamp."""

    def __init__(self, devices, callback):
        # device structure looks like:
        #  {devID: [device_desc, device_state], devID: ...}
        self.devOrder = devices  # remember order of devices for communicating with MultiClamp driver
        self.devices = dict([(self.mkDevId(d), [d, None]) for d in devices])
        self.callback = callback
        self.lock = threading.Lock()
        self.thread = threading.Thread(self.messageLoop)
        self.startMessageThread()
        
    def mkDevId(self, desc):
        return desc['com'] | (desc['dev'] << 8) | (desc['chan'] << 16)
        
    def __del__(self):
        self.quit()
        
    def quit(self):
        if self.thread.isAlive():
            self.stopMessageThread()
            self.thread.join(5.0)
        if self.thread.isAlive():
            print "WARNING: Failed to stop MultiClamp telegraph thread."
        
    def startMessageThread(self):
        with self.lock:
            self.stopThread = False
            self.thread.start()

    def stopMessageThread(self):
        with self.lock:
            self.stopThread = True
        

    def updateState(self, devID, state):
        with self.lock:
            self.devices[devID][1] = state
        self.emit('update', devID)
        
    def emit(self, msg, devID):
        """Send a message via the registered callback function"""
        with self.lock:
            self.callback(msg, *self.devices[devID])
        
    def messageLoop(self):
        # create hidden window for receiving messages (how silly is this?)
        self.createWindow()
        self.registerMessages()
        
        # request connection to MCC
        for d in self.devices:
            self.post('OPEN', d)
        
        # listen for changes / reconnect requests / stop requests
        
        while True:
            while True:
                ## wndProc will be called during PeekMessage if we have received any updates.
                ## reconnect messages are received directly by PeekMessage
                ret = wmlib.PeekMessageA(None, self.hWnd, 0, 0, wmlib.PM_REMOVE)
                if ret() == 0:
                    break
                else:
                    msg = ret[0].message
                    if msg == self.msgIds['RECONNECT']:
                        devID = ret[0].lParam
                        if devID in self.deviceOrder:
                            self.emit('reconnect')
                            self.post('OPEN', devID)
                
            with self.lock:
                if self.stopThread:
                    for d in self.devices:
                        self.post('CLOSE', d)
                    break
        
            time.sleep(0.1)

    def createWindow(self):
        wndClass = wmlib.WNDCLASSA(0, wmlib.WNDPROC(self.wndProc), 0, 0, wmlib.HWND_MESSAGE, 0, 0, 0, "", "AxTelegraphWin")
        ret = wmlib.RegisterClassA(wndClass)
        print "Register class:", ret()
        if ret() == 0:
            raise Exception("Error registering window class.")
        cwret = wmlib.CreateWindowExA(
            0, wndClass.lpszClassName, "title", 
            wmlib.WS_OVERLAPPEDWINDOW,
            wmlib.CW_USEDEFAULT,
            wmlib.CW_USEDEFAULT,
            wmlib.CW_USEDEFAULT,
            wmlib.CW_USEDEFAULT,
            0, 0, wmlib.HWND_MESSAGE, 0)
        if cwret() == 0:
            raise Exception("Error creating window.", self.getWindowsError())

        self.hWnd = cwret.rval
        print "Create window:", hWnd
        

    def wndProc(self, hWnd, msg, wParam, lParam):
        """Callback function executed by windows when a message has arrived."""
        print "Window event:", msg
        if msg == wmlib.WM_COPYDATA:
            print "  copydatastruct", lParam
            data = cast(lParam, POINTER(wmlib.COPYDATASTRUCT)).contents
            if data.dwData == msgIds['REQUEST']:
                print "  got update from MCC"
                
                data  = cast(data.lpData, POINTER(wmlib.MC_TELEGRAPH_DATA)).contents
                
                #### Make sure packet is for the correct device!
                devID = self.mkDevId({'com': data.uComPortID, 'dev': data.uAxoBusID, 'chan': data.uChannelID})
                if not devID in self.devices:
                    return False
                
                #for f in data._fields_:
                    #print "    ", f[0], getattr(data, f[0])
                #global d
                state = dict([(f[0], getattr(data, f[0])) for f in data._fields_])
                self.updateState(devID, state)
            else:
                print "  unknown message type", data.dwData
        return True


    def getWindowsError(self):
        return windll.kernel32.GetLastError()


    def registerMessages(self):
        self.msgIds = {}
        for m in ['OPEN', 'CLOSE', 'REQUEST', 'BROADCAST', 'RECONNECT', 'ID']:
            self.msgIds[m] = wmlib.RegisterWindowMessageA(wmlib('values', 'MCTG_' + m + '_MESSAGE_STR'))()


    def post(self, msg, val):
        ret = wmlib.PostMessageA(wmlib.HWND_BROADCAST, self.msgIds[msg], self.hWnd, val)
        if ret() == 0:
            raise Exception("Error during post.", self.getWindowsError())
    
    



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

