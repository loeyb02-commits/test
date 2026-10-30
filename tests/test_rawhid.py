"""Synthetic descriptor/report tests; NOT evidence of physical Windows input."""
import ctypes as C
from contextlib import ExitStack
import struct
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from penasmr import rawhid as h
from penasmr.core import Tracker
from penasmr.wintab import DiagnosticLog

class Fn:
    def __init__(self,fn): self.fn=fn
    def __call__(self,*args): return self.fn(*args)

def axis(usage,page,index,maximum):
    c=h.VALUE_CAP(); c.page=page; c.report=1; c.link=1
    c.absolute=1; c.bits=16; c.count=1; c.maximum=maximum
    c.details[0]=usage; c.details[6]=index
    return c

def button(usage,index):
    c=h.BUTTON_CAP(); c.page=13; c.report=1; c.link=1
    c.details[0]=usage; c.details[6]=index
    return c

class FakeHid:
    def __init__(self,missing_pressure=False):
        self.values=[axis(0x30,1,0,31495),axis(0x31,1,1,19684)]
        if not missing_pressure: self.values.append(axis(0x30,13,2,2047))
        self.buttons=[button(0x42,3),button(0x32,4)]
        self.HidP_GetCaps=Fn(self.caps)
        self.HidP_GetValueCaps=Fn(lambda typ,out,n,pp:self.copy(self.values,out,n))
        self.HidP_GetButtonCaps=Fn(lambda typ,out,n,pp:self.copy(self.buttons,out,n))
        self.HidP_GetData=Fn(self.data)
        self.omit_x=False
    def caps(self,pp,out):
        cap=h.HIDP_CAPS(); cap.page=13; cap.usage=2; cap.input_bytes=8
        cap.input_buttons=len(self.buttons); cap.input_values=len(self.values); cap.input_indices=5
        C.memmove(out,C.byref(cap),C.sizeof(cap)); return h.SUCCESS
    def copy(self,values,out,n):
        C.cast(n,C.POINTER(h.U16))[0]=len(values)
        for i,value in enumerate(values): out[i]=value
        return h.SUCCESS
    def data(self,typ,out,n,pp,raw,length):
        report,flags,x,y,p=struct.unpack('<BBHHH',C.string_at(raw,length))
        entries=[(0,x),(1,y),(2,p)]
        if self.omit_x: entries=entries[1:]
        if flags&1: entries.append((3,1))
        if flags&2: entries.append((4,1))
        C.cast(n,C.POINTER(h.U32))[0]=len(entries)
        for i,(index,value) in enumerate(entries): out[i]=h.HIDP_DATA(index,0,value)
        return h.SUCCESS

