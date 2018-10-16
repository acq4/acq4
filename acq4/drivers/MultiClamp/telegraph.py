# -*- coding: utf-8 -*-
from __future__ import print_function
import sys
sys.path.append('C:\\cygwin\\home\\Experimenters\\luke\\acq4\\lib\\util')
from ctypes import *
import ctypes
import struct, os
from acq4.util.clibrary import *
import time
import weakref

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



## Create hidden window so we can catch messages
def wndProc(hWnd, msg, wParam, lParam):
    print("Window event:", msg)
    if msg == wmlib.WM_COPYDATA:
        print("  copydatastruct", lParam)
        data = cast(lParam, POINTER(wmlib.COPYDATASTRUCT)).contents
        if data.dwData == msgIds['REQUEST']:
            print("  got update from MCC")
            data  = cast(data.lpData, POINTER(wmlib.MC_TELEGRAPH_DATA)).contents
            for f in data._fields_:
                print("    ", f[0], getattr(data, f[0]))
            global d
            d = dict([(f[0], getattr(data, f[0])) for f in data._fields_])
        else:
            print("  unknown message type", data.dwData)
    return True


def getError():
    return windll.kernel32.GetLastError()

#wndClass = wmlib.WNDCLASSA(0, wmlib.WNDPROC(wndProc), 0, 0, windll.kernel32.GetModuleHandleA(c_int(0)), 0, 0, 0, "", "AxTelegraphWin")
wndClass = wmlib.WNDCLASSA(0, wmlib.WNDPROC(wndProc), 0, 0, wmlib.HWND_MESSAGE, 0, 0, 0, "", "AxTelegraphWin")
ret = wmlib.RegisterClassA(wndClass)
print("Register class:", ret())
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
    raise Exception("Error creating window.", getError())

hWnd = cwret.rval
print("Create window:", hWnd)

## register messages
messages = ['OPEN', 'CLOSE', 'REQUEST', 'BROADCAST', 'RECONNECT', 'ID']
     
msgIds = {}
for m in messages:
    msgIds[m] = wmlib.RegisterWindowMessageA(wmlib('values', 'MCTG_' + m + '_MESSAGE_STR'))()


def packSignalIDs(comPort, axoBus, channel):
    return comPort | (axoBus << 8) | (channel << 16)



## open connection to specific clamp channel
def post(msg, val):
    ret = wmlib.PostMessageA(wmlib.HWND_BROADCAST, msg, hWnd, val)
    if ret() == 0:
        raise Exception("Error during post.", getError())
    
    



## poll for commander windows
def peekMsg():
    ret = wmlib.PeekMessageA(None, hWnd, 0, 0, wmlib.PM_REMOVE)
    if ret() == 0:
        return None
    elif ret() == -1:
        raise Exception("Error during peek", getError())
    else:
        msg = ret[0]
        if msg.message in msgIds.values():
            print("Peeked Message:", list(msgIds.keys())[list(msgIds.values()).index(msg.message)])
        else:
            print("Peeked Message:", msg.message)
        return msg

def getMsgs():
    msgs = []
    while True:
        msg = peekMsg()
        if msg is None:
            return msgs
        else:
            msgs.append(msg)


#post(msgIds['OPEN'], packSignalIDs(3, 0, 1))

post(msgIds['BROADCAST'], 0)
time.sleep(1)

def unpackID(i):
    return (i & 0xFF, (i>>8) & 0xFF, (i>>16))

msgs = getMsgs()
ids = [m.lParam for m in msgs if m.message==msgIds['ID']]
print("Devices available:", list(map(unpackID, ids)))

for i in ids:
    post(msgIds['OPEN'], i)

def msgLoop():
    while True:
        m = peekMsg()
        #if m is not None:
            #print "got message"
        time.sleep(0.1)
    
msgLoop()


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

