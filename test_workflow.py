import ast
from pathlib import Path
import queue
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock

source = (Path(__file__).resolve().parent / 'pro4.py').read_text(encoding='utf-8')
tree = ast.parse(source)
# Import-free execution lets the workflow be tested without a RAW codec or display.
tree.body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom, ast.If))]
ns = dict(Path=Path, queue=queue, tempfile=tempfile, threading=threading)
exec(compile(tree, 'pro4_improved.py', 'exec'), ns)
App = ns['RawDeveloperApp']

class Image:
    def save(self, stream, **kwargs):
        stream.write(b'jpeg-test')

class Raw:
    def __enter__(self): return self
    def __exit__(self, *args): pass

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.app = App.__new__(App)
        self.app.events = queue.Queue()
        self.app.cancel_event = threading.Event()
        ns['rawpy'] = types.SimpleNamespace(imread=Mock(return_value=Raw()))
        ns['process_with_preset'] = Mock(return_value='rgb')
        ns['apply_adjustments'] = Mock(return_value=Image())

    def test_collision_and_failed_save(self):
        save = ns['save_unique_jpeg']
        (self.folder / 'a.jpg').write_bytes(b'original')
        self.assertEqual(save(Image(), self.folder, 'a').name, 'a_1.jpg')
        self.assertEqual((self.folder / 'a.jpg').read_bytes(), b'original')
        broken = Mock()
        broken.save.side_effect = OSError('disk full')
        with self.assertRaises(OSError): save(broken, self.folder, 'a')
        self.assertFalse((self.folder / 'a_2.jpg').exists())

    def run_batch(self, folder=None):
        self.app._process_images(folder or self.folder, self.folder / 'out',
                                 ('vivid', 1, 1, 1))
        events = list(self.app.events.queue)
        return events[-1]

    def test_same_stem_and_mixed_case(self):
        (self.folder / 'a.Rw2').touch()
        (self.folder / 'a.NEF').touch()
        self.assertEqual(self.run_batch(), ('done', 2, 0, 0, False, None))
        self.assertEqual(len(list((self.folder / 'out').glob('*.jpg'))), 2)

    def test_cancel_after_decode(self):
        (self.folder / 'a.RW2').touch()
        def decode(*args):
            self.app.cancel_event.set()
            return 'rgb'
        ns['process_with_preset'].side_effect = decode
        self.assertEqual(self.run_batch(), ('done', 0, 0, 1, True, None))
        self.assertEqual(list((self.folder / 'out').glob('*.jpg')), [])

    def test_error_continues(self):
        (self.folder / 'a.RW2').touch()
        (self.folder / 'b.RW2').touch()
        ns['rawpy'].imread.side_effect = [ValueError('bad raw'), Raw()]
        self.assertEqual(self.run_batch(), ('done', 1, 1, 0, False, None))

    def test_invalid_folder(self):
        result = self.run_batch(self.folder / 'missing')
        self.assertEqual(result[0], 'done')
        self.assertIsNotNone(result[-1])

    def test_preview_error_is_captured(self):
        ns['rawpy'].imread.side_effect = ValueError('bad preview')
        self.app._load_preview('x', 'film', 5)
        self.assertEqual(self.app.events.get(), ('preview', 5, None, 'bad preview'))

    def test_preview_uses_requested_preset(self):
        self.app._load_preview('x', 'monochrome', 7)
        self.assertEqual(ns['process_with_preset'].call_args.args[1], 'monochrome')
        self.assertEqual(self.app.events.get(), ('preview', 7, 'rgb', None))

    def test_double_start_guard(self):
        self.app.processing = True
        self.app.start_processing()  # No Tk variables are accessed on repeat start.

    def test_stale_preview_is_ignored(self):
        self.app.preview_generation = 2
        self.app.preview_base_rgb = 'current'
        self.app.preview_busy = True
        self.app.closing = False
        self.app.root = Mock()
        self.app._start_pending_preview = Mock()
        self.app._update_preview = Mock()
        self.app.events.put(('preview', 1, 'stale', None))
        self.app._drain_events()
        self.assertEqual(self.app.preview_base_rgb, 'current')
        self.app._update_preview.assert_not_called()
        self.app._start_pending_preview.assert_called_once()

if __name__ == '__main__':
    unittest.main()

