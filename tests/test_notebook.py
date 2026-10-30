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

    def create_rectangle(self,*coords,**kw):
        return self.create_line(*coords,**kw)

    def delete(self,item):
        self.deleted.append(item)

    def coords(self,item,*coords):
        self.updated.append(item)

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
