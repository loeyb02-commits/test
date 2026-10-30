"""Exercise the native message adapter with fake Win32 functions, without a tablet."""
import ctypes as C
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from penasmr import pen_input


class Function:
    def __init__(self, function): self.function=function
    def __call__(self,*args): return self.function(*args)


class NativePenTests(TestCase):
    def test_direct_pen_down_barrel_up_and_duplicate_suppression(self):
        info=pen_input.POINTER_PEN_INFO()
        info.pointerInfo.ptPixelLocation.x=101
        info.pointerInfo.ptPixelLocation.y=202
        info.pointerInfo.pointerFlags=4
        info.penFlags=1
        info.penMask=1
        info.pressure=512
        def read(pointer_id,out):
            C.memmove(out,C.byref(info),C.sizeof(info))
            return 1
        user=SimpleNamespace(**{name:Function(function) for name,function in {
            'GetPointerPenInfo':read,
            'GetPointerPenInfoHistory':lambda *args:0,
            'GetMessageExtraInfo':lambda:0xFF515700,
            'SetPropW':lambda *args:1,
            'RemovePropW':lambda *args:1,
            'CallWindowProcW':lambda *args:77,
            'SetWindowLongPtrW':lambda *args:123,
            'SetWindowLongW':lambda *args:123,
        }.items()})
        with patch.object(pen_input,'os',SimpleNamespace(name='nt')), \
             patch.object(C,'WinDLL',return_value=user,create=True), \
             patch.object(C,'WINFUNCTYPE',C.CFUNCTYPE,create=True), \
             patch.object(C,'set_last_error',create=True):
            adapter=pen_input.NativePen(SimpleNamespace(winfo_id=lambda:42))
            self.assertEqual(adapter.callback(42,0x0246,7,0),0)
            self.assertEqual(adapter.samples.popleft(),(101,202,True,True,.5))
            info.pointerInfo.pointerFlags=0
            info.penFlags=0
            info.pointerInfo.ptPixelLocation.x=102
            adapter.callback(42,0x0247,7,0)
            self.assertEqual(adapter.samples.popleft(),(102,202,False,False,.5))
            self.assertEqual(adapter.callback(42,0x0200,0,0),0)
            user.GetMessageExtraInfo=Function(lambda:0)
            self.assertEqual(adapter.callback(42,0x0200,0,0),77)
            self.assertEqual(adapter.callback(42,0x02CC,0,0),adapter.gesture_flags)
            adapter.callback(42,0x024C,0,0)
            self.assertEqual(adapter.samples.popleft(),(None,None,False,False,0))
            adapter.close()
            self.assertFalse(adapter.installed)
