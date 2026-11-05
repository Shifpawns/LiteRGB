import ctypes
import logging
import threading
from ctypes import wintypes

WM_POWERBROADCAST = 0x0218
WM_QUERYENDSESSION = 0x0011
PBT_APMSUSPEND = 0x0004
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012

LRESULT = ctypes.c_ssize_t
WNDPROC = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


def watch(on_sleep, on_resume):
    try:
        user32 = ctypes.windll.user32
    except AttributeError:
        return

    def run():
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT

        def handler(hwnd, message, wparam, lparam):
            try:
                if message == WM_POWERBROADCAST:
                    if wparam == PBT_APMSUSPEND:
                        on_sleep()
                    elif wparam in (PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC):
                        on_resume()
                    return 1
                if message == WM_QUERYENDSESSION:
                    on_sleep()
                    return 1
            except Exception as error:
                logging.warning("Power event failed: %s", error)
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)

        procedure = WNDPROC(handler)
        window_class = WNDCLASSW()
        window_class.lpfnWndProc = procedure
        window_class.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
        window_class.lpszClassName = "LiteRGBPowerWatcher"
        user32.RegisterClassW(ctypes.byref(window_class))
        user32.CreateWindowExW.restype = wintypes.HWND
        hwnd = user32.CreateWindowExW(0, window_class.lpszClassName, "LiteRGB", 0, 0, 0, 0, 0,
                                      None, None, window_class.hInstance, None)
        if not hwnd:
            logging.warning("Power watcher window could not be created")
            return
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

    threading.Thread(target=run, daemon=True).start()
