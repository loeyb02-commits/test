import tempfile
import unittest
from pathlib import Path
from penasmr.notebook import Library, History, inside, distance, segments_distance


class NotebookTests(unittest.TestCase):
    def test_nested_folders_and_multiple_pages_survive_save(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'notes'/'library.json'
            lib = Library(path)
            parent = lib.folder('학교')
            child = lib.folder('수학', parent['id'])
            note = lib.note('미적분', child['id'])
            note['pages'][0].append(dict(tool='펜', color='#202124', width=3, points=[[1,2],[3,4]]))
            note['pages'].append([])
            lib.save()
            self.assertEqual(Library(path).data, lib.data)
            self.assertFalse(path.with_suffix('.tmp').exists())

    def test_history_snapshots_and_redo_branch(self):
        h=History()
        page=[]
        h.record(page)
        page.append({'points':[[1,2]]})
        h.step(page)
        self.assertEqual(page,[])
        h.step(page,True)
        self.assertEqual(page,[{'points':[[1,2]]}])
        h.record(page)
        page[0]['points'][0][0]=10
        h.step(page)
        self.assertEqual(page[0]['points'][0][0],1)
        h.record(page)
        self.assertFalse(h.redo)

    def test_lasso_and_eraser_geometry(self):
        self.assertEqual(segments_distance([0,5],[10,5],[5,0],[5,10]),0)
        polygon=[[0,0],[20,0],[20,20],[0,20]]
        self.assertTrue(inside([10,10],polygon))
        self.assertFalse(inside([30,10],polygon))
        self.assertEqual(distance([5,3],[0,0],[10,0]),3)
        self.assertEqual(distance([0,3],[0,0],[0,0]),3)

    def test_corrupt_library_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'library.json'
            path.write_text('broken')
            with self.assertRaises(ValueError): Library(path)
            self.assertEqual(path.read_text(),'broken')


class SelectionTests(unittest.TestCase):
    def test_any_contact_selects_whole_stroke(self):
        from penasmr.notebook import stroke_intersects_polygon
        box = [[0,0],[20,0],[20,20],[0,20]]
        def hit(points, width=2):
            return stroke_intersects_polygon({'points':points,'width':width},box)
        self.assertTrue(hit([[-10,10],[10,10]]))
        self.assertTrue(hit([[-10,10],[30,10]]))  # both sampled ends outside
        self.assertTrue(hit([[-10,-1],[30,-1]], 2))  # visible edge touches
        self.assertTrue(hit([[20,10]]))  # dot on boundary
        self.assertFalse(hit([[-10,-3],[30,-3]], 2))
        self.assertFalse(hit([[30,30],[40,40]]))
        self.assertFalse(stroke_intersects_polygon({'points':[[1,1]],'width':2},[]))


class RecordingCanvas:
    def __init__(self):
        self.next_id=0
        self.created=[]
        self.deleted=[]
        self.updated=[]

    def create_line(self,*coords,**kw):
        self.next_id+=1
        self.created.append((self.next_id,coords,kw))
        return self.next_id

    def canvasx(self,x): return x
    def canvasy(self,y): return y
    def winfo_width(self): return 1000
    def winfo_height(self): return 800
    def create_image(self,*coords,**kw):
        return self.create_line(*coords,**kw)

    def create_rectangle(self,*coords,**kw):
        return self.create_line(*coords,**kw)

    def delete(self,item):
        self.deleted.append(item)

    def coords(self,item,*coords):
        self.updated.append(item)

    def tag_raise(self,tag):
        pass

    def itemconfigure(self,item,**kw):
        pass


class RenderingTests(unittest.TestCase):
    def test_writing_keeps_background_and_existing_strokes(self):
        from penasmr.notebook import PageRenderer
        canvas=RecordingCanvas()
        renderer=PageRenderer(canvas)
        background_count=len(canvas.created)
        page=[dict(tool='펜',color='black',width=3,points=[[0,0]])]
        renderer.render(page,[])
        stroke_id=renderer.items[0]
        page[0]['points'].append([10,10])
        renderer.render(page,[])
        self.assertEqual(len(canvas.created),background_count+1)
        self.assertEqual(renderer.items,[stroke_id])
        self.assertIn(stroke_id,canvas.updated)
        self.assertNotIn(stroke_id,canvas.deleted)
        self.assertNotIn('all',canvas.deleted)
        renderer.render([],[])
        self.assertIn(stroke_id,canvas.deleted)
        self.assertEqual(renderer.items,[])


class InputTests(unittest.TestCase):
    def test_windows_touch_signature_keeps_pen_and_mouse(self):
        from penasmr.windows_input import is_touch_mouse
        self.assertTrue(is_touch_mouse(0xFF515780))
        self.assertTrue(is_touch_mouse(0xFF5157FF))
        self.assertTrue(is_touch_mouse(0xFF515780 - (1 << 32)))  # signed LPARAM
        self.assertFalse(is_touch_mouse(0xFF515700))  # pen
        self.assertFalse(is_touch_mouse(0))  # physical mouse
        self.assertFalse(is_touch_mouse(0x12345680))

    def test_note_reorder_and_folder_move_survive_reload(self):
        with tempfile.TemporaryDirectory() as d:
            lib=Library(Path(d)/'library.json')
            folder=lib.folder('폴더')
            a,b,c=[lib.note(name) for name in ('A','B','C')]
            lib.move_note(c['id'],before=a['id'])
            self.assertEqual([n['title'] for n in lib.data['notes']],['C','A','B'])
            lib.move_note(a['id'],folder['id'])
            lib.save()
            restored=Library(lib.path)
            self.assertEqual(restored.data,lib.data)
            self.assertEqual(restored.data['notes'][-1]['folder'],folder['id'])


class FolderAndButtonTests(unittest.TestCase):
    def test_folder_reordering_and_descendant_cycle_prevention(self):
        with tempfile.TemporaryDirectory() as d:
            lib=Library(Path(d)/'library.json')
            a=lib.folder('A')
            b=lib.folder('B')
            child=lib.folder('child',a['id'])
            lib.move_folder(b['id'],before=a['id'])
            self.assertEqual([f['title'] for f in lib.data['folders']],['B','A','child'])
            with self.assertRaises(ValueError): lib.move_folder(a['id'],child['id'])
            with self.assertRaises(ValueError): lib.move_folder(a['id'],a['id'])
            lib.apply_tree_order([b['id'],a['id'],child['id']])
            lib.save()
            self.assertEqual(Library(lib.path).data,lib.data)

    def test_right_button_detected_with_left_button_also_pressed(self):
        from penasmr.windows_input import right_button_pressed
        self.assertTrue(right_button_pressed(0x0400))
        self.assertTrue(right_button_pressed(0x0500))


class VectorEditingTests(unittest.TestCase):
    def test_corner_scale_is_relative_to_original_and_undoable(self):
        from penasmr.notebook import resize_strokes
        original=[dict(tool='펜',color='black',width=2,points=[[10,10],[20,20]])]
        scaled=resize_strokes(original,[0,0],[20,20],[40,40])
        self.assertEqual(scaled[0]['points'],[[20,20],[40,40]])
        self.assertEqual(scaled[0]['width'],4)
        self.assertEqual(original[0]['width'],2)
        restored=resize_strokes(original,[0,0],[20,20],[20,20])
        self.assertEqual(restored,original)

    def test_zoom_scales_raw_paths_without_changing_saved_points(self):
        from penasmr.notebook import PageRenderer
        canvas=RecordingCanvas()
        renderer=PageRenderer(canvas)
        stroke=dict(tool='펜',color='black',width=3,points=[[10,10],[10.2,10.3],[20,20]])
        renderer.render([stroke],[])
        self.assertEqual(canvas.created[-1][1],(10,10,10.2,10.3,20,20))
        self.assertFalse(canvas.created[-1][2]['smooth'])
        renderer.zoom=2
        renderer.render([stroke],[])
        self.assertEqual(stroke['points'],[[10,10],[10.2,10.3],[20,20]])
        self.assertEqual(renderer.snapshot[0][-1],2)

    def test_unchanged_page_and_panning_do_not_resubmit_paths(self):
        from penasmr.notebook import PageRenderer
        canvas=RecordingCanvas()
        renderer=PageRenderer(canvas)
        page=[dict(tool='펜',color='black',width=3,points=[[10,10],[20,20]]) for _ in range(200)]
        renderer.render(page,[])
        canvas.updated.clear()
        renderer.render(page,[])
        self.assertEqual(canvas.updated,[])
        page[-1]['points'].append([21,21])
        renderer.render(page,[])
        self.assertEqual(canvas.updated,[renderer.items[-1]])


class RadialZoomTests(unittest.TestCase):
    def test_radial_distance_controls_zoom_from_each_gesture_start(self):
        from penasmr.notebook import radial_zoom
        self.assertGreater(radial_zoom(1,(300,200),(400,200),(200,200)),1)
        self.assertLess(radial_zoom(1,(300,200),(250,200),(200,200)),1)
        self.assertEqual(radial_zoom(1,(300,200),(200,300),(200,200)),1)
        self.assertEqual(radial_zoom(2,(100,100),(100,100),(200,200)),2)
