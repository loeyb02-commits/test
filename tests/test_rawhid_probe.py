import ctypes as C
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from penasmr import rawhid_probe as hid

class Function:
    def __init__(self,fn): self.fn=fn
    def __call__(self,*args): return self.fn(*args)

class Tests(unittest.TestCase):
    def test_windows_abi(self):
        self.assertEqual(C.sizeof(hid.HIDINFO),16)
        self.assertEqual(C.sizeof(hid.DEVICEINFO),32)
        self.assertEqual(hid.RAWINPUTDEVICELIST.kind.offset,C.sizeof(C.c_void_p))

    def test_read_only_inventory_does_not_register_or_open_devices(self):
        calls=[]
        def listing(out,count,size):
            calls.append('list')
            C.cast(count,C.POINTER(hid.U32))[0]=1
            if out is None: return 0
            out[0].device=123
            out[0].kind=2
            return 1
        def info(device,command,out,size):
            calls.append('info')
            self.assertEqual(command,0x2000000b)
            data=C.cast(out,C.POINTER(hid.DEVICEINFO)).contents
            data.kind=2
            data.data.hid=hid.HIDINFO(0x056a,1,1,0x0d,2)
            return C.sizeof(hid.DEVICEINFO)
        user=SimpleNamespace(GetRawInputDeviceList=Function(listing),GetRawInputDeviceInfoW=Function(info))
        with patch.object(hid,'os',SimpleNamespace(name='nt')), \
             patch.object(C,'WinDLL',return_value=user,create=True):
            report=hid.enumerate_hid()
        self.assertEqual(calls,['list','list','info'])
        self.assertEqual(report['devices'][0]['vendor'],0x056a)
        self.assertIn('does not prove',report['note'])

if __name__=='__main__': unittest.main()
