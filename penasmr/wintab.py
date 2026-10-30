"""Non-promoting Wintab polling, with bounded, persistent startup diagnostics.

ABI checked against Wacom-Developer/wacom-device-kit-windows WintabSDK/WINTAB.H.
Opening a context is NOT evidence of background packet delivery.
"""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import platform
import time

U32, I32 = C.c_uint32, C.c_int32
WTI_DEFCONTEXT, WTI_DEFSYSCTX, WTI_DEVICES = 3, 4, 100
CXO_SYSTEM, CXO_PEN, CXO_MESSAGES, CXO_CSRMESSAGES = 1, 2, 4, 8
MASK = 0x80 | 0x100 | 0x400  # PK_X | PK_Y | PK_NORMAL_PRESSURE

class AXIS(C.Structure):
    _fields_ = [('minimum', I32), ('maximum', I32), ('units', U32), ('resolution', U32)]

_CONTEXT_FIELDS = [(n, U32) for n in (
    'options','status','locks','msgbase','device','pktrate','pktdata','pktmode',
    'movemask','btndnmask','btnupmask')]
_CONTEXT_FIELDS += [(n, I32) for n in (
    'inorgx','inorgy','inorgz','inextx','inexty','inextz',
    'outorgx','outorgy','outorgz','outextx','outexty','outextz')]
_CONTEXT_FIELDS += [(n, U32) for n in ('sensx','sensy','sensz')]
_CONTEXT_FIELDS += [(n, I32) for n in ('sysmode','sysorgx','sysorgy','sysextx','sysexty')]
_CONTEXT_FIELDS += [(n, U32) for n in ('syssensx','syssensy')]

class LOGCONTEXT(C.Structure):
    # Windows WCHAR is always 16 bits, even when ABI tests run on Linux.
    _fields_ = [('name', C.c_uint16*40)] + _CONTEXT_FIELDS

class LOGCONTEXTA(C.Structure):
    _fields_ = [('name', C.c_char*40)] + _CONTEXT_FIELDS

class PACKET(C.Structure):
    _fields_ = [('x', I32), ('y', I32), ('pressure', U32)]

def context_values(ctx):
    result = {name: int(getattr(ctx, name)) for name, _ in _CONTEXT_FIELDS}
    raw = C.string_at(C.addressof(ctx), 80 if isinstance(ctx, LOGCONTEXT) else 40)
    result['name'] = raw.decode('utf-16-le' if isinstance(ctx, LOGCONTEXT) else 'ascii',errors='replace').split('\0',1)[0]
    return result

def prepare_context(default):
    """Keep driver mappings; remove unsupported legacy pen-service integration."""
    ctx = type(default).from_buffer_copy(default)
    name = b'PenASMR observer'
    if isinstance(ctx, LOGCONTEXT):
        for i, value in enumerate(name):
            ctx.name[i] = value
        ctx.name[len(name)] = 0
    else:
        ctx.name = name
    # CXO_PEN is not a generic 'collect pen' or background-subscription flag.
    # Preserve CXO_SYSTEM only if supplied by the selected driver default.
    ctx.options &= ~(CXO_PEN | CXO_MESSAGES | CXO_CSRMESSAGES)
    ctx.pktdata = ctx.movemask = MASK
    ctx.pktmode = 0
    # Do not claim button events / implicit button capture from another app.
    ctx.btndnmask = ctx.btnupmask = 0
    return ctx

def validate_context(ctx):
    if not ctx.inextx or not ctx.inexty or not ctx.outextx or not ctx.outexty:
        raise RuntimeError('Default context has zero X/Y input or output extent')
    if ctx.pktdata != MASK or ctx.pktmode != 0:
        raise RuntimeError('Context packet layout differs from PACKET ABI')

class DiagnosticLog:
    def __init__(self, path=None):
        base = Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'PenASMR'
        self.path = Path(path) if path else base / 'wintab-startup.json'
        self.data = {
            'schema': 1, 'python': platform.python_version(), 'platform': platform.platform(),
            'pointer_bits': C.sizeof(C.c_void_p)*8,
            'abi': {'LOGCONTEXTW': C.sizeof(LOGCONTEXT), 'LOGCONTEXTA': C.sizeof(LOGCONTEXTA),
                    'AXIS': C.sizeof(AXIS), 'PACKET': C.sizeof(PACKET)},
            'events': [], 'background_delivery': 'not_verified',
            'last_error_note': 'Wintab does not guarantee SetLastError. Zero is not a success indication; nonzero is supplementary evidence only.',
        }
        self.write_error = None

    def add(self, event, **values):
        self.data['events'].append(dict(event=event, **values))
        self.save()

    def save(self):
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.data,indent=2,ensure_ascii=False),encoding='utf-8')
            temporary.replace(self.path)
        except OSError as exc:
            self.write_error = str(exc)  # report without masking the driver error

