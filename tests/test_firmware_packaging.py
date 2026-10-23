"""Check deterministic local firmware packaging without distributing firmware payloads."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


firmware = load('prepare_firmware', 'scripts/prepare-firmware.py')


class FirmwarePackagingTests(unittest.TestCase):
    def test_archive_does_not_depend_on_host_mtime(self):
        import os
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            source = path / 'example'
            source.write_bytes(b'fixture')
            first = firmware.archive_files(path, 'modem')
            os.utime(source, (1, 1))
            self.assertEqual(first, firmware.archive_files(path, 'modem'))

    def test_public_board_helper_indexes_aliases_and_rejects_empty_input(self):
        relative = Path('ports/candidate/firmware-xiaomi-platina/gen-board-2.py')
        overlay = Path('project/public/files') / relative
        if (ROOT / overlay).exists():
            relative = overlay
        if not (ROOT / relative).exists():
            self.skipTest('Public packaging helper is tested in the public export')
        helper = load('board_index', relative)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            with self.assertRaises(ValueError):
                helper.index(path)
            for name in ('bdwlan.bin', 'bdwlan.b33', 'bdwlan.102', 'bdwlan.unknown'):
                (path / name).write_bytes(b'fixture')
            indexed = {row['data']: row['names'] for row in helper.index(path)}
            self.assertEqual(indexed['bdwlan.b33'], ['bus=snoc,qmi-board-id=33'])
            self.assertEqual(indexed['bdwlan.102'], ['bus=snoc,qmi-board-id=102'])
            self.assertEqual(indexed['bdwlan.bin'], ['bus=snoc', 'bus=snoc,qmi-board-id=ff', 'bus=snoc,qmi-board-id=0'])
            self.assertNotIn('bdwlan.unknown', indexed)


if __name__ == '__main__':
    unittest.main()
