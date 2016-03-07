from ctypes import *

#libHandle = windll.kernel32.LoadLibraryA('C:\\Program Files (x86)\\Thorlabs\\FW102C\\bin\\uart_library.dll')
libHandle = windll.kernel32.LoadLibraryA('uart_library_installed_32bit.dll')
#fw = WinDLL('uart_library.dll')
fw = WinDLL(None,handle=libHandle)
#$attr = getattr(fw,'uart_library.h')

ports = c_char_p()
#pPorts = pointer(ports)
res = fw.fnUART_LIBRARY_list(ports,255)
print ports.value, ports
#ports,c_long(255))

nBaud = c_int(115200)
nPort = c_int(4)
print nPort.value
res = fw.fnUART_LIBRARY_open()
print res
