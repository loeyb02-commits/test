"""Filter Windows touch before Tk converts it to ordinary mouse input."""
import ctypes as C
import os
from ctypes import wintypes as W


def is_touch_mouse(extra):
    # Microsoft MI_WP_SIGNATURE and touch flag; pen uses the same signature
    # without the touch bit. Keep physical mouse and pen messages.
    return extra & 0xFFFFFF00 == 0xFF515700 and bool(extra & 0x80)


class TouchFilter:
    def __init__(self):
        self.hook = None
        if os.name != 'nt':
            return
        self.user = C.WinDLL('user32', use_last_error=True)
        kernel = C.WinDLL('kernel32', use_last_error=True)
        result = C.c_ssize_t
        callback = C.WINFUNCTYPE(result, C.c_int, W.WPARAM, W.LPARAM)
        class MSG(C.Structure):
            _fields_ = [('hwnd', W.HWND), ('message', W.UINT),
                        ('wParam', W.WPARAM), ('lParam', W.LPARAM),
                        ('time', W.DWORD), ('pt', W.POINT), ('lPrivate', W.DWORD)]
        self.user.SetWindowsHookExW.argtypes = [C.c_int, callback, W.HINSTANCE, W.DWORD]
        self.user.SetWindowsHookExW.restype = W.HANDLE
        self.user.CallNextHookEx.argtypes = [W.HANDLE, C.c_int, W.WPARAM, W.LPARAM]
        self.user.CallNextHookEx.restype = result
        self.user.GetMessageExtraInfo.restype = W.LPARAM
        self.user.UnhookWindowsHookEx.argtypes = [W.HANDLE]
        self.user.UnhookWindowsHookEx.restype = W.BOOL
        self.user.CloseTouchInputHandle.argtypes = [W.HANDLE]
        self.user.GetPointerType.argtypes = [W.UINT, C.POINTER(W.UINT)]
        self.user.GetPointerType.restype = W.BOOL
        kernel.GetCurrentThreadId.restype = W.DWORD

        def process(code, removed, address):
            if code >= 0 and removed == 1:
                msg = C.cast(address, C.POINTER(MSG)).contents
                touch = False
                if 0x0200 <= msg.message <= 0x020E:
                    touch = is_touch_mouse(self.user.GetMessageExtraInfo())
                elif msg.message == 0x0240:  # WM_TOUCH owns a handle
                    self.user.CloseTouchInputHandle(W.HANDLE(msg.lParam))
                    touch = True
                elif msg.message in (0x0245, 0x0246, 0x0247, 0x0249, 0x024A, 0x024E, 0x024F):
                    kind = W.UINT()
                    touch = bool(self.user.GetPointerType(msg.wParam & 0xFFFF, C.byref(kind))) and kind.value == 2
                if touch:
                    msg.message = 0  # WM_NULL: never reaches a Tk widget
            return self.user.CallNextHookEx(self.hook, code, removed, address)

        self.callback = callback(process)  # retain for the full hook lifetime
        self.hook = self.user.SetWindowsHookExW(3, self.callback, None, kernel.GetCurrentThreadId())
        if not self.hook:
            raise C.WinError(C.get_last_error())

    def close(self):
        if self.hook:
            self.user.UnhookWindowsHookEx(self.hook)
            self.hook = None
