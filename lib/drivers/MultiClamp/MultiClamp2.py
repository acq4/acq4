# -*- coding: utf-8 -*-
from ctypes import *
import struct, os
from lib.util.CParser import *
#from PyQt4 import QtCore, QtGui

from lib.util.CParser import *; 
wd = os.path.dirname(__file__)
headerFiles = ['WinNtTypes.h', 'BaseTsd.h', 'WinDef.h', 'WTypes.h', 'WinUserAbridged.h']
p = CParser([os.path.join(wd, h) for h in headerFiles], 
            types={'__int64': ('long long')})
p.processAll(cache='WinUser.cache', noCacheWarning=True)

##  Windows API 
#   provides dll.RegisterWindowMessageA, dll.PostMessageA, dll.PeekMessageA, dll.GetMessageA
#   See: http://msdn.microsoft.com/en-us/library/dd458658(VS.85).aspx
dll = windll.User32

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

## poll for commander windows

## start thread for receiving messages



