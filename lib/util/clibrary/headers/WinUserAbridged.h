// definitions pulled from WinUser.h and elsewhere to provide message-passing functionality
// needed in MCTelegraphs.hpp

// typedef char *LPCSTR;
// typedef LPCSTR LPCTSTR;
// typedef unsigned short WCHAR;
// typedef WCHAR *LPCWSTR;
// typedef unsigned int UINT;
// typedef bool BOOL;
// typedef unsigned long DWORD;
// typedef void *PVOID;
// typedef PVOID HANDLE;
// typedef HANDLE HWND;
// typedef UINT_PTR WPARAM;
// 
#define WINUSERAPI
#define WINAPI
#define __in
#define __in_opt
#define __out
#define CONST const
#define FAR far
/*
 * Message structure
 */
// typedef struct tagMSG {
//     HWND        hwnd;
//     UINT        message;
//     WPARAM      wParam;
//     LPARAM      lParam;
//     DWORD       time;
//     POINT       pt;
// #ifdef _MAC
//     DWORD       lPrivate;
// #endif
// } MSG, *PMSG, NEAR *NPMSG, FAR *LPMSG;


WINUSERAPI
UINT
WINAPI
RegisterWindowMessageA(
    __in LPCSTR lpString);
WINUSERAPI
UINT
WINAPI
RegisterWindowMessageW(
    __in LPCWSTR lpString);

WINUSERAPI
BOOL
WINAPI
PostMessageA(
    __in_opt HWND hWnd,
    __in UINT Msg,
    __in WPARAM wParam,
    __in LPARAM lParam);
WINUSERAPI
BOOL
WINAPI
PostMessageW(
    __in_opt HWND hWnd,
    __in UINT Msg,
    __in WPARAM wParam,
    __in LPARAM lParam);

WINUSERAPI
BOOL
WINAPI
PeekMessageA(
    __out LPMSG lpMsg,
    __in_opt HWND hWnd,
    __in UINT wMsgFilterMin,
    __in UINT wMsgFilterMax,
    __in UINT wRemoveMsg);
WINUSERAPI
BOOL
WINAPI
PeekMessageW(
    __out LPMSG lpMsg,
    __in_opt HWND hWnd,
    __in UINT wMsgFilterMin,
    __in UINT wMsgFilterMax,
    __in UINT wRemoveMsg);

/*
 * PeekMessage() Options
 */
#define PM_NOREMOVE         0x0000
#define PM_REMOVE           0x0001
#define PM_NOYIELD          0x0002
#define PM_QS_INPUT         (QS_INPUT << 16)
#define PM_QS_POSTMESSAGE   ((QS_POSTMESSAGE | QS_HOTKEY | QS_TIMER) << 16)
#define PM_QS_PAINT         (QS_PAINT << 16)
#define PM_QS_SENDMESSAGE   (QS_SENDMESSAGE << 16)



WINUSERAPI
BOOL
WINAPI
GetMessageA(
    __out LPMSG lpMsg,
    __in_opt HWND hWnd,
    __in UINT wMsgFilterMin,
    __in UINT wMsgFilterMax);
WINUSERAPI
BOOL
WINAPI
GetMessageW(
    __out LPMSG lpMsg,
    __in_opt HWND hWnd,
    __in UINT wMsgFilterMin,
    __in UINT wMsgFilterMax);
