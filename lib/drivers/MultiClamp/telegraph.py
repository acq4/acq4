# -*- coding: utf-8 -*-
import sys
sys.path.append('C:\\cygwin\\home\\Experimenters\\luke\\acq4\\lib\\util')
from ctypes import *
import ctypes
import struct, os
from clibrary import *
import weakref
#from lib.util.CLibrary import *
#from PyQt4 import QtCore, QtGui

__all__ = ['MultiClamp']

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


## Get window handle. Should be a long integer; may change in future windows versions.
#from PyQt4 import QtGui, QtCore

#class App(QtGui.QApplication):
    #def winEventFilter(self, msg):
        #print "got message", msg
        #print dir(msg)
        ##return 0


#app = App([])
#app = QtGui.QApplication([])
#win = QtGui.QMainWindow()
#win.show()

#evd = QtCore.QAbstractEventDispatcher.instance()

#def eventFilter(*args):
    #print "event:", args
    #return False
#evd.setEventFilter(eventFilter)

#print "Getting hwnd..", win.winId()
#hWnd = ctypes.pythonapi.PyCObject_AsVoidPtr(py_object(win.winId().ascobject()))
#print hWnd





## Create hidden window so we can catch messages
def wndProc(*args):
    print "Window event:", args
    return 0

wndClass = wmlib.WNDCLASSA(0, wmlib.WNDPROC(wndProc), 0, 0, windll.kernel32.GetModuleHandleA(c_int(0)), 0, 0, 0, "", "AxTelegraphWin")
ret = wmlib.RegisterClassA(wndClass)
if ret() == 0:
    raise Exception("Error registering window class.")
cwret = wmlib.CreateWindowExA(0, wndClass.lpszClassName, "title", 0, 0, 0, 0, 0, 0, 0, wndClass.hInstance, 0)
if cwret() is None:
    erv = windll.kernel32.GetLastError()
    raise Exception("Error creating window.", erv)
hWnd = cwret()


## register messages
messages = [
    'MCTG_OPEN_MESSAGE_STR',
    'MCTG_CLOSE_MESSAGE_STR',
    'MCTG_REQUEST_MESSAGE_STR',
    'MCTG_BROADCAST_MESSAGE_STR',
    'MCTG_RECONNECT_MESSAGE_STR',
    'MCTG_ID_MESSAGE_STR',
]
     
msgIds = {}
for m in messages:
    msgIds[m] = wmlib.RegisterWindowMessageA(wmlib('values', m))()


def packSignalIDs(comPort, axoBus, channel):
    return comPort | (axoBus << 8) | (channel << 16)


## open connection to specific clamp channel
ret = wmlib.PostMessageA(wmlib.HWND_BROADCAST, msgIds['MCTG_OPEN_MESSAGE_STR'], hWnd, packSignalIDs(3, 0, 1))
print "Broadcast:", ret()

## poll for commander windows
def getMsg():
    return wmlib.PeekMessageA(None, hWnd, 0, 0, wmlib.PM_NOREMOVE)



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

