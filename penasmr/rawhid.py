"""Experimental standard HID pen input; no Wintab, hooks or input reinjection.

Microsoft hidpi.h ABI. Only Wacom Digitizers/Pen collections with descriptor-
verified absolute X/Y, pressure and tip switch in one report/collection qualify.
"""
import ctypes as C
import os
import time
from .rawhid_probe import RAWINPUTDEVICELIST, DEVICEINFO, ERROR_RESULT
from .wintab import DiagnosticLog

U8,U16,U32,I32 = C.c_uint8,C.c_uint16,C.c_uint32,C.c_int32
PTR,UPTR,IPTR = C.c_void_p,C.c_size_t,C.c_ssize_t
SUCCESS = 0x00110000

class HIDP_CAPS(C.Structure):
    _fields_ = [(n,U16) for n in ('usage','page','input_bytes','output_bytes','feature_bytes')] + [('reserved',U16*17)] + [(n,U16) for n in ('links','input_buttons','input_values','input_indices','output_buttons','output_values','output_indices','feature_buttons','feature_values','feature_indices')]

_PREFIX = [('page',U16),('report',U8),('alias',U8),('bitfield',U16),('link',U16),('link_usage',U16),('link_page',U16),('is_range',U8),('string_range',U8),('designator_range',U8),('absolute',U8)]
class VALUE_CAP(C.Structure):
    _fields_ = _PREFIX + [('has_null',U8),('reserved',U8),('bits',U16),('count',U16),('reserved2',U16*5),('units_exp',U32),('units',U32),('minimum',I32),('maximum',I32),('physical_min',I32),('physical_max',I32),('details',U16*8)]
class BUTTON_CAP(C.Structure):
    _fields_ = _PREFIX + [('report_count',U16),('reserved2',U16),('reserved',U32*9),('details',U16*8)]
class HIDP_DATA(C.Structure):
    _fields_ = [('index',U16),('reserved',U16),('value',U32)]
class INPUT_HEADER(C.Structure):
    _fields_ = [('kind',U32),('size',U32),('device',PTR),('code',UPTR)]
class REGISTRATION(C.Structure):
    _fields_ = [('page',U16),('usage',U16),('flags',U32),('window',PTR)]

def data_index(cap, page, usage):
    if cap.alias or cap.page != page:
        return None
    if cap.is_range:
        if cap.details[0] <= usage <= cap.details[1]:
            index = cap.details[6]+usage-cap.details[0]
            return index if index <= cap.details[7] else None
    elif cap.details[0] == usage:
        return int(cap.details[6])
    return None

def select_fields(values, buttons):
    groups = {}
    for label,page,usage in [('x',1,0x30),('y',1,0x31),('pressure',13,0x30)]:
        for cap in values:
            index = data_index(cap,page,usage)
            if index is None or not cap.absolute or not 1 <= cap.bits <= 32 or cap.maximum <= cap.minimum:
                continue
            if not cap.is_range and cap.count != 1:
                continue
            fields = groups.setdefault((int(cap.report),int(cap.link)),{})
            if label in fields:
                raise RuntimeError('Ambiguous duplicate HID axis; descriptor needs device-specific review')
            fields[label] = dict(index=index,minimum=int(cap.minimum),maximum=int(cap.maximum),bits=int(cap.bits))
    for label,usage in [('tip',0x42),('in_range',0x32)]:
        for cap in buttons:
            index = data_index(cap,13,usage)
            if index is not None:
                fields=groups.setdefault((int(cap.report),int(cap.link)),{})
                if label in fields:
                    raise RuntimeError('Ambiguous duplicate HID button')
                fields[label]=dict(index=index)
    valid=[(key,fields) for key,fields in groups.items() if {'x','y','pressure','tip'} <= fields.keys()]
    if len(valid) != 1:
        raise RuntimeError('Need one unambiguous absolute X/Y/pressure/tip report in the same HID collection; split or vendor-specific reports are not guessed')
    return valid[0]

def signed_value(raw, field):
    raw &= (1 << field['bits'])-1
    if field['minimum'] < 0 and raw & (1 << (field['bits']-1)):
        raw -= 1 << field['bits']
    if not field['minimum'] <= raw <= field['maximum']:
        raise RuntimeError('HID value outside descriptor logical range')
    return raw

