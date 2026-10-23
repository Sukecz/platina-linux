"""Exercise the actual image overlay and reject missing/corrupt runtime assets."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('image_runtime', ROOT / 'scripts/image-runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class ImageRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import PIL
        except ImportError:
            raise unittest.SkipTest('Asset integration requires host Pillow')
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.overlay = Path(cls.temp.name) / 'overlay'
        with contextlib.redirect_stdout(io.StringIO()):
            cls.result = runtime.prepare(cls.overlay)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'rootfs'
        shutil.copytree(self.overlay, self.root, symlinks=True)

    def test_complete_overlay_has_both_screens_and_active_shutdown(self):
        self.assertEqual(runtime.audit(self.root), self.result)
        self.assertEqual(self.result['screens_verified'], 2)
        self.assertTrue((self.root / 'etc/runlevels/default/platina-power-chord').is_file())
        self.assertIn('dry_run=no', (self.root / runtime.CONFIG).read_text())
        self.assertEqual((self.root / 'etc/platina-release').read_text(),
                         'Platina Linux ' + self.result['version'] + '\n')
        files = {str(p.relative_to(self.root)) for p in self.root.rglob('*') if p.is_file()}
        self.assertFalse(any('usb-off' in name or name.endswith('.ko') for name in files))
        self.assertTrue((self.root / 'etc/NetworkManager/dispatcher.d/90-platina-usb-power').is_file())
        self.assertFalse((self.root / 'etc/platina/usb-power.json').exists())

    def test_missing_shutdown_helper_is_rejected(self):
        (self.root / 'usr/local/sbin/platina-poweroff').unlink()
        with self.assertRaises(FileNotFoundError):
            runtime.audit(self.root)

    def test_corrupt_poweroff_frame_is_rejected(self):
        frame = next(self.root.glob('usr/local/share/platina/releases/*/poweroff/frame.bgrx.gz'))
        frame.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            runtime.audit(self.root)

    def test_inactive_shutdown_or_bad_permissions_are_rejected(self):
        (self.root / 'usr/local/sbin/platina-power-chord').chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'mode/type'):
            runtime.audit(self.root)

    def test_service_not_enabled_is_rejected(self):
        (self.root / 'etc/runlevels/default/platina-power-chord').unlink()
        with self.assertRaisesRegex(ValueError, 'symlink'):
            runtime.audit(self.root)

    def test_manifest_cannot_add_unrelated_or_traversing_files(self):
        path = self.root / runtime.MANIFEST
        manifest = json.loads(path.read_text())
        manifest['files']['../../outside'] = {'mode': 0o644, 'bytes': 0, 'sha256': '0' * 64}
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'file set'):
            runtime.audit(self.root)

    def test_prepare_refuses_existing_output(self):
        with self.assertRaisesRegex(ValueError, 'Preserve'):
            runtime.prepare(self.root)


if __name__ == '__main__':
    unittest.main()
