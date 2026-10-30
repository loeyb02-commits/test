"""Native Windows Ink pen messages, before legacy mouse drag thresholds."""
import ctypes as C
from ctypes import wintypes as W
from collections import deque
import os


class POINTER_INFO(C.Structure):
    _fields_ = [('pointerType', W.UINT), ('pointerId', W.UINT),
                ('frameId', W.UINT), ('pointerFlags', W.UINT),
                ('sourceDevice', W.HANDLE), ('hwndTarget', W.HWND),
                ('ptPixelLocation', W.POINT), ('ptHimetricLocation', W.POINT),
                ('ptPixelLocationRaw', W.POINT), ('ptHimetricLocationRaw', W.POINT),
                ('dwTime', W.DWORD), ('historyCount', W.UINT),
                ('InputData', C.c_int32), ('dwKeyStates', W.DWORD),
                ('PerformanceCount', C.c_uint64), ('ButtonChangeType', W.UINT)]


class POINTER_PEN_INFO(C.Structure):
    _fields_ = [('pointerInfo', POINTER_INFO), ('penFlags', W.UINT),
                ('penMask', W.UINT), ('pressure', W.UINT),
                ('rotation', W.UINT), ('tiltX', C.c_int32), ('tiltY', C.c_int32)]


class NativePen:
    def __init__(self, canvas):
        self.samples = deque()
        self.installed = False
        self.active = False
        self.seen = False
        if os.name != 'nt':
            return
        self.user = C.WinDLL('user32', use_last_error=True)
        self.hwnd = canvas.winfo_id()
        result = C.c_ssize_t
        proc_type = C.WINFUNCTYPE(result, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
        self.user.GetPointerPenInfo.argtypes = [W.UINT, C.POINTER(POINTER_PEN_INFO)]
        self.user.GetPointerPenInfo.restype = W.BOOL
        self.user.GetPointerPenInfoHistory.argtypes = [W.UINT, C.POINTER(W.UINT), C.POINTER(POINTER_PEN_INFO)]
        self.user.GetPointerPenInfoHistory.restype = W.BOOL
        self.user.GetMessageExtraInfo.restype = W.LPARAM
        self.user.SetPropW.argtypes = [W.HWND, W.LPCWSTR, W.HANDLE]
        self.user.SetPropW.restype = W.BOOL
        self.user.RemovePropW.argtypes = [W.HWND, W.LPCWSTR]
        self.user.RemovePropW.restype = W.HANDLE
        self.user.CallWindowProcW.argtypes = [C.c_void_p, W.HWND, W.UINT, W.WPARAM, W.LPARAM]
        self.user.CallWindowProcW.restype = result
        self.setter = getattr(self.user, 'SetWindowLongPtrW' if C.sizeof(C.c_void_p)==8 else 'SetWindowLongW')
        self.setter.argtypes = [W.HWND, C.c_int, C.c_void_p]
        self.setter.restype = C.c_void_p
        # Disable press-and-hold, flicks, and pen feedback for this writing surface.
        self.gesture_flags = 0x00000001 | 0x00010000 | 0x00000008 | 0x00000010 | 0x00008000
        if not self.user.SetPropW(self.hwnd, 'MicrosoftTabletPenServiceProperty', W.HANDLE(self.gesture_flags)):
            raise C.WinError(C.get_last_error())

        def receive(hwnd, message, wp, lp):
            if message == 0x02CC:  # WM_TABLET_QUERYSYSTEMGESTURESTATUS
                return self.gesture_flags
            if message in (0x0245, 0x0246, 0x0247):
                info = POINTER_PEN_INFO()
                if self.user.GetPointerPenInfo(wp & 0xFFFF, C.byref(info)):
                    self.seen = True
                    samples = [info]
                    if message == 0x0245:
                        count = W.UINT()
                        self.user.GetPointerPenInfoHistory(wp & 0xFFFF, C.byref(count), None)
                        if 0 < count.value <= 4096:
                            batch = (POINTER_PEN_INFO * count.value)()
                            if self.user.GetPointerPenInfoHistory(wp & 0xFFFF, C.byref(count), batch):
                                samples = list(batch[:count.value])[::-1]
                    for sample in samples:
                        p = sample.pointerInfo
                        contact = bool(p.pointerFlags & 4) and message != 0x0247
                        self.samples.append((p.ptPixelLocation.x, p.ptPixelLocation.y,
                                             contact, bool(sample.penFlags & 7 or p.pointerFlags & 0x20),
                                             sample.pressure/1024 if sample.penMask & 1 else .6))
                    return 0
            if message == 0x024C:  # WM_POINTERCAPTURECHANGED
                self.samples.append((None,None,False,False,0))
            # Once pointer input is active, discard its duplicate promoted mouse stream.
            if self.seen and 0x0200 <= message <= 0x020E:
                extra = self.user.GetMessageExtraInfo()
                if extra & 0xFFFFFF00 == 0xFF515700:
                    return 0
            return self.user.CallWindowProcW(self.previous, hwnd, message, wp, lp)

        self.callback = proc_type(receive)
        C.set_last_error(0)
        self.previous = self.setter(self.hwnd, -4, C.cast(self.callback, C.c_void_p))
        if not self.previous:
            self.user.RemovePropW(self.hwnd, 'MicrosoftTabletPenServiceProperty')
            raise C.WinError(C.get_last_error())
        self.installed = True

    def close(self):
        if self.installed:
            self.setter(self.hwnd, -4, self.previous)
            self.user.RemovePropW(self.hwnd, 'MicrosoftTabletPenServiceProperty')
            self.installed = False
