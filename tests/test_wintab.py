"""ABI and initialization regression tests. Fake driver != Windows hardware test."""
import ctypes as C
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import ExitStack
from penasmr.core import Tracker
from penasmr import wintab as wt

class Function:
    def __init__(self, call):
        self.call = call
    def __call__(self, *args):
        return self.call(*args)

class Driver:
    def __init__(self, reject_system=False, reject_unicode=False,
                 pressure=True, demote=True, bad_effective=False):
        self.opens, self.operations = [], []
        self.live = None
        self.contexts = {}
        self.reject_system = reject_system
        self.reject_unicode = reject_unicode
        self.pressure = pressure
        self.demote = demote
        self.bad_effective = bad_effective
        for suffix,cls in [('W',wt.LOGCONTEXT),('A',wt.LOGCONTEXTA)]:
            setattr(self,'WTInfo'+suffix,Function(lambda cat,idx,out,s=suffix,c=cls:self.info(s,c,cat,idx,out)))
            setattr(self,'WTOpen'+suffix,Function(lambda hwnd,p,enable,s=suffix:self.open(s,hwnd,p,enable)))
            setattr(self,'WTGet'+suffix,Function(lambda h,p:self.get(h,p)))
        self.WTClose = Function(self.close)
        self.WTOverlap = Function(self.overlap)
        self.WTEnable = Function(self.enable)
        self.WTQueueSizeSet = Function(lambda h,n:True)
        self.WTPacketsGet = Function(lambda h,n,b:0)

    def info(self,suffix,cls,category,index,out):
        if suffix == 'W' and self.reject_unicode:
            return 0
        if category in (3,4):
            value=cls()
            value.options=wt.CXO_PEN | wt.CXO_MESSAGES | (wt.CXO_SYSTEM if category==4 else 0)
            value.inextx=value.outextx=10000
            value.inexty=value.outexty=8000
            value.sensx=value.sensy=value.syssensx=value.syssensy=65536
            value.pktrate=200
            value.btndnmask=value.btnupmask=0xffffffff
        elif category==1:
            value=wt.U32(0xffff if index==7 else 1)
        elif category==100 and index==6:
            value=wt.U32(wt.MASK if self.pressure else 0x180)
        elif category==100 and index in (12,13,15):
            value=wt.AXIS(0,2047 if index==15 else 10000,0,65536)
        else:
            return 0
        if out is not None:
            C.memmove(out,C.byref(value),C.sizeof(value))
        return C.sizeof(value)

    def open(self,suffix,hwnd,p,enabled):
        cls=wt.LOGCONTEXT if suffix=='W' else wt.LOGCONTEXTA
        ctx=cls.from_buffer_copy(C.string_at(p,C.sizeof(cls)))
        self.opens.append((suffix,hwnd,enabled,wt.context_values(ctx)))
        self.operations.append(('open',enabled))
        if self.reject_system and ctx.options & wt.CXO_SYSTEM:
            return 0
        self.live=77
        self.contexts[77]=ctx
        return 77

    def overlap(self,h,top):
        self.operations.append(('overlap',top))
        return self.demote

    def enable(self,h,on):
        self.operations.append(('enable',on))
        return True

    def get(self,h,p):
        ctx=self.contexts[h]
        if self.bad_effective:
            ctx.pktdata |= 0x40
        C.memmove(p,C.byref(ctx),C.sizeof(ctx))
        return True

    def close(self,h):
        self.operations.append(('close',h))
        self.live=None
        return True

class ReportedDefaultsDriver(Driver):
    """Replay uploaded default contexts; later device/open behavior is simulated."""
    def __init__(self, **kwargs):
        self.fixture=json.loads((Path(__file__).parent/'fixtures'/'wacom-default-contexts.json').read_text())
        self.queries=[]
        super().__init__(**kwargs)

    def info(self,suffix,cls,category,index,out):
        self.queries.append((category,index))
        if category in (3,4):
            value=cls()
            for name,number in self.fixture['contexts'][str(category)].items():
                if name != 'name':
                    setattr(value,name,number)
        elif category==1:
            value=wt.U32(self.fixture['context_options'] if index==7 else self.fixture['ndevices'])
        else:
            return super().info(suffix,cls,category,index,out)
        if out is not None:
            C.memmove(out,C.byref(value),C.sizeof(value))
        return C.sizeof(value)

class InitializationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log=wt.DiagnosticLog(Path(self.tmp.name)/'startup.json')

    def make(self,driver,valid_window=True):
        user=SimpleNamespace(IsWindow=Function(lambda h:valid_window),
                             GetAncestor=Function(lambda h,flags:1001),
                             GetForegroundWindow=Function(lambda:1001))
        with ExitStack() as stack:
            stack.enter_context(patch.object(wt,'os',SimpleNamespace(name='nt')))
            stack.enter_context(patch.object(C,'WinDLL',side_effect=lambda name,**kwargs:user if name=='user32' else driver,create=True))
            stack.enter_context(patch.object(C,'set_last_error',return_value=None,create=True))
            stack.enter_context(patch.object(C,'get_last_error',return_value=0,create=True))
            return wt.Wintab(999,Tracker(),self.log)

    def test_windows_abi_and_offsets(self):
        self.assertEqual(C.sizeof(wt.LOGCONTEXT),212)
        self.assertEqual(C.sizeof(wt.LOGCONTEXTA),172)
        self.assertEqual(C.sizeof(wt.AXIS),16)
        self.assertEqual(C.sizeof(wt.PACKET),12)
        self.assertEqual(wt.LOGCONTEXT.options.offset,80)
        self.assertEqual(wt.LOGCONTEXT.pktdata.offset,104)
        self.assertEqual(wt.LOGCONTEXT.inorgx.offset,124)
        self.assertEqual(wt.LOGCONTEXT.syssensy.offset,208)

    def test_disabled_open_demote_enable_and_effective_context(self):
        d=Driver()
        b=self.make(d)
        suffix,hwnd,enabled,ctx=d.opens[0]
        self.assertEqual((suffix,hwnd,enabled),('W',1001,False))
        self.assertEqual(ctx['options'],wt.CXO_SYSTEM)
        self.assertEqual(ctx['btndnmask']|ctx['btnupmask'],0)
        self.assertEqual(d.operations[:4],[('open',False),('overlap',False),('enable',True),('overlap',False)])
        self.assertEqual(b.xscale,10000)
        saved=json.loads(self.log.path.read_text())
        self.assertEqual(saved['background_delivery'],'not_verified')
        self.assertTrue(any(e['event']=='effective_context' for e in saved['events']))

    def test_digitizer_fallback_after_system_rejection(self):
        d=Driver(reject_system=True)
        self.make(d)
        self.assertEqual(len(d.opens),2)
        self.assertEqual(d.opens[1][3]['options'],0)
        failure=next(e for e in self.log.data['events'] if e['event']=='WTOpenW')
        self.assertEqual(failure['result'],0)
        self.assertEqual(failure['last_error'],0)

    def test_ansi_fallback_uses_matching_abi(self):
        d=Driver(reject_unicode=True)
        self.make(d)
        self.assertEqual(d.opens[0][0],'A')

    def test_missing_pressure_never_claims_success(self):
        d=Driver(pressure=False)
        with self.assertRaisesRegex(RuntimeError,'All conservative'):
            self.make(d)
        self.assertFalse(d.opens)
        self.assertEqual(self.log.data['events'][-1]['event'],'startup_failed')
        self.assertTrue(self.log.path.exists())

    def test_demote_failure_never_enables_and_closes_every_handle(self):
        d=Driver(demote=False)
        with self.assertRaises(RuntimeError):
            self.make(d)
        self.assertFalse(any(name=='enable' for name,_ in d.operations))
        self.assertEqual(sum(name=='close' for name,_ in d.operations),4)
        self.assertIsNone(d.live)

    def test_changed_packet_abi_is_rejected_and_closed(self):
        d=Driver(bad_effective=True)
        with self.assertRaises(RuntimeError):
            self.make(d)
        self.assertIsNone(d.live)
        self.assertFalse(any(e['event']=='context_opened' for e in self.log.data['events']))

    def test_invalid_window_fails_before_open(self):
        d=Driver()
        with self.assertRaisesRegex(RuntimeError,'Invalid top-level'):
            self.make(d,False)
        self.assertFalse(d.opens)

    def test_zero_mapping_is_not_opened(self):
        ctx=wt.prepare_context(wt.LOGCONTEXT())
        with self.assertRaisesRegex(RuntimeError,'zero X/Y'):
            wt.validate_context(ctx)

    def test_query_size_mismatch_rejected_before_copy(self):
        b=object.__new__(wt.Wintab)
        calls=[]
        def wrong(cat,index,out):
            calls.append(out)
            return 4
        with self.assertRaisesRegex(RuntimeError,'size 4, expected 212'):
            b._query(wrong,4,0,wt.LOGCONTEXT)
        self.assertEqual(calls,[None])

    def test_last_error_is_captured_with_context_failure(self):
        b=object.__new__(wt.Wintab)
        b.log=self.log
        b.dll=SimpleNamespace(WTOpenW=lambda *args:0)
        with patch.object(C,'set_last_error',create=True), \
             patch.object(C,'get_last_error',return_value=5,create=True), \
             patch.object(C,'FormatError',return_value='Access denied',create=True):
            self.assertEqual(b._call('WTOpenW',1001,None,False),0)
        event=json.loads(self.log.path.read_text())['events'][-1]
        self.assertEqual(event['last_error'],5)
        self.assertEqual(event['last_error_text'],'Access denied')

    def test_context_preparation_preserves_driver_mapping_and_original(self):
        original=wt.LOGCONTEXT()
        original.options=15
        original.inextx=1234
        original.outexty=-8765
        original.btndnmask=0xffffffff
        prepared=wt.prepare_context(original)
        self.assertEqual((prepared.inextx,prepared.outexty),(1234,-8765))
        self.assertEqual(prepared.options,wt.CXO_SYSTEM)
        self.assertEqual(original.options,15)
        self.assertEqual(original.btndnmask,0xffffffff)

    def test_reported_defaults_pass_normalization_and_query_physical_device(self):
        d=ReportedDefaultsDriver()
        self.make(d)
        self.assertEqual(len(d.opens),1)
        ctx=d.opens[0][3]
        self.assertEqual(ctx['options'],1) # inherited 0x8011, interface supports 0x0d
        self.assertEqual(ctx['device'],0xffffffff) # preserve valid virtual binding
        self.assertEqual((ctx['inextx'],ctx['outextx']),(31496,1920))
        self.assertIn((100,6),d.queries)
        self.assertNotIn((99,6),d.queries)
        self.assertNotIn((100+0xffffffff,6),d.queries)
        resolved=next(e for e in self.log.data['events'] if e['event']=='device_resolution')
        self.assertEqual(resolved['capability_device'],0)
        normalized=next(e for e in self.log.data['events'] if e['event']=='prepared_options')
        self.assertEqual(normalized['removed'],0x8010)
        self.assertTrue(any(e['event']=='WTOpenW' for e in self.log.data['events']))

    def test_reported_digitizer_fallback_also_clears_default_extra_options(self):
        d=ReportedDefaultsDriver(reject_system=True)
        self.make(d)
        self.assertEqual(len(d.opens),2)
        self.assertEqual(d.opens[1][3]['options'],0)
        self.assertEqual(d.opens[1][3]['device'],0xffffffff)

    def test_multiple_devices_do_not_use_arbitrary_aggregate_calibration(self):
        d=ReportedDefaultsDriver()
        d.fixture['ndevices']=2
        with self.assertRaises(RuntimeError):
            self.make(d)
        self.assertFalse(d.opens)

    def test_unknown_aggregate_device_count_is_not_guessed(self):
        for count in (None,0,2):
            with self.subTest(count=count), self.assertRaises(RuntimeError):
                wt.capability_device(0xffffffff,count)
        self.assertEqual(wt.capability_device(0xffffffff,1),0)

if __name__=='__main__':
    unittest.main()
