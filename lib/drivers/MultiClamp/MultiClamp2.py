# -*- coding: utf-8 -*-
from ctypes import *
import struct, os
from lib.util.clibrary import *
#from lib.util.CLibrary import *
#from PyQt4 import QtCore, QtGui

wd = os.path.dirname(__file__)
headerFiles = ['WinNtTypes.h', 'BaseTsd.h', 'WinDef.h', 'WTypes.h', 'WinUserAbridged.h']
p = CParser([os.path.join(wd, h) for h in headerFiles], 
            types={'__int64': ('long long')})
p.processAll(cache='WinUser.cache', noCacheWarning=True)

##  Windows Messaging API 
#   provides dll.RegisterWindowMessageA, dll.PostMessageA, dll.PeekMessageA, dll.GetMessageA
#   See: http://msdn.microsoft.com/en-us/library/dd458658(VS.85).aspx
wmlib = CLibrary(windll.User32, p)


## Get window handle. Should be a long integer; may change in future windows versions.
#hWnd = struct.unpack('l', QtGui.QApplication.activeWindow().winId().asstring(4))

## Load windows API header
winuserHeader = os.path.join(os.path.dirname(__file__), "WinUser.h")  ## file is copied from visual studio
#defs, funcs = cheader.getDefs(winuserHeader)
winuserDefs = parseFiles(winuserHeader, cache=winuserHeader+'.cache')


## Load Axon telegraph header
telegraphHeader = os.path.join(os.path.dirname(__file__), "mcTelegraphs.hpp")  ## file is copied from SDK

## Load Multiclamp header
axonMCHeader = os.path.join(os.path.dirname(__file__), "AxMultiClampMsg.h")  ## file is copied from SDK


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
    msgIds[m] = wmlib.RegisterWindowMessageA(wmlib[m])


def packSignalIDs(comPort, axoBus, channel):
    return comPort | (axoBus << 8) | (channel << 16)


## open connection to specific clamp channel
wmlib.PostMessageA(wmlib.HWND_BROADCAST, msgIds['MCTG_OPEN_MESSAGE_STR'], hWnd, packSignalIDs(3, 0, 1))

## poll for commander windows

## start thread for receiving messages

## for each message:
if msg.cbData == wmlib.MC_TELEGRAPH_DATA.size() and msg.dwData == msgIds['MCTG_REQUEST_MESSAGE_STR']:
    data = wmlib.MC_TELEGRAPH_DATA(msg.lpData)
    if data.uComPortID == 3 and data.uAxoBusID == 0 and data.uChannelID == 1:
        ## message is the correct type, and for the correct channel
        pass


## watch for reconnect messages

## close connection
wmlib.PostMessageA(wmlib.HWND_BROADCAST, msgIds['MCTG_CLOSE_MESSAGE_STR'], hWnd, packSignalIDs(3, 0, 1))



## request an update
## careful -- does this disable automatic notification of changes?
#wmlib.PostMessageA(wmlib.HWND_BROADCAST, msgIds['MCTG_REQUEST_MESSAGE_STR'], hWnd, packSignalIDs(3, 0, 1))