class FakeUser:
    def __init__(self):
        self.registrations=[]; self.foreground=100; self.raw=b''
        self.GetAncestor=Fn(lambda hwnd,flags:100)
        self.IsWindow=Fn(lambda hwnd:True)
        self.GetForegroundWindow=Fn(lambda:self.foreground)
        self.GetRawInputDeviceList=Fn(self.listing)
        self.GetRawInputDeviceInfoW=Fn(self.info)
        self.RegisterRawInputDevices=Fn(self.register)
        self.GetRawInputData=Fn(self.input)
    def listing(self,out,n,size):
        C.cast(n,C.POINTER(h.U32))[0]=1
        if out is None: return 0
        out[0].device=99; out[0].kind=2
        return 1
    def info(self,device,command,out,n):
        if command==0x2000000b:
            info=h.DEVICEINFO(); info.size=C.sizeof(info); info.kind=2
            info.data.hid.vendor=0x056a; info.data.hid.product=0x314
            info.data.hid.usage_page=13; info.data.hid.usage=2
            C.memmove(out,C.byref(info),C.sizeof(info)); return C.sizeof(info)
        if command==0x20000005:
            C.cast(n,C.POINTER(h.U32))[0]=8
            if out is None: return 0
            C.memmove(out,b'preparse',8); return 8
        raise AssertionError(command)
    def register(self,p,n,size):
        r=C.cast(p,C.POINTER(h.REGISTRATION)).contents
        self.registrations.append((r.page,r.usage,r.flags,r.window))
        return True
    def input(self,handle,command,out,n,header_size):
        C.cast(n,C.POINTER(h.U32))[0]=len(self.raw)
        if out is None: return 0
        C.memmove(out,self.raw,len(self.raw)); return len(self.raw)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.log=DiagnosticLog(Path(self.tmp.name)/'raw.json')
    def descriptor(self): return h.PenDescriptor(FakeHid(),C.create_string_buffer(b'pp'))
    def backend(self,missing=False):
        user=FakeUser(); hid=FakeHid(missing)
        com=SimpleNamespace(SetWindowSubclass=Fn(lambda *a:True),RemoveWindowSubclass=Fn(lambda *a:True),DefSubclassProc=Fn(lambda *a:42))
        with ExitStack() as stack:
            stack.enter_context(patch.object(h,'os',SimpleNamespace(name='nt')))
            stack.enter_context(patch.object(C,'WinDLL',side_effect=lambda name,**kw:{'user32':user,'hid':hid,'comctl32':com}[name],create=True))
            stack.enter_context(patch.object(C,'WINFUNCTYPE',C.CFUNCTYPE,create=True))
            backend=h.RawHID(100,Tracker(),self.log)
        return backend,user
    def raw(self,reports,code=1):
        header=h.INPUT_HEADER(2,0,99,code)
        payload=struct.pack('<II',len(reports[0]),len(reports))+b''.join(reports)
        header.size=C.sizeof(header)+len(payload)
        return bytes(header)+payload

    def test_abi(self):
        self.assertEqual([C.sizeof(t) for t in (h.HIDP_CAPS,h.VALUE_CAP,h.BUTTON_CAP,h.HIDP_DATA)],[64,72,72,8])
        self.assertEqual(h.VALUE_CAP.bits.offset,18)
        self.assertEqual(h.VALUE_CAP.minimum.offset,40)
        self.assertEqual(h.VALUE_CAP.details.offset,56)
        self.assertEqual(h.BUTTON_CAP.details.offset,56)
    def test_descriptor_decode_normalizes_and_uses_tip_switch(self):
        d=self.descriptor()
        x,y,p,contact,raw=d.decode(struct.pack('<BBHHH',1,3,31495,19684,2047))
        self.assertEqual((x,y,p,contact,raw),(1.,1.,1.,True,2047))
        self.assertFalse(d.decode(struct.pack('<BBHHH',1,2,100,200,1000))[3])
        self.assertFalse(d.decode(struct.pack('<BBHHH',1,1,100,200,1000))[3])
    def test_other_report_id_is_not_a_pen_sample(self):
        self.assertIsNone(self.descriptor().decode(struct.pack('<BBHHH',2,3,100,200,1000)))
    def test_bad_length_and_missing_coordinate_are_rejected(self):
        d=self.descriptor()
        with self.assertRaises(RuntimeError): d.decode(b'bad')
        d.hid.omit_x=True
        with self.assertRaisesRegex(RuntimeError,'missing required x'):
            d.decode(struct.pack('<BBHHH',1,3,100,200,1000))
    def test_missing_pressure_and_split_collection_are_not_guessed(self):
        with self.assertRaises(RuntimeError): h.PenDescriptor(FakeHid(True),C.create_string_buffer(b'pp'))
        hid=FakeHid(); hid.values[2].link=2
        with self.assertRaises(RuntimeError): h.PenDescriptor(hid,C.create_string_buffer(b'pp'))
    def test_signed_values_range_and_range_indices(self):
        f=dict(bits=16,minimum=-100,maximum=100)
        self.assertEqual(h.signed_value(65526,f),-10)
        with self.assertRaises(RuntimeError): h.signed_value(200,f)
        c=axis(0x30,1,0,100); c.is_range=1; c.details[0]=0x30; c.details[1]=0x31
        c.details[6]=4; c.details[7]=5
        self.assertEqual(h.data_index(c,1,0x31),5)
    def test_background_requires_sink_flag_and_stable_window(self):
        w=h.BackgroundWindow(100)
        self.assertFalse(w.stable(200,True,1.))
        self.assertFalse(w.stable(200,True,1.49))
        self.assertTrue(w.stable(200,True,1.51))
        self.assertFalse(w.stable(200,False,2.))
        self.assertFalse(w.stable(300,True,2.1))
        self.assertFalse(w.stable(100,True,5.))
    def test_startup_and_cleanup_do_not_suppress_legacy_input(self):
        b,u=self.backend()
        self.assertEqual(u.registrations,[(13,2,0x2100,100)])
        self.assertEqual(self.log.data['background_delivery'],'not_verified')
        b.close()
        self.assertEqual(u.registrations[-1],(13,2,1,None))
    def test_reports_feed_tracker_and_background_contact_counts(self):
        b,u=self.backend(); u.foreground=200
        b.attribution.observe(200,8.)
        u.raw=self.raw([struct.pack('<BBHHH',1,3,100,200,1000)])
        with patch.object(h.time,'perf_counter',return_value=10.): b._receive(1)
        self.assertEqual((b.count,b.background,b.background_contact_packets,b.max_pressure),(1,1,1,1000))
        self.assertGreater(b.tracker.motion.pressure,0)
        b.close()
    def test_transition_and_foreground_delivery_do_not_count_as_background(self):
        b,u=self.backend(); u.foreground=200
        u.raw=self.raw([struct.pack('<BBHHH',1,3,100,200,1000)])
        with patch.object(h.time,'perf_counter',return_value=10.): b._receive(1)
        self.assertEqual((b.background,b.transition_packets),(0,1))
        u.raw=self.raw([struct.pack('<BBHHH',1,3,100,200,1000)],code=0)
        with patch.object(h.time,'perf_counter',return_value=12.): b._receive(1)
        self.assertEqual(b.background,0)
        b.close()
    def test_batched_reports_use_latest_position_without_invented_timestamps(self):
        b,u=self.backend()
        u.raw=self.raw([struct.pack('<BBHHH',1,3,100,200,1000),struct.pack('<BBHHH',1,2,200,300,0)],code=0)
        b._receive(1)
        self.assertEqual((b.count,b.contact_packets),(2,1))
        self.assertEqual(b.tracker.motion.pressure,0)
        b.close()
    def test_callback_failure_still_delegates_and_stops_on_poll(self):
        b,u=self.backend(); u.raw=b'bad'
        self.assertEqual(b._window_message(100,0xff,1,1,0,0),42)
        with self.assertRaises(RuntimeError): b.poll()
        b.close()
    def test_device_removal_stops_backend(self):
        b,u=self.backend()
        self.assertEqual(b._window_message(100,0xfe,2,99,0,0),42)
        with self.assertRaisesRegex(RuntimeError,'removed'): b.poll()
        b.close()
    def test_no_matching_descriptor_does_not_register(self):
        with self.assertRaisesRegex(RuntimeError,'descriptor-verified'): self.backend(missing=True)
        self.assertFalse(any(e['event']=='rawhid_registered' for e in self.log.data['events']))

if __name__=='__main__': unittest.main()
