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

#define HWND_BROADCAST  ((HWND)0xffff)
#define HWND_MESSAGE     ((HWND)-3)

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


WINUSERAPI
HWND
WINAPI
CreateWindowExA(
    __in DWORD dwExStyle,
    __in_opt LPCSTR lpClassName,
    __in_opt LPCSTR lpWindowName,
    __in DWORD dwStyle,
    __in int X,
    __in int Y,
    __in int nWidth,
    __in int nHeight,
    __in_opt HWND hWndParent,
    __in_opt HMENU hMenu,
    __in_opt HINSTANCE hInstance,
    __in_opt LPVOID lpParam);
WINUSERAPI
HWND
WINAPI
CreateWindowExW(
    __in DWORD dwExStyle,
    __in_opt LPCWSTR lpClassName,
    __in_opt LPCWSTR lpWindowName,
    __in DWORD dwStyle,
    __in int X,
    __in int Y,
    __in int nWidth,
    __in int nHeight,
    __in_opt HWND hWndParent,
    __in_opt HMENU hMenu,
    __in_opt HINSTANCE hInstance,
    __in_opt LPVOID lpParam);



typedef struct tagWNDCLASSEXA {
    UINT        cbSize;
    /* Win 3.x */
    UINT        style;
    WNDPROC     lpfnWndProc;
    int         cbClsExtra;
    int         cbWndExtra;
    HINSTANCE   hInstance;
    HICON       hIcon;
    HCURSOR     hCursor;
    HBRUSH      hbrBackground;
    LPCSTR      lpszMenuName;
    LPCSTR      lpszClassName;
    /* Win 4.0 */
    HICON       hIconSm;
} WNDCLASSEXA, *PWNDCLASSEXA, NEAR *NPWNDCLASSEXA, FAR *LPWNDCLASSEXA;
typedef struct tagWNDCLASSEXW {
    UINT        cbSize;
    /* Win 3.x */
    UINT        style;
    WNDPROC     lpfnWndProc;
    int         cbClsExtra;
    int         cbWndExtra;
    HINSTANCE   hInstance;
    HICON       hIcon;
    HCURSOR     hCursor;
    HBRUSH      hbrBackground;
    LPCWSTR     lpszMenuName;
    LPCWSTR     lpszClassName;
    /* Win 4.0 */
    HICON       hIconSm;
} WNDCLASSEXW, *PWNDCLASSEXW, NEAR *NPWNDCLASSEXW, FAR *LPWNDCLASSEXW;

typedef struct tagWNDCLASSA {
    UINT        style;
    WNDPROC     lpfnWndProc;
    int         cbClsExtra;
    int         cbWndExtra;
    HINSTANCE   hInstance;
    HICON       hIcon;
    HCURSOR     hCursor;
    HBRUSH      hbrBackground;
    LPCSTR      lpszMenuName;
    LPCSTR      lpszClassName;
} WNDCLASSA, *PWNDCLASSA, NEAR *NPWNDCLASSA, FAR *LPWNDCLASSA;
typedef struct tagWNDCLASSW {
    UINT        style;
    WNDPROC     lpfnWndProc;
    int         cbClsExtra;
    int         cbWndExtra;
    HINSTANCE   hInstance;
    HICON       hIcon;
    HCURSOR     hCursor;
    HBRUSH      hbrBackground;
    LPCWSTR     lpszMenuName;
    LPCWSTR     lpszClassName;
} WNDCLASSW, *PWNDCLASSW, NEAR *NPWNDCLASSW, FAR *LPWNDCLASSW;


WINUSERAPI
ATOM
WINAPI
RegisterClassA(
    __in CONST WNDCLASSA *lpWndClass);
WINUSERAPI
ATOM
WINAPI
RegisterClassW(
    __in CONST WNDCLASSW *lpWndClass);