class PenDescriptor:
    def __init__(self, hid, preparsed, diagnostics=None):
        self.hid,self.preparsed=hid,preparsed
        caps=HIDP_CAPS()
        self.check(hid.HidP_GetCaps(preparsed,C.byref(caps)),'HidP_GetCaps')
        if diagnostics:
            diagnostics.add('hid_caps',page=int(caps.page),usage=int(caps.usage),
                            report_bytes=int(caps.input_bytes),value_caps=int(caps.input_values),
                            button_caps=int(caps.input_buttons),data_indices=int(caps.input_indices))
        if (caps.page,caps.usage) != (13,2) or not 1 <= caps.input_bytes <= 65535:
            raise RuntimeError('Unexpected HID pen collection/report length')
        if not 1 <= caps.input_values <= 512 or not 1 <= caps.input_buttons <= 512 or not 1 <= caps.input_indices <= 4096:
            raise RuntimeError('Unexpected HID capability counts')
        values=(VALUE_CAP*caps.input_values)(); n=U16(len(values))
        self.check(hid.HidP_GetValueCaps(0,values,C.byref(n),preparsed),'HidP_GetValueCaps')
        if n.value > len(values): raise RuntimeError('Invalid HID value capability count')
        buttons=(BUTTON_CAP*caps.input_buttons)(); nb=U16(len(buttons))
        self.check(hid.HidP_GetButtonCaps(0,buttons,C.byref(nb),preparsed),'HidP_GetButtonCaps')
        if nb.value > len(buttons): raise RuntimeError('Invalid HID button capability count')
        if diagnostics:
            def summary(cap):
                fields={name:int(getattr(cap,name)) for name in ('page','report','link','link_usage','link_page','is_range','absolute','alias')}
                fields.update(usage_min=int(cap.details[0]),usage_max=int(cap.details[1] if cap.is_range else cap.details[0]),
                              index_min=int(cap.details[6]),index_max=int(cap.details[7] if cap.is_range else cap.details[6]))
                if isinstance(cap,VALUE_CAP):
                    fields.update(bits=int(cap.bits),count=int(cap.count),minimum=int(cap.minimum),maximum=int(cap.maximum))
                return fields
            diagnostics.add('hid_report_layout',values=[summary(c) for c in values[:n.value]],
                            buttons=[summary(c) for c in buttons[:nb.value]],
                            note='Descriptor metadata only, not pen coordinates or report bytes.')
        self.report,self.link=None,None
        (self.report,self.link),self.fields=select_fields(values[:n.value],buttons[:nb.value])
        self.length=int(caps.input_bytes)
        self.data=(HIDP_DATA*caps.input_indices)()
        self.summary=dict(report_id=self.report,link=self.link,report_bytes=self.length,fields=self.fields)

    @staticmethod
    def check(status, operation):
        if status & 0xffffffff != SUCCESS:
            raise RuntimeError(f'{operation}: NTSTATUS {status & 0xffffffff:#010x}')

    def decode(self, report):
        if len(report) != self.length:
            raise RuntimeError(f'HID report length {len(report)}, descriptor expects {self.length}')
        if report[0] != self.report:
            return None # another report in the collection, not a pen sample
        raw=C.create_string_buffer(report,len(report)); n=U32(len(self.data))
        self.check(self.hid.HidP_GetData(0,self.data,C.byref(n),self.preparsed,raw,len(report)),'HidP_GetData')
        if n.value > len(self.data): raise RuntimeError('Invalid HID data count')
        entries={int(p.index):int(p.value) for p in self.data[:n.value]}
        coordinates=[]
        for name in ('x','y','pressure'):
            f=self.fields[name]
            if f['index'] not in entries:
                raise RuntimeError('HID report missing required '+name)
            v=signed_value(entries[f['index']],f)
            coordinates.append((v-f['minimum'])/(f['maximum']-f['minimum']))
        raw_pressure=signed_value(entries[self.fields['pressure']['index']],self.fields['pressure'])
        tip=bool(entries.get(self.fields['tip']['index'],0)&0xff)
        in_range='in_range' not in self.fields or bool(entries.get(self.fields['in_range']['index'],0)&0xff)
        return (*coordinates,tip and in_range and coordinates[2]>0,raw_pressure)

class BackgroundWindow:
    """Conservative transition exclusion; WM_INPUTSINK is also required."""
    def __init__(self, own):
        self.own=own; self.foreground=None; self.changed=0.
    def observe(self, foreground, now):
        if foreground != self.foreground:
            self.foreground,self.changed=foreground,now
    def stable(self, foreground, sink, now):
        self.observe(foreground,now)
        return bool(sink and foreground and foreground != self.own and now-self.changed >= .5)

