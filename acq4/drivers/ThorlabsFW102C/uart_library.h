// The following ifdef block is the standard way of creating macros which make exporting 
// from a DLL simpler. All files within this DLL are compiled with the UART_LIBRARY_EXPORTS
// symbol defined on the command line. this symbol should not be defined on any project
// that uses this DLL. This way any other project whose source files include this file see 
// UART_LIBRARY_API functions as being imported from a DLL, whereas this DLL sees symbols
// defined with this macro as being exported.
#ifdef UART_LIBRARY_EXPORTS
#define UART_LIBRARY_API extern "C" __declspec(dllexport)
#else
#define UART_LIBRARY_API extern "C" __declspec(dllimport)
#endif

/// <summary>
///  open the COM port function.
/// </summary>
/// <param name="nPort">COM port number to be open, check the correct value through device manager.</param>
/// <param name="nBaud">bit per second of port</param>
/// <returns>0: success; 1: failed.</returns>
UART_LIBRARY_API int fnUART_LIBRARY_open(int nPort, int nBaud);
/// <summary>
/// closed current opend port
/// </summary>
UART_LIBRARY_API void fnUART_LIBRARY_close();
/// <summary>
/// <p>write string to device through opened serial port.</p>
/// <p>make sure the port was opened successful before call this function.</p>
/// </summary>
/// <param name="b">input string</param>
/// <param name="size">size of string to be written.</param>
/// <returns>0: success; 1: failed.</returns>
UART_LIBRARY_API int fnUART_LIBRARY_write(char *b, int size);
/// <summary>
/// <p>wread string from device through opened serial port.</p>
/// <p>make sure the port was opened successful before call this function.</p>
/// </summary>
/// <param name="b">returned string buffer</param>
/// <param name="limit">max length value of b buffer</param>
/// <returns>size of actual read data in byte.</returns>
UART_LIBRARY_API int fnUART_LIBRARY_read(char *b, int limit);
/// <summary>
/// list all the possible Serial port on this computer.
/// </summary>
/// <param name="nPort">port list returned string, seperated by comma</param>
/// <param name="var">max length value of nPort buffer</param>
/// <returns>0: success; 1: failed.</returns>
UART_LIBRARY_API int fnUART_LIBRARY_list(char *nPort, int var);
/// <summary>
/// <p>set command to device according to protocal in manual.</p>
/// <p>make sure the port was opened successful before call this function.</p>
/// <p>make sure this is the correct device by checking the ID string before call this function.</p>
/// </summary>
/// <param name="c">input command string</param>
/// <param name="var">lenth of input command string (<255)</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xEC: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
UART_LIBRARY_API int fnUART_LIBRARY_Set(char *c,int var);
/// <summary>
/// <p>set command to device according to protocal in manual and get the return string.</p>
/// <p>make sure the port was opened successful before call this function.</p>
/// <p>make sure this is the correct device by checking the ID string before call this function.</p>
/// </summary>
/// <param name="c">input command string (<255)</param>
/// <param name="d">output string (<255)</param>
/// <returns>
/// <p>0: success;</p>
/// <p>0xEA: CMD_NOT_DEFINED;</p>
/// <p>0xEB: time out;</p>
/// <p>0xEC: time out;</p>
/// <p>0xED: invalid string buffer;</p>
/// </returns>
UART_LIBRARY_API int fnUART_LIBRARY_Get(char *c,char *d);