"""Small, local-first notebook. Coordinates are stored in page units."""
import copy
import json
import math
import os
from pathlib import Path
import uuid


def uid():
    return uuid.uuid4().hex


def distance(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    t = max(0, min(1, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy))) if dx or dy else 0
    return math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy)


def segments_distance(a, b, c, d):
    def cross(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    if cross(a,b,c)*cross(a,b,d) < 0 and cross(c,d,a)*cross(c,d,b) < 0:
        return 0
    return min(distance(a,c,d), distance(b,c,d), distance(c,a,b), distance(d,a,b))


def inside(p, polygon):
    hit = False
    for a, b in zip(polygon, polygon[1:]+polygon[:1]):
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:
            hit = not hit
    return hit


class Library:
    def __init__(self, path):
        self.path = Path(path)
        self.data = {'folders': [], 'notes': []}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(self.data.get('folders'), list) or not isinstance(self.data.get('notes'), list):
                raise ValueError('올바른 노트 파일이 아닙니다.')

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
        os.replace(temp, self.path)

    def folder(self, title, parent=None):
        item = dict(id=uid(), title=title, parent=parent)
        self.data['folders'].append(item)
        return item

    def note(self, title, folder=None):
        item = dict(id=uid(), title=title, folder=folder, pages=[[]])
        self.data['notes'].append(item)
        return item


class History:
    def __init__(self):
        self.undo = []
        self.redo = []

    def record(self, strokes):
        self.undo.append(copy.deepcopy(strokes))
        self.redo.clear()

    def step(self, strokes, reverse=False):
        source, target = (self.redo, self.undo) if reverse else (self.undo, self.redo)
        if source:
            target.append(copy.deepcopy(strokes))
            strokes[:] = source.pop()


def main():
    import tkinter as tk
    from tkinter import ttk, simpledialog, messagebox
    from .core import Tracker, Friction

    root = tk.Tk()
    root.title('종이 · 필기 노트')
    root.geometry('1280x900')
    path = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'PenNotes' / 'library.json'
    try:
        library = Library(path)
    except (ValueError, OSError) as exc:
        messagebox.showerror('노트 열기 실패', f'{path}\n{exc}\n원본 파일을 보존하고 종료합니다.')
        root.destroy()
        return
    if not library.data['notes']:
        library.note('첫 번째 노트')
    note = library.data['notes'][0]
    page = 0
    histories = {}
    selection = []
    gesture = None
    tool = tk.StringVar(value='펜')
    color = tk.StringVar(value='#202124')
    width = tk.DoubleVar(value=3)
    sound = tk.BooleanVar(value=False)
    volume = tk.DoubleVar(value=.3)
    status = tk.StringVar()
    page_label = tk.StringVar()
    tracker, engine = Tracker(), Friction()
    stream = None
    save_job = None

    def strokes():
        return note['pages'][page]

    def history():
        return histories.setdefault((note['id'], page), History())

    def save():
        nonlocal save_job
        save_job = None
        try:
            library.save()
            status.set(f'자동 저장됨 · {path}')
        except OSError as exc:
            status.set(f'저장 실패: {exc}')
            return False
        return True

    def changed():
        nonlocal save_job
        if save_job:
            root.after_cancel(save_job)
        status.set('저장 중…')
        save_job = root.after(400, save)

    side = ttk.Frame(root, padding=10)
    side.pack(side='left', fill='y')
    ttk.Label(side, text='나의 노트', font=('', 17, 'bold')).pack(anchor='w', pady=8)
    tree = ttk.Treeview(side, show='tree', selectmode='browse', height=25)
    tree.pack(fill='both', expand=True)
    main_frame = ttk.Frame(root)
    main_frame.pack(side='left', fill='both', expand=True)
    toolbar = ttk.Frame(main_frame, padding=8)
    toolbar.pack(fill='x')
    colors_frame = ttk.Frame(main_frame, padding=(8, 0))
    colors_frame.pack(fill='x')
    holder = ttk.Frame(main_frame)
    holder.pack(fill='both', expand=True, padx=8, pady=8)
    canvas = tk.Canvas(holder, bg='#fffef9', scrollregion=(0, 0, 1000, 1400), highlightthickness=0)
    sy = ttk.Scrollbar(holder, orient='vertical', command=canvas.yview)
    sx = ttk.Scrollbar(holder, orient='horizontal', command=canvas.xview)
    canvas.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
    sy.pack(side='right', fill='y')
    sx.pack(side='bottom', fill='x')
    canvas.pack(fill='both', expand=True)
    footer = ttk.Frame(main_frame, padding=8)
    footer.pack(fill='x')
    ttk.Label(root, textvariable=status, anchor='w').pack(side='bottom', fill='x')

    def rebuild():
        tree.delete(*tree.get_children())
        pending = list(library.data['folders'])
        while pending:
            ready = [f for f in pending if not f['parent'] or tree.exists(f['parent'])]
            if not ready:
                break
            for f in ready:
                tree.insert(f['parent'] or '', 'end', iid=f['id'], text='📁 '+f['title'], open=True)
                pending.remove(f)
        for n in library.data['notes']:
            tree.insert(n['folder'] or '', 'end', iid=n['id'], text='▤ '+n['title'])
        tree.selection_set(note['id'])

    def redraw():
        canvas.delete('all')
        for y in range(40, 1400, 32):
            canvas.create_line(0, y, 1000, y, fill='#ecece7')
        for i, s in enumerate(strokes()):
            points = s['points']
            coords = [v for p in points for v in p]
            if len(points) == 1:
                coords += coords
                coords[-1] += .01
            options = dict(fill=s['color'], width=s['width'], capstyle='round', joinstyle='round')
            if s['tool'] == '형광펜':
                options['stipple'] = 'gray50'
            canvas.create_line(*coords, **options)
        if selection:
            pts = [p for i in selection for p in strokes()[i]['points']]
            x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
            x1, y1 = max(p[0] for p in pts), max(p[1] for p in pts)
            canvas.create_rectangle(x0-8,y0-8,x1+8,y1+8,outline='#4263eb',dash=(5,3))
        page_label.set(f'{note["title"]} · {page+1} / {len(note["pages"])} 페이지')

    def choose(event=None):
        nonlocal note, page, gesture
        ids = tree.selection()
        target = next((n for n in library.data['notes'] if ids and n['id']==ids[0]), None)
        if target and target is not note:
            if gesture:
                release(None)
            note, page = target, 0
            selection.clear()
            redraw()

    tree.bind('<<TreeviewSelect>>', choose)

    def selected_folder():
        ids = tree.selection()
        if ids and any(f['id']==ids[0] for f in library.data['folders']):
            return ids[0]
        return note['folder']

    def new_item(folder=False):
        nonlocal note, page
        title = simpledialog.askstring('새 폴더' if folder else '새 노트', '이름', parent=root)
        if not title or not title.strip():
            return
        if folder:
            library.folder(title.strip(), selected_folder())
        else:
            note = library.note(title.strip(), selected_folder())
            page = 0
            selection.clear()
        rebuild()
        redraw()
        changed()

    def rename():
        ids = tree.selection()
        item = next((n for n in library.data['notes']+library.data['folders'] if ids and n['id']==ids[0]), None)
        if item:
            title = simpledialog.askstring('이름 변경', '이름', initialvalue=item['title'], parent=root)
            if title and title.strip():
                item['title'] = title.strip()
                rebuild(); redraw(); changed()

    def move():
        ids = tree.selection()
        item = next((n for n in library.data['notes']+library.data['folders'] if ids and n['id']==ids[0]), None)
        if not item:
            return
        dialog = tk.Toplevel(root)
        dialog.title('폴더로 이동')
        choices = ttk.Treeview(dialog, show='tree', height=15)
        choices.pack(fill='both', expand=True, padx=12, pady=12)
        choices.insert('', 'end', iid='ROOT', text='전체 노트', open=True)
        excluded = {item['id']}
        while True:
            more = {f['id'] for f in library.data['folders'] if f['parent'] in excluded}
            if more <= excluded: break
            excluded |= more
        pending = [f for f in library.data['folders'] if f['id'] not in excluded]
        while pending:
            ready = [f for f in pending if not f['parent'] or choices.exists(f['parent'])]
            if not ready: break
            for f in ready:
                choices.insert(f['parent'] or 'ROOT', 'end', iid=f['id'], text=f['title'], open=True)
                pending.remove(f)
        def apply():
            target = choices.selection()
            if target:
                item['folder' if 'pages' in item else 'parent'] = None if target[0]=='ROOT' else target[0]
                rebuild(); changed(); dialog.destroy()
        ttk.Button(dialog, text='이동', command=apply).pack(pady=8)

    for label, cmd in [('새 노트',lambda:new_item()),('새 폴더',lambda:new_item(True)),('이름 변경',rename),('폴더로 이동',move)]:
        ttk.Button(side,text=label,command=cmd).pack(fill='x', pady=3)

    def palette():
        for w in colors_frame.winfo_children(): w.destroy()
        values = [('검정','#202124'),('빨강','#e03131'),('파랑','#1971c2'),('초록','#2b8a3e'),('보라','#862e9c')]
        if tool.get()=='형광펜':
            values = [('노랑','#ffe600'),('빨강','#ff6060'),('파랑','#53a6ff'),('검정','#202124')]
        if color.get() not in [v for _,v in values]: color.set(values[0][1])
        for label, value in values:
            tk.Radiobutton(colors_frame,text=label,variable=color,value=value,fg=value,indicatoron=False,padx=12).pack(side='left',padx=2)
        ttk.Label(colors_frame,text='  올가미: 둘러싸기 → 선택 영역 드래그 / 크기 ±').pack(side='left')

    for label in ('펜','형광펜','획 지우개','올가미'):
        ttk.Radiobutton(toolbar,text=label,value=label,variable=tool,command=palette).pack(side='left',padx=3)
    ttk.Label(toolbar,text='두께').pack(side='left',padx=8)
    ttk.Scale(toolbar,from_=1,to=30,variable=width,length=100).pack(side='left')
    ttk.Label(toolbar,textvariable=width,width=5).pack(side='left')

    def undo(reverse=False):
        if gesture: return
        history().step(strokes(), reverse)
        selection.clear(); redraw(); changed()
    ttk.Button(toolbar,text='↶ 취소',command=undo).pack(side='left',padx=4)
    ttk.Button(toolbar,text='↷ 재실행',command=lambda:undo(True)).pack(side='left')

    def scale(factor):
        if not selection or gesture: return
        history().record(strokes())
        pts = [p for i in selection for p in strokes()[i]['points']]
        cx,cy = sum(p[0] for p in pts)/len(pts),sum(p[1] for p in pts)/len(pts)
        for i in selection:
            s=strokes()[i]
            s['points']=[[cx+(x-cx)*factor,cy+(y-cy)*factor] for x,y in s['points']]
            s['width']*=factor
        redraw(); changed()
    ttk.Button(footer,text='선택 −',command=lambda:scale(.9)).pack(side='left')
    ttk.Button(footer,text='선택 +',command=lambda:scale(1.1)).pack(side='left',padx=4)

    def audio():
        nonlocal stream
        engine.enabled = sound.get()
        if sound.get() and stream is None:
            try:
                import sounddevice as sd
                def callback(out, frames, timing, flags):
                    out[:] = engine.render(frames,tracker.motion)
                stream=sd.RawOutputStream(samplerate=48000,channels=1,dtype='float32',blocksize=256,callback=callback)
                stream.start()
            except Exception as exc:
                if stream:
                    stream.close(); stream=None
                sound.set(False); engine.enabled=False
                messagebox.showwarning('필기 소리',f'오디오 장치를 열 수 없습니다. 필기는 계속 사용할 수 있습니다.\n{exc}')
    ttk.Checkbutton(footer,text='필기 소리',variable=sound,command=audio).pack(side='left',padx=15)
    ttk.Scale(footer,from_=0,to=.8,variable=volume,length=90,command=lambda v:setattr(engine,'volume',float(v))).pack(side='left')
    engine.volume=.3
    engine.enabled=False

    def turn(delta=0, add=False):
        nonlocal page
        if gesture: return
        if add:
            note['pages'].append([])
            page=len(note['pages'])-1
            changed()
        else:
            page=max(0,min(len(note['pages'])-1,page+delta))
        selection.clear(); redraw()
        canvas.yview_moveto(0)
    ttk.Button(footer,text='＋ 페이지',command=lambda:turn(add=True)).pack(side='right')
    ttk.Button(footer,text='다음 ›',command=lambda:turn(1)).pack(side='right',padx=4)
    ttk.Label(footer,textvariable=page_label).pack(side='right',padx=10)
    ttk.Button(footer,text='‹ 이전',command=lambda:turn(-1)).pack(side='right')

    def point(e):
        return [max(0,min(1000,canvas.canvasx(e.x))),max(0,min(1400,canvas.canvasy(e.y)))]

    def press(e):
        nonlocal gesture
        p=point(e)
        mode=tool.get()
        if mode=='올가미' and selection:
            pts=[p for i in selection for p in strokes()[i]['points']]
            if min(a[0] for a in pts)-8<=p[0]<=max(a[0] for a in pts)+8 and min(a[1] for a in pts)-8<=p[1]<=max(a[1] for a in pts)+8:
                history().record(strokes())
                gesture=dict(mode='move',last=p)
                return
        selection.clear()
        if mode!='올가미': history().record(strokes())
        gesture=dict(mode=mode,points=[p],last=p)
        if mode in ('펜','형광펜'):
            strokes().append(dict(tool=mode,color=color.get(),width=width.get(),points=[p]))
            tracker.update(p[0]/1000,p[1]/1000,.6,True)
        elif mode=='획 지우개': erase(p,p)
        redraw()

    def erase(a,b):
        strokes()[:]=[s for s in strokes() if not any(segments_distance(a,b,p,q)<=width.get()/2+s['width']/2 for p,q in zip(s['points'],s['points'][1:]+s['points'][-1:]))]

    def drag(e):
        if not gesture: return
        p=point(e)
        mode=gesture['mode']
        if mode in ('펜','형광펜'):
            strokes()[-1]['points'].append(p)
            tracker.update(p[0]/1000,p[1]/1000,.6,True)
        elif mode=='획 지우개': erase(gesture['last'],p)
        elif mode=='move':
            dx,dy=p[0]-gesture['last'][0],p[1]-gesture['last'][1]
            for i in selection:
                strokes()[i]['points']=[[x+dx,y+dy] for x,y in strokes()[i]['points']]
        else: gesture['points'].append(p)
        gesture['last']=p
        redraw()
        if mode=='올가미' and len(gesture['points'])>1:
            canvas.create_line(*[v for p in gesture['points'] for v in p],fill='#4263eb',dash=(4,3))

    def release(e):
        nonlocal gesture
        if not gesture: return
        tracker.update(0,0,0,False)
        if gesture['mode']=='올가미':
            polygon=gesture['points']
            if len(polygon)>2:
                selection[:]=[i for i,s in enumerate(strokes()) if all(inside(p,polygon) for p in s['points'])]
        else: changed()
        gesture=None
        redraw()
    canvas.bind('<ButtonPress-1>',press)
    canvas.bind('<B1-Motion>',drag)
    canvas.bind('<ButtonRelease-1>',release)
    canvas.bind('<MouseWheel>',lambda e:canvas.yview_scroll(-1 if e.delta>0 else 1,'units'))
    canvas.bind('<Button-4>',lambda e:canvas.yview_scroll(-1,'units'))
    canvas.bind('<Button-5>',lambda e:canvas.yview_scroll(1,'units'))
    root.bind('<Control-z>',lambda e:undo())
    root.bind('<Control-y>',lambda e:undo(True))
    root.bind('<Control-s>',lambda e:save())

    def close():
        if gesture: release(None)
        if not save():
            messagebox.showerror('저장 실패','저장하지 못했습니다. 저장 경로와 디스크를 확인하세요.')
            return
        if stream: stream.stop(); stream.close()
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    palette(); rebuild(); redraw(); save()
    root.mainloop()
