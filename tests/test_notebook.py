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
