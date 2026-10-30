import argparse
import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from .core import Tracker, Friction
from .wintab import Wintab, DiagnosticLog

def main():
    parser = argparse.ArgumentParser(description='PenASMR Wintab observer')
    parser.add_argument('--input-only',action='store_true',help='Test Wintab without opening an audio device')
    parser.add_argument('--hid-info',action='store_true',help='Save read-only HID inventory and exit; does not capture pen input')
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('Windows 11 and Wacom driver required. Run tests on Linux with unittest.')
    root = tk.Tk()
    root.title('PenASMR — Wacom' + (' [input only]' if args.input_only else ''))
    root.geometry('540x390')
    tracker, engine = Tracker(), Friction()
    backend = stream = None
    failures = 0
    config = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'PenASMR'
    diagnostics = DiagnosticLog(config / 'wintab-startup.json')
    if args.hid_info:
        from .rawhid_probe import enumerate_hid
        try:
            inventory = enumerate_hid()
        except Exception as exc:
            inventory = {'error':str(exc)}
        config.mkdir(parents=True,exist_ok=True)
        path = config / 'hid-inventory.json'
        path.write_text(json.dumps(inventory,indent=2),encoding='utf-8')
        messagebox.showinfo('HID inventory (not an input test)',str(path))
        root.destroy()
        return
    settings = config / 'settings.json'
    try:
        saved = json.loads(settings.read_text())
        for key, lo, hi in [('volume',0,1),('pressure_response',.2,3),('speed_response',.2,3)]:
            setattr(engine,key,max(lo,min(hi,float(saved.get(key,getattr(engine,key))))))
    except (OSError,ValueError,TypeError):
        pass
    engine.enabled = not args.input_only
    enabled = tk.BooleanVar(value=not args.input_only)
    ttk.Checkbutton(root,text='ASMR ON / OFF',variable=enabled,command=lambda:setattr(engine,'enabled',enabled.get())).pack(pady=10)
    for label,key,lo,hi in [('Volume','volume',0,1),('Pressure curve (higher = softer at low pressure)','pressure_response',.2,3),('Speed texture response','speed_response',.2,3)]:
        ttk.Label(root,text=label).pack()
        scale = ttk.Scale(root,from_=lo,to=hi,command=lambda v,k=key:setattr(engine,k,float(v)))
        scale.set(getattr(engine,key))
        scale.pack(fill='x',padx=20)
    status = tk.StringVar(value='Starting…')
    ttk.Label(root,textvariable=status,wraplength=500).pack(pady=12)
    errors = []
    def callback(out, frames, timing, flags):
        nonlocal failures
        if flags:
            failures += 1
        out[:] = engine.render(frames,tracker.motion)
    def report():
        config.mkdir(parents=True,exist_ok=True)
        data = dict(packets=backend.count if backend else 0,
                    background_packets=backend.background if backend else 0,
                    contact_packets=backend.contact_packets if backend else 0,
                    background_contact_packets=backend.background_contact_packets if backend else 0,
                    maximum_raw_pressure=backend.max_pressure if backend else 0,
                    audio_status_events=failures,errors=errors,
                    input_only=args.input_only,
                    wintab_startup=diagnostics.data,
                    startup_log_write_error=diagnostics.write_error,
                    note='Background means another window, not proof that OneNote was foreground. Follow README controlled test.')
        path = config / 'diagnostics.json'
        path.write_text(json.dumps(data,indent=2),encoding='utf-8')
        messagebox.showinfo('Diagnostics',str(path))
    ttk.Button(root,text='Save diagnostic report',command=report).pack()
    def close():
        if stream:
            stream.stop()
            stream.close()
        if backend:
            backend.close()
        config.mkdir(parents=True,exist_ok=True)
        settings.write_text(json.dumps({k:getattr(engine,k) for k in ('volume','pressure_response','speed_response')}))
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    root.update_idletasks()
    try:
        backend = Wintab(root.winfo_id(),tracker,diagnostics)
        if not args.input_only:
            import sounddevice as sd
            stream = sd.RawOutputStream(samplerate=48000,channels=1,dtype='float32',blocksize=256,latency='low',callback=callback)
            stream.start()
    except Exception as exc:
        errors.append(str(exc))
        diagnostics.add('application_startup_failed',error=str(exc))
        if backend:
            backend.close()
            backend = None
        status.set('Startup failed: '+str(exc))
        messagebox.showerror('Startup failed',str(exc))
    def poll():
        nonlocal backend
        if backend:
            try:
                backend.poll()
            except Exception as exc:
                errors.append(str(exc))
                diagnostics.add('input_stopped',error=str(exc))
                backend.close()
                backend = None
                engine.enabled = False
                status.set('Input stopped: '+str(exc))
                return
        root.after(4,poll)
    def refresh():
        if backend:
            status.set(f'Packets: {backend.count} | Background: {backend.background}\nContact: {backend.contact_packets} | BG contact: {backend.background_contact_packets} | Max pressure: {backend.max_pressure}\nAudio status events: {failures}. OneNote background delivery needs testing.')
        root.after(500,refresh)
    poll()
    refresh()
    root.mainloop()

if __name__ == '__main__':
    main()
