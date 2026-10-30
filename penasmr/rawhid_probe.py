"""Read-only Windows Raw Input HID inventory, NOT an input backend.

Does not register input, open device handles, or change legacy/Ink delivery.
No report bytes, device paths or serial numbers are collected.
"""
import ctypes as C
from ctypes import wintypes as W
import os

U32 = C.c_uint32
U16 = C.c_uint16

class RAWINPUTDEVICELIST(C.Structure):
    _fields_ = [('device',C.c_void_p),('kind',U32)]

class HIDINFO(C.Structure):
    _fields_ = [('vendor',U32),('product',U32),('version',U32),('usage_page',U16),('usage',U16)]

class DEVICEUNION(C.Union):
    _fields_ = [('hid',HIDINFO),('reserved',U32*6)]

class DEVICEINFO(C.Structure):
    _fields_ = [('size',U32),('kind',U32),('data',DEVICEUNION)]

ERROR_RESULT = 0xffffffff

def enumerate_hid():
    if os.name != 'nt':
        raise RuntimeError('Raw Input inventory requires Windows')
    user = C.WinDLL('user32',use_last_error=True)
    listing = user.GetRawInputDeviceList
    listing.argtypes = [C.POINTER(RAWINPUTDEVICELIST),C.POINTER(U32),U32]
    listing.restype = U32
    info = user.GetRawInputDeviceInfoW
    info.argtypes = [C.c_void_p,U32,C.c_void_p,C.POINTER(U32)]
    info.restype = U32
    count = U32()
    if listing(None,C.byref(count),C.sizeof(RAWINPUTDEVICELIST)) == ERROR_RESULT:
        raise C.WinError(C.get_last_error())
    if count.value > 4096:
        raise RuntimeError('Unreasonable Raw Input device count')
    devices = (RAWINPUTDEVICELIST*count.value)()
    copied = listing(devices,C.byref(count),C.sizeof(RAWINPUTDEVICELIST))
    if copied == ERROR_RESULT:
        raise C.WinError(C.get_last_error())
    if copied > len(devices):
        raise RuntimeError('Device list changed; run inventory again')
    result = []
    for entry in devices[:copied]:
        if entry.kind != 2: # RIM_TYPEHID
            continue
        data = DEVICEINFO()
        data.size = C.sizeof(data)
        size = U32(C.sizeof(data))
        returned = info(entry.device,0x2000000b,C.byref(data),C.byref(size)) # RIDI_DEVICEINFO
        if returned == ERROR_RESULT:
            result.append({'error_code':C.get_last_error()})
            continue
        if returned != C.sizeof(data) or data.kind != 2:
            result.append({'error':'Unexpected RID_DEVICE_INFO size/type','returned':int(returned)})
            continue
        hid = data.data.hid
        result.append({name:int(getattr(hid,name)) for name,_ in HIDINFO._fields_})
    return {
        'devices':result,
        'wacom_vendor_id':0x056a,
        'note':'Inventory only. A Wacom/digitizer entry does not prove reports, pressure, tip switch, or background delivery are accessible. No input was registered or intercepted.',
    }
