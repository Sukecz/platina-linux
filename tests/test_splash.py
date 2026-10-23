"""Offline checks for release versions, decoded assets and padded fbdev rows."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


release = module('platina_release', 'scripts/platina-release.py')
splash = module('platina_splash', 'scripts/phone-splash.py')


class VersionTests(unittest.TestCase):
    def test_semantic_bumps(self):
        self.assertEqual(release.next_version('0.1.9', 'patch'), '0.1.10')
        self.assertEqual(release.next_version('0.1.9', 'minor'), '0.2.0')
        self.assertEqual(release.next_version('0.1.9', 'major'), '1.0.0')

    def test_bad_versions_rejected(self):
        for value in ('01.2.3', '1.2', '../1.2.3', '1.2.3\n', '1.2.3;reboot'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                release.version_tuple(value)

    def test_canonical_identity(self):
        self.assertEqual(release.load_release()['name'], 'Platina Linux')


class FramebufferTests(unittest.TestCase):
    def layout(self):
        variable = [0] * 40
        variable[:7] = [1080, 2280, 1080, 4560, 0, 2280, 32]
        variable[8:10], variable[11:13], variable[14:16] = [16, 8], [8, 8], [0, 8]
        fixed = bytearray(80)
        struct.pack_into('=I', fixed, 24, 4352 * 4560)
        struct.pack_into('=I', fixed, 48, 4352)
        return variable, fixed

    def test_stride_and_virtual_page_offset(self):
        variable, fixed = self.layout()
        result = splash.geometry(struct.pack('=40I', *variable), fixed)
        self.assertEqual(result, (1080, 2280, 4352, 4352 * 2280, 4352 * 4560))

    def test_wrong_pixel_order_rejected(self):
        variable, fixed = self.layout()
        variable[8] = 0
        with self.assertRaises(ValueError):
            splash.geometry(struct.pack('=40I', *variable), fixed)

    def test_too_small_mapping_rejected(self):
        variable, fixed = self.layout()
        struct.pack_into('=I', fixed, 24, 1024)
        with self.assertRaises(ValueError):
            splash.geometry(struct.pack('=40I', *variable), fixed)

    def test_row_padding_and_outside_viewport_preserved(self):
        target = bytearray(b'x' * 40)
        splash.paint(target, b'abcdEFGH', (1, 2, 8, 8, 40))
        self.assertEqual(target[8:12], b'abcd')
        self.assertEqual(target[16:20], b'EFGH')
        self.assertEqual(target[12:16], b'xxxx')
        self.assertEqual(target[:8], b'x' * 8)

    def test_real_bundle_valid_and_version_matches(self):
        directory = ROOT / ('artifacts/platina-linux-' + release.load_release()['version'])
        if not directory.exists():
            self.skipTest('Local generated release bundle is not part of clean source checkouts')
        manifest, raw = splash.load_frame(directory)
        self.assertEqual(manifest['version'], release.load_release()['version'])
        self.assertEqual(len(raw), 1080 * 2280 * 4)

    def test_corrupt_frame_rejected_before_hardware_access(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = {'schema': 1, 'name': 'Platina Linux', 'display': {
                'width': 1080, 'height': 2280, 'format': 'BGRX8888',
                'frame': 'frame.bgrx.gz', 'raw_bytes': 1080 * 2280 * 4,
                'compressed_sha256': '0' * 64, 'raw_sha256': '0' * 64}}
            (root / 'release.json').write_text(json.dumps(manifest))
            (root / 'frame.bgrx.gz').write_bytes(gzip.compress(b'wrong'))
            with self.assertRaisesRegex(ValueError, 'checksum'):
                splash.load_frame(root)

    def test_generated_poweroff_frame_is_separate_and_checksum_valid(self):
        try:
            import PIL
        except ImportError:
            self.skipTest('Host-only asset builder needs Pillow')
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / 'release'
            release.build(directory)
            boot, raw_boot = splash.load_frame(directory)
            shutdown, raw_shutdown = splash.load_frame(directory / 'poweroff')
            self.assertEqual(shutdown['purpose'], 'poweroff-screen')
            self.assertEqual(shutdown['version'], boot['version'])
            self.assertEqual(len(raw_shutdown), len(raw_boot))
            self.assertNotEqual(raw_shutdown, raw_boot)


if __name__ == '__main__':
    unittest.main()
