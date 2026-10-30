"""Wintab ABI, polling a non-overlapping background context. Windows only."""
import ctypes as C
from ctypes import wintypes as W
import os
import time

class AXIS(C.Structure):
    _fields_ = [('minimum', C.c_int32), ('maximum', C.c_int32), ('units', C.c_uint32), ('resolution', C.c_uint32)]

class LOGCONTEXT(C.Structure):
    _fields_ = [('name', C.c_wchar*40)] + [(n, C.c_uint32) for n in ('options','status','locks','msgbase','device','pktrate','pktdata','pktmode','movemask','btndnmask','btnupmask')] + [(n,C.c_int32) for n in ('inorgx','inorgy','inorgz','inextx','inexty','inextz','outorgx','outorgy','outorgz','outextx','outexty','outextz')] + [(n,C.c_uint32) for n in ('sensx','sensy','sensz')] + [('sysmode',C.c_int32),('sysorgx',C.c_int32),('sysorgy',C.c_int32),('sysextx',C.c_int32),('sysexty',C.c_int32),('syssensx',C.c_uint32),('syssensy',C.c_uint32)]

# PK_X | PK_Y | PK_NORMAL_PRESSURE; fields MUST follow Wintab mask order.
MASK = 0x80 | 0x100 | 0x400
class PACKET(C.Structure):
    _fields_ = [('x',C.c_int32),('y',C.c_int32),('pressure',C.c_uint32)]

class Wintab:
    def __init__(self, hwnd, tracker):
        if os.name != 'nt':
            raise RuntimeError('Wintab requires Windows')
        self.tracker = tracker
        self.dll = C.WinDLL('Wintab32.dll')
        self.dll.WTInfoW.argtypes = [C.c_uint32,C.c_uint32,C.c_void_p]
        self.dll.WTInfoW.restype = C.c_uint32
        self.dll.WTOpenW.argtypes = [W.HWND,C.POINTER(LOGCONTEXT),W.BOOL]
        self.dll.WTOpenW.restype = W.HANDLE
        self.dll.WTPacketsGet.argtypes = [W.HANDLE,C.c_int,C.c_void_p]
        self.dll.WTPacketsGet.restype = C.c_int
        self.dll.WTClose.argtypes = [W.HANDLE]
        self.dll.WTClose.restype = W.BOOL
        self.dll.WTQueueSizeSet.argtypes = [W.HANDLE,C.c_int]
        self.dll.WTQueueSizeSet.restype = W.BOOL
        ctx = LOGCONTEXT()
        if not self.dll.WTInfoW(4,0,C.byref(ctx)): # WTI_DEFSYSCTX
            raise RuntimeError('WTI_DEFSYSCTX unavailable')
        ctx.name = 'PenASMR background observer'
        ctx.options |= 0x0002 | 0x0001 # CXO_PEN | CXO_SYSTEM
        ctx.options &= ~(0x0004 | 0x0008) # polling, no packet/cursor messages
        ctx.pktdata = ctx.movemask = MASK
        ctx.pktmode = 0 # absolute coordinates and pressure
        self.handle = self.dll.WTOpenW(hwnd,C.byref(ctx),True)
        if not self.handle:
            raise RuntimeError('WTOpenW failed: driver rejected background context')
        # Never WTOverlap(..., TRUE): do not promote above OneNote.
        self.dll.WTQueueSizeSet(self.handle,256)
        self.axes = []
        for index in (12,13,15): # DVC_X, DVC_Y, DVC_NPRESSURE
            axis = AXIS()
            if not self.dll.WTInfoW(100+ctx.device,index,C.byref(axis)) or axis.maximum <= axis.minimum:
                self.close()
                raise RuntimeError(f'Invalid Wintab device axis {index}')
            self.axes.append(axis)
        # Context output coordinates may differ from physical axis coordinates.
        self.xscale = max(1,abs(ctx.outextx))
        self.yscale = max(1,abs(ctx.outexty))
        self.buffer = (PACKET*256)()
        self.count = self.background = self.contact_packets = self.max_pressure = 0
        self.user = C.WinDLL('user32')
        self.user.GetForegroundWindow.restype = W.HWND
        self.user.GetAncestor.argtypes = [W.HWND,C.c_uint]
        self.user.GetAncestor.restype = W.HWND
        self.own = self.user.GetAncestor(hwnd,2) or hwnd

    def poll(self):
        count = self.dll.WTPacketsGet(self.handle,256,self.buffer)
        now = time.perf_counter()
        for p in self.buffer[:max(0,count)]:
            self.count += 1
            bg = self.user.GetForegroundWindow() != self.own
            self.background += int(bg)
            a = self.axes[2]
            pressure = max(0.,min(1.,(p.pressure-a.minimum)/(a.maximum-a.minimum)))
            self.contact_packets += int(pressure > 0)
            self.max_pressure = max(self.max_pressure,p.pressure)
            # Drain stale batches but derive motion only from their newest position.
        if count > 0:
            p = self.buffer[count-1]
            self.tracker.update(p.x/self.xscale,p.y/self.yscale,pressure,pressure>0,now)

    def close(self):
        if getattr(self,'handle',None):
            self.dll.WTClose(self.handle)
            self.handle = None
