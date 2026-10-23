"""Protect kernel/cmdline identity and reject unsafe boot/archive inputs."""
import gzip
import hashlib
import importlib.util
from pathlib import Path
import stat
import struct
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('scope_initramfs', Path(__file__).resolve().parents[1] / 'scripts/scope-initramfs-modules.py')
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


def boot_image(ramdisk=b'old ramdisk'):
    kernel = b'kernel and appended device tree'
    header = bytearray(4096)
    header[:8] = b'ANDROID!'
    struct.pack_into('<10I', header, 8, len(kernel), 32768, len(ramdisk), 16777216, 0, 15728640, 256, 4096, 0, 0)
    cmdline = b'console=ttyMSM0'
    header[64:64 + len(cmdline)] = cmdline
    header[576:596] = hashlib.sha1(kernel + struct.pack('<I', len(kernel)) + ramdisk + struct.pack('<I', len(ramdisk)) + b'\0' * 4).digest()
    return bytes(header) + kernel.ljust(4096, b'\0') + ramdisk.ljust((len(ramdisk) + 4095) // 4096 * 4096, b'\0')


class BootTests(unittest.TestCase):
    def test_replacement_preserves_kernel_and_cmdline(self):
        before = boot_image()
        changed = scope.replace_ramdisk(before, b'new ramdisk' * 900)
        kernel, ramdisk, _ = scope.parts(changed)
        self.assertEqual(kernel, scope.parts(before)[0])
        self.assertEqual(ramdisk, b'new ramdisk' * 900)
        self.assertEqual(changed[64:576], before[64:576])
        self.assertEqual(changed[608:1632], before[608:1632])

    def test_corrupt_payload_rejected(self):
        bad = bytearray(boot_image())
        bad[4096] ^= 1
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            scope.replace_ramdisk(bad, b'new')

    def test_unknown_trailer_rejected(self):
        with self.assertRaisesRegex(ValueError, 'trailer'):
            scope.parts(boot_image() + b'unknown footer')

    def test_unsupported_header_rejected(self):
        bad = bytearray(boot_image())
        struct.pack_into('<I', bad, 40, 4)
        with self.assertRaisesRegex(ValueError, 'layout'):
            scope.parts(bad)

    def test_unsafe_archive_path_rejected(self):
        record = ('../escape', [0, stat.S_IFREG | 0o600, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], b'data')
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            scope.unpack(scope.pack([record]))

    def test_scoped_index_must_match_actual_modules(self):
        prefix = 'lib/modules/7.2.12-sdm660/'
        fields = [0, stat.S_IFREG | 0o644, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        records = [(prefix + 'kernel/fixture.ko.zst', fields, b'fixture')]
        boot = boot_image(gzip.compress(scope.pack(records)))

        def wrong_index(command, **kwargs):
            target = Path(command[4]) / 'lib/modules/7.2.12-sdm660'
            (target / 'modules.dep').write_text('kernel/absent.ko.zst:\n')

        with patch.object(scope.subprocess, 'run', side_effect=wrong_index):
            with self.assertRaisesRegex(ValueError, 'differs'):
                scope.scope(boot, '7.2.12-sdm660')


if __name__ == '__main__':
    unittest.main()
