from ctypes import *
import pdb
import time

#libHandle = windll.kernel32.LoadLibraryA('C:\\Program Files (x86)\\Thorlabs\\FW102C\\bin\\uart_library.dll')
#libHandle = windll.kernel32.LoadLibraryA('uart_library_installed_32bit.dll')
#libHandle = windll.kernel32.LoadLibraryA('uart_library.dll')
fw = WinDLL('uart_library.dll')
#fw = cdll.LoadLibrary('uart_library.dll')
#fw = WinDLL(None,handle=libHandle)
#$attr = getattr(fw,'uart_library.h')

print fw

#pPorts = pointer(ports)
#pdb.set_trace()
#fw.fnUART_LIBRARY_open()
ports = c_char_p('test')
#res = fw.fnUART_LIBRARY_isOpen()
#print 'is open:', res
#res = fw.fnUART_LIBRARY_list(ports,c_int(255))
#print 'list of available ports:', ports.value, res
#ports,c_long(255))

nPort = c_char_p('COM4')
nBaud = c_int(115200)
timeOut = c_int(3)
print 'connecting to port :', nPort.value
hdl = fw.fnUART_LIBRARY_open(nPort, nBaud, timeOut)
hdl = fw.fnUART_LIBRARY_open(nPort, nBaud, timeOut)
print 'response to open call :', hdl, type(hdl)

hdl = c_int(hdl)
#command = c_ubyte('pos?\r')
str_bytes = 'pos=4\r000'
raw_bytes = (c_ubyte * 8).from_buffer_copy(str_bytes)

#pdb.set_trace()
print 're', type(raw_bytes), sizeof(raw_bytes)
#response= (c_ubyte * 8).from_buffer_copy(str_bytes)
resp = [0]*6*1024
response = c_ubyte*6*1024
res = fw.fnUART_LIBRARY_Get(hdl,raw_bytes,resp)

print response.value

print 'closing port'
res = fw.fnUART_LIBRARY_close(hdl)
del(fw)