class RawHID:
    name='rawhid'
    def __init__(self, hwnd, tracker, diagnostics=None):
        self.log=diagnostics if diagnostics is not None else DiagnosticLog()
        self.tracker=tracker
        self.count=self.background=self.contact_packets=self.background_contact_packets=self.max_pressure=0
        self.raw_messages=self.sink_messages=self.transition_packets=0
        self.subclassed=self.registered=False
        self.pending_error=None
        self.log.data.pop('initialization_revision',None)
        self.log.data.update(input_backend='rawhid',rawhid_revision=1,
                             abi={t.__name__:C.sizeof(t) for t in (HIDP_CAPS,VALUE_CAP,BUTTON_CAP,HIDP_DATA,INPUT_HEADER,REGISTRATION)})
        try:
            self._initialize(hwnd)
        except Exception as exc:
            self.close()
            self.log.add('rawhid_startup_failed',error=str(exc))
            raise RuntimeError(f'{exc}\nDiagnostics: {self.log.path}') from exc

    @staticmethod
    def bind(dll,name,args,result):
        fn=getattr(dll,name); fn.argtypes=args; fn.restype=result
        return fn

    def _initialize(self, hwnd):
        if os.name != 'nt': raise RuntimeError('Raw HID requires Windows')
        if [C.sizeof(t) for t in (HIDP_CAPS,VALUE_CAP,BUTTON_CAP,HIDP_DATA)] != [64,72,72,8]:
            raise RuntimeError('Unexpected HID ABI')
        self.user=C.WinDLL('user32',use_last_error=True)
        self.com=C.WinDLL('comctl32',use_last_error=True)
        self.hid=C.WinDLL('hid',use_last_error=True)
        self.bind(self.user,'GetAncestor',[PTR,U32],PTR)
        self.bind(self.user,'GetForegroundWindow',[],PTR)
        self.bind(self.user,'IsWindow',[PTR],I32)
        self.own=self.user.GetAncestor(hwnd,2) or hwnd
        if not self.user.IsWindow(self.own): raise RuntimeError('Invalid Raw Input owner window')
        self.attribution=BackgroundWindow(self.own)
        self.bind(self.user,'GetRawInputDeviceList',[C.POINTER(RAWINPUTDEVICELIST),C.POINTER(U32),U32],U32)
        self.bind(self.user,'GetRawInputDeviceInfoW',[PTR,U32,PTR,C.POINTER(U32)],U32)
        self.bind(self.user,'RegisterRawInputDevices',[C.POINTER(REGISTRATION),U32,U32],I32)
        self.bind(self.user,'GetRawInputData',[PTR,U32,PTR,C.POINTER(U32),U32],U32)
        self.bind(self.hid,'HidP_GetCaps',[PTR,C.POINTER(HIDP_CAPS)],I32)
        self.bind(self.hid,'HidP_GetValueCaps',[I32,C.POINTER(VALUE_CAP),C.POINTER(U16),PTR],I32)
        self.bind(self.hid,'HidP_GetButtonCaps',[I32,C.POINTER(BUTTON_CAP),C.POINTER(U16),PTR],I32)
        self.bind(self.hid,'HidP_GetData',[I32,C.POINTER(HIDP_DATA),C.POINTER(U32),PTR,PTR,U32],I32)
        count=U32()
        if self.user.GetRawInputDeviceList(None,C.byref(count),C.sizeof(RAWINPUTDEVICELIST)) == ERROR_RESULT:
            raise C.WinError(C.get_last_error())
        if count.value > 4096: raise RuntimeError('Unreasonable Raw Input device count')
        devices=(RAWINPUTDEVICELIST*count.value)()
        copied=self.user.GetRawInputDeviceList(devices,C.byref(count),C.sizeof(RAWINPUTDEVICELIST))
        if copied == ERROR_RESULT: raise C.WinError(C.get_last_error())
        if copied > len(devices): raise RuntimeError('Device list changed; restart')
        eligible=[]
        for entry in devices[:copied]:
            if entry.kind != 2: continue
            data=DEVICEINFO(); data.size=C.sizeof(data); size=U32(C.sizeof(data))
            returned=self.user.GetRawInputDeviceInfoW(entry.device,0x2000000b,C.byref(data),C.byref(size))
            if returned != C.sizeof(data) or data.kind != 2: continue
            ident=data.data.hid
            if (ident.vendor,ident.usage_page,ident.usage) != (0x056a,13,2): continue
            try:
                size=U32()
                if self.user.GetRawInputDeviceInfoW(entry.device,0x20000005,None,C.byref(size)) == ERROR_RESULT:
                    raise C.WinError(C.get_last_error())
                if not 1 <= size.value <= 1024*1024: raise RuntimeError('Invalid preparsed data length')
                preparsed=C.create_string_buffer(size.value)
                n=self.user.GetRawInputDeviceInfoW(entry.device,0x20000005,preparsed,C.byref(size))
                if n == ERROR_RESULT: raise C.WinError(C.get_last_error())
                if n != len(preparsed): raise RuntimeError('Preparsed data changed; restart')
                decoder=PenDescriptor(self.hid,preparsed,self.log)
                self.log.add('hid_descriptor',vendor=int(ident.vendor),product=int(ident.product),**decoder.summary)
                eligible.append((entry.device,decoder))
            except Exception as exc:
                self.log.add('hid_descriptor_rejected',vendor=int(ident.vendor),product=int(ident.product),error=str(exc))
        if len(eligible) != 1: raise RuntimeError('Need exactly one descriptor-verified Wacom pen collection; see HID descriptor log')
        self.device,self.decoder=eligible[0]
        callback_type=C.WINFUNCTYPE(IPTR,PTR,U32,UPTR,IPTR,UPTR,UPTR)
        self.callback=callback_type(self._window_message)
        self.bind(self.com,'SetWindowSubclass',[PTR,callback_type,UPTR,UPTR],I32)
        self.bind(self.com,'RemoveWindowSubclass',[PTR,callback_type,UPTR],I32)
        self.bind(self.com,'DefSubclassProc',[PTR,U32,UPTR,IPTR],IPTR)
        if not self.com.SetWindowSubclass(self.own,self.callback,0x5041534d,0):
            raise RuntimeError('SetWindowSubclass failed')
        self.subclassed=True
        registration=REGISTRATION(13,2,0x100|0x2000,self.own) # INPUTSINK | DEVNOTIFY
        if not self.user.RegisterRawInputDevices(C.byref(registration),1,C.sizeof(REGISTRATION)):
            raise C.WinError(C.get_last_error())
        self.registered=True
        self.log.add('rawhid_registered',backend='rawhid',flags=0x2100,
                     note='Registration only; actual background reports, contact and OneNote coexistence remain unverified.')

    def _window_message(self, hwnd, msg, wparam, lparam, subclass, ref):
        try:
            if msg == 0x00ff and self.pending_error is None: # WM_INPUT
                self._receive(lparam)
            elif msg == 0x00fe and wparam == 2 and lparam == self.device:
                self.pending_error='Wacom device removed; reconnect and restart PenASMR'
        except Exception as exc:
            self.pending_error=str(exc) # no Python exception may cross a Windows callback
        return self.com.DefSubclassProc(hwnd,msg,wparam,lparam)

    def _receive(self, handle):
        size=U32(); header_size=C.sizeof(INPUT_HEADER)
        if self.user.GetRawInputData(handle,0x10000003,None,C.byref(size),header_size) == ERROR_RESULT:
            raise C.WinError(C.get_last_error())
        if not header_size+8 <= size.value <= 1024*1024:
            raise RuntimeError('Invalid Raw Input size')
        buf=C.create_string_buffer(size.value)
        n=self.user.GetRawInputData(handle,0x10000003,buf,C.byref(size),header_size)
        if n == ERROR_RESULT: raise C.WinError(C.get_last_error())
        if n != len(buf): raise RuntimeError('Raw Input size changed')
        header=INPUT_HEADER.from_buffer_copy(buf)
        if header.kind != 2 or header.device != self.device: return
        self.raw_messages+=1
        if header.size != n: raise RuntimeError('Raw Input header length mismatch')
        length=U32.from_buffer_copy(buf,header_size).value
        count=U32.from_buffer_copy(buf,header_size+4).value
        if not length or not count or length*count != n-header_size-8:
            raise RuntimeError('Malformed RAWHID report array')
        now=time.perf_counter(); fg=self.user.GetForegroundWindow()
        sink=(header.code & 0xff)==1
        self.sink_messages+=int(sink)
        background=self.attribution.stable(fg,sink,now)
        latest=None
        payload=buf.raw
        for i in range(count):
            begin=header_size+8+i*length
            sample=self.decoder.decode(payload[begin:begin+length])
            if sample is None: continue
            x,y,pressure,contact,raw_pressure=sample
            self.count+=1; self.contact_packets+=int(contact)
            self.background+=int(background)
            self.background_contact_packets+=int(background and contact)
            self.transition_packets+=int(sink and not background)
            self.max_pressure=max(self.max_pressure,raw_pressure)
            # Batched reports have no individual timing here: update latest only.
            latest=(x,y,pressure,contact)
        if latest is not None: self.tracker.update(*latest,now)

    def poll(self):
        if self.pending_error: raise RuntimeError(self.pending_error)
        self.attribution.observe(self.user.GetForegroundWindow(),time.perf_counter())

    def close(self):
        if self.registered:
            registration=REGISTRATION(13,2,1,None) # RIDEV_REMOVE
            result=self.user.RegisterRawInputDevices(C.byref(registration),1,C.sizeof(REGISTRATION))
            self.log.add('rawhid_unregister',result=bool(result))
            self.registered=False
        if self.subclassed:
            result=self.com.RemoveWindowSubclass(self.own,self.callback,0x5041534d)
            if not result:
                _retained_callbacks.append(self) # keep callback alive until process exit
            self.log.add('rawhid_unsubclass',result=bool(result))
            self.subclassed=False

_retained_callbacks=[]
