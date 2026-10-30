"""Run with a display: PYTHONPATH=. python tests/gui_notebook_smoke.py"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import tkinter as tk
from tkinter import ttk
from penasmr.notebook import main, Library
errors=[]
def test(root):
    root.report_callback_exception=lambda *args:errors.append(args)
    def descendants(w):
        for child in w.winfo_children():
            yield child
            yield from descendants(child)
    root.update()
    widgets=list(descendants(root))
    canvas=next(w for w in widgets if isinstance(w,tk.Canvas))
    scales=[w for w in widgets if type(w) is tk.Scale]
    assert len(scales)==3
    add=next(w for w in widgets if isinstance(w,ttk.Button) and w.cget('text')=='＋ 페이지')
    before=(canvas.winfo_geometry(),add.winfo_rootx(),add.winfo_rooty())
    count=len(canvas.find_all())
    canvas.event_generate('<ButtonPress-1>',x=100,y=100)
    for x in range(110,300,10):
        canvas.event_generate('<B1-Motion>',x=x,y=110)
        root.update()
    canvas.event_generate('<ButtonRelease-1>',x=300,y=110)
    root.update()
    assert len(canvas.find_all())==count+1
    after=(canvas.winfo_geometry(),add.winfo_rootx(),add.winfo_rooty())
    assert before==after,(before,after)
    pen,marker,eraser=scales
    pen.set(6.5); root.update()
    assert marker.get()==16 and eraser.get()==12
    # Real thumb drag: test both near endpoints, with half-unit quantization.
    x,y=marker.coords(marker.get())
    marker.event_generate('<ButtonPress-1>',x=x,y=y)
    marker.event_generate('<B1-Motion>',x=x+35,y=y)
    marker.event_generate('<ButtonRelease-1>',x=x+35,y=y)
    root.update()
    assert marker.get()>16,marker.get()
    assert pen.get()==6.5
    assert marker.get()*2==int(marker.get()*2)
    for mode in ('형광펜','펜','올가미'):
        next(w for w in widgets if isinstance(w,ttk.Radiobutton) and w.cget('text')==mode).invoke()
        root.update()
    assert pen.get()==6.5 and marker.get()>16
    pen_button=next(w for w in widgets if isinstance(w,ttk.Radiobutton) and w.cget('text')=='펜')
    pen_button.invoke()
    # Right-drag deletes a whole stroke and does not change the selected tool.
    canvas.event_generate('<ButtonPress-3>',x=100,y=100)
    canvas.event_generate('<B3-Motion>',x=150,y=110)
    canvas.event_generate('<ButtonRelease-3>',x=150,y=110)
    root.update()
    assert len(canvas.find_all())==count
    assert root.getvar(pen_button.cget('variable'))=='펜'
    next(w for w in widgets if isinstance(w,ttk.Button) and w.cget('text')=='↶ 취소').invoke()
    root.update()
    assert len(canvas.find_all())==count+1
    # Hold right, then press/drag the pen tip (left) while pen stays selected.
    canvas.event_generate('<ButtonPress-3>',x=600,y=100)
    canvas.event_generate('<ButtonPress-1>',x=100,y=100,state=0x400)
    canvas.event_generate('<B1-Motion>',x=150,y=110,state=0x500)
    canvas.event_generate('<ButtonRelease-1>',x=150,y=110,state=0x500)
    canvas.event_generate('<ButtonRelease-3>',x=150,y=110)
    root.update()
    assert len(canvas.find_all())==count
    assert root.getvar(pen_button.cget('variable'))=='펜'
    next(w for w in widgets if isinstance(w,ttk.Button) and w.cget('text')=='↶ 취소').invoke()
    root.update()
    assert len(canvas.find_all())==count+1
    # Tool shortcuts, including uppercase and restoring pen.
    canvas.focus_force(); root.update()
    for key,expected in [('v','올가미'),('e','획 지우개'),('S','펜')]:
        canvas.event_generate('<KeyPress-'+key+'>'); root.update()
        assert root.getvar(pen_button.cget('variable'))==expected
    add.invoke(); root.update()
    assert len(canvas.find_all())==count
    canvas.focus_force(); root.update()
    canvas.event_generate('<Left>'); root.update()
    assert len(canvas.find_all())==count+1
    canvas.event_generate('<Right>'); root.update()
    assert len(canvas.find_all())==count
    # Going next from the last page creates exactly one page.
    next_page=next(w for w in widgets if isinstance(w,ttk.Button) and w.cget('text')=='다음 ›')
    next_page.invoke(); root.update()
    assert len(canvas.find_all())==count
    canvas.event_generate('<Left>'); root.update()
    canvas.event_generate('<Right>'); root.update()
    # Drag the paper without creating ink.
    canvas.yview_moveto(.4)
    old=canvas.yview()
    canvas.event_generate('<KeyPress-space>')
    canvas.event_generate('<ButtonPress-1>',x=200,y=200)
    canvas.event_generate('<B1-Motion>',x=200,y=300)
    canvas.event_generate('<ButtonRelease-1>',x=200,y=300)
    canvas.event_generate('<KeyRelease-space>')
    root.update()
    assert canvas.yview()[0]<old[0]
    assert len(canvas.find_all())==count
    # Notes visibly follow the drag, and their new order is persisted.
    from tkinter import simpledialog
    with patch.object(simpledialog,'askstring',return_value='두 번째 노트'):
        next(w for w in widgets if isinstance(w,ttk.Button) and w.cget('text')=='새 노트').invoke()
    root.update()
    tree=next(w for w in widgets if isinstance(w,ttk.Treeview))
    first,second=tree.get_children('')
    x0,y0,w0,h0=tree.bbox(first)
    x1,y1,w1,h1=tree.bbox(second)
    tree.event_generate('<ButtonPress-1>',x=60,y=y1+h1//2)
    tree.event_generate('<B1-Motion>',x=60,y=y0+1)
    root.update()
    assert tree.get_children('')[0]==second
    assert any(w.winfo_manager()=='place' for w in tree.winfo_children())
    tree.event_generate('<ButtonRelease-1>',x=60,y=y0+1)
    root.update()
    # Folder edges reorder folders; centres accept notes at the top.
    new_folder=next(w for w in widgets if isinstance(w,ttk.Button) and w.cget('text')=='새 폴더')
    for title in ('폴더 A','폴더 B'):
        with patch.object(simpledialog,'askstring',return_value=title):
            new_folder.invoke()
        root.update()
    folder_a,folder_b=tree.get_children('')[:2]
    def drag_row(row,target,centre=False):
        _,y,_,h=tree.bbox(row)
        _,ty,_,th=tree.bbox(target)
        tree.event_generate('<ButtonPress-1>',x=60,y=y+h//2)
        tree.event_generate('<B1-Motion>',x=60,y=ty+(th//2 if centre else 1))
        root.update()
        tree.event_generate('<ButtonRelease-1>',x=60,y=ty+(th//2 if centre else 1))
        root.update()
    drag_row(folder_b,folder_a)
    assert tree.get_children('')[:2]==(folder_b,folder_a)
    tree.selection_set(folder_b); root.update()
    with patch.object(simpledialog,'askstring',return_value='기존 폴더 노트'):
        next(w for w in widgets if isinstance(w,ttk.Button) and w.cget('text')=='새 노트').invoke()
    root.update()
    old_child=tree.get_children(folder_b)[0]
    drag_row(second,folder_b,centre=True)
    assert tree.get_children(folder_b)==(second,old_child)
    root.tk.call(root.protocol('WM_DELETE_WINDOW'))
    data=Library(Path(os.environ['LOCALAPPDATA'])/'PenNotes/library.json').data
    original=next(n for n in data['notes'] if n['title']=='첫 번째 노트')
    assert len(original['pages'])==3
    assert len(original['pages'][0])==1
    assert data['folders'][0]['id']==folder_b
    assert data['order'].index(second)<data['order'].index(old_child)
    assert next(n for n in data['notes'] if n['id']==second)['folder']==folder_b
    assert not errors,errors
    print('GUI PASS: held-right + pen eraser, shortcuts, auto page, folder reorder, top insertion, drawing, sliders and save')
if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as data_dir:
        with patch.dict(os.environ, {'LOCALAPPDATA': data_dir}), patch.object(tk.Tk, 'mainloop', test):
            main()