class Wintab:
    def __init__(self, hwnd, tracker, diagnostics=None):
        self.log = diagnostics if diagnostics is not None else DiagnosticLog()
        self.tracker, self.handle = tracker, None
        try:
            self._initialize(hwnd)
        except Exception as exc:
            self.close()
            self.log.add('startup_failed', error=str(exc))
            raise RuntimeError(f'{exc}\nDiagnostics: {self.log.path}' +
                               (f' (write failed: {self.log.write_error})' if self.log.write_error else '')) from exc

    def _bind(self, name, args, result):
        fn = getattr(self.dll,name)
        fn.argtypes, fn.restype = args, result
        return fn

    def _call(self, name, *args):
        C.set_last_error(0)
        result = getattr(self.dll,name)(*args)
        error = C.get_last_error()  # read before making another Windows API call
        self.log.add(name, result=int(result or 0), last_error=error,
                     last_error_text=C.FormatError(error).strip() if error else None)
        return result

    def _query(self, fn, category, index, cls):
        size = int(fn(category,index,None))
        if size != C.sizeof(cls):
            raise RuntimeError(f'WTInfo category={category} index={index}: size {size}, expected {C.sizeof(cls)}')
        # Query size first; never hand an undersized structure to WTInfo.
        buf = C.create_string_buffer(size)
        copied = int(fn(category,index,buf))
        if copied != size:
            raise RuntimeError(f'WTInfo category={category} index={index}: returned {copied}, expected {size}')
        return cls.from_buffer_copy(buf)

    def _initialize(self, hwnd):
        if os.name != 'nt':
            raise RuntimeError('Wintab requires Windows')
        if (C.sizeof(LOGCONTEXT),C.sizeof(LOGCONTEXTA),C.sizeof(AXIS),C.sizeof(PACKET)) != (212,172,16,12):
            raise RuntimeError('Unexpected Wintab ABI layout')
        self.user = C.WinDLL('user32',use_last_error=True)
        self.user.IsWindow.argtypes, self.user.IsWindow.restype = [W.HWND], W.BOOL
        self.user.GetAncestor.argtypes, self.user.GetAncestor.restype = [W.HWND,U32], W.HWND
        self.user.GetForegroundWindow.argtypes, self.user.GetForegroundWindow.restype = [], W.HWND
        self.own = self.user.GetAncestor(hwnd,2) or hwnd
        if not self.user.IsWindow(self.own):
            raise RuntimeError('Invalid top-level owner HWND')
        self.log.add('owner', hwnd=int(self.own), is_window=True)
        # Use the installed system driver, not a DLL beside the EXE.
        self.dll = C.WinDLL('Wintab32.dll',use_last_error=True,winmode=0x00000800)
        self._bind('WTClose',[W.HANDLE],W.BOOL)
        self._bind('WTEnable',[W.HANDLE,W.BOOL],W.BOOL)
        self._bind('WTOverlap',[W.HANDLE,W.BOOL],W.BOOL)
        self._bind('WTPacketsGet',[W.HANDLE,C.c_int,C.c_void_p],C.c_int)
        self._bind('WTQueueSizeSet',[W.HANDLE,C.c_int],W.BOOL)
        # W first; A is a bounded compatibility fallback, always paired with A ABI.
        for suffix, cls in [('W',LOGCONTEXT),('A',LOGCONTEXTA)]:
            try:
                info = self._bind('WTInfo'+suffix,[U32,U32,C.c_void_p],U32)
                self._bind('WTOpen'+suffix,[W.HWND,C.POINTER(cls),W.BOOL],W.HANDLE)
                self._bind('WTGet'+suffix,[W.HANDLE,C.POINTER(cls)],W.BOOL)
            except AttributeError as exc:
                self.log.add('api_unavailable',api=suffix,error=str(exc))
                continue
            try:
                caps = self._query(info,1,7,U32).value # IFC_CTXOPTIONS
                self.log.add('interface',api=suffix,context_options=caps,
                             ndevices=self._query(info,1,4,U32).value)
            except RuntimeError as exc:
                caps = None
                self.log.add('interface_query_warning',api=suffix,error=str(exc))
            for category in (WTI_DEFSYSCTX,WTI_DEFCONTEXT):
                try:
                    default = self._query(info,category,0,cls)
                    self.log.add('default_context',api=suffix,category=category,context=context_values(default))
                    ctx = prepare_context(default)
                    if category == WTI_DEFCONTEXT:
                        ctx.options &= ~CXO_SYSTEM
                    validate_context(ctx)
                    if caps is not None and ctx.options & ~caps:
                        raise RuntimeError(f'Default requests unsupported option bits: {ctx.options & ~caps:#x}')
                    supported = self._query(info,WTI_DEVICES+ctx.device,6,U32).value # DVC_PKTDATA
                    self.log.add('packet_capabilities',device=int(ctx.device),supported=supported,required=MASK)
                    if supported & MASK != MASK:
                        raise RuntimeError(f'Device lacks required X/Y/pressure packet bits: {MASK & ~supported:#x}')
                    axes = [self._query(info,WTI_DEVICES+ctx.device,index,AXIS) for index in (12,13,15)]
                    if any(a.maximum <= a.minimum for a in axes):
                        raise RuntimeError('Invalid device X/Y/normal-pressure axis')
                    self.log.add('axes',values=[{n:int(getattr(a,n)) for n,_ in AXIS._fields_} for a in axes])
                    self.log.add('open_attempt',api=suffix,category=category,enabled=False,context=context_values(ctx))
                    self.handle = self._call('WTOpen'+suffix,self.own,C.byref(ctx),False)
                    if not self.handle:
                        raise RuntimeError(f'WTOpen{suffix} returned NULL; cause not reported by Wintab')
                    # Open disabled, move to bottom BEFORE enabling. Never promote.
                    if not self._call('WTOverlap',self.handle,False):
                        raise RuntimeError('WTOverlap(FALSE) failed; refusing to enable context')
                    if not self._call('WTEnable',self.handle,True):
                        raise RuntimeError('WTEnable(TRUE) failed')
                    if not self._call('WTOverlap',self.handle,False):
                        raise RuntimeError('WTOverlap(FALSE) after enable failed')
                    effective = cls()
                    if not self._call('WTGet'+suffix,self.handle,C.byref(effective)):
                        raise RuntimeError('WTGet failed; cannot verify negotiated packet ABI')
                    self.log.add('effective_context',api=suffix,context=context_values(effective))
                    validate_context(effective)
                    if effective.options & (CXO_PEN | CXO_MESSAGES | CXO_CSRMESSAGES):
                        raise RuntimeError('Driver enabled unexpected pen-service/message options')
                    self.axes = axes
                    self.xscale, self.yscale = abs(effective.outextx),abs(effective.outexty)
                    self._call('WTQueueSizeSet',self.handle,256) # failure is advisory
                    self.buffer = (PACKET*256)()
                    self.count = self.background = self.contact_packets = self.max_pressure = 0
                    self.background_contact_packets = 0
                    self.log.add('context_opened',api=suffix,category=category,
                                 note='Creation only; foreground and OneNote background delivery still need separate tests.')
                    return
                except RuntimeError as exc:
                    self.close()
                    self.log.add('attempt_failed',api=suffix,category=category,error=str(exc))
        raise RuntimeError('All conservative Wintab context attempts failed. See startup diagnostics; background support is undetermined.')

    def poll(self):
        count = self.dll.WTPacketsGet(self.handle,256,self.buffer)
        if not 0 <= count <= 256:
            raise RuntimeError(f'Invalid WTPacketsGet count: {count}')
        now = time.perf_counter()
        background = self.user.GetForegroundWindow() != self.own
        pressure = 0.
        for p in self.buffer[:count]:
            self.count += 1
            self.background += int(background)
            a = self.axes[2]
            pressure = max(0.,min(1.,(p.pressure-a.minimum)/(a.maximum-a.minimum)))
            self.contact_packets += int(pressure > 0)
            self.background_contact_packets += int(background and pressure > 0)
            self.max_pressure = max(self.max_pressure,p.pressure)
        if count:
            p = self.buffer[count-1]
            self.tracker.update(p.x/self.xscale,p.y/self.yscale,pressure,pressure>0,now)

    def close(self):
        if getattr(self,'handle',None):
            handle, self.handle = self.handle, None
            self._call('WTClose',handle)
