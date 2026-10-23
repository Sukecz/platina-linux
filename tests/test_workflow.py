"""Offline regression tests for artifact integrity and isolated build preparation."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('project_workflow', Path(__file__).resolve().parents[1] / 'scripts/project.py')
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / 'bundle'
        self.bundle.mkdir()
        self.payload = b'audited boot payload'
        (self.bundle / 'boot.img').write_bytes(self.payload)
        self.row = {'file': 'boot.img', 'bytes': len(self.payload),
                    'sha256': hashlib.sha256(self.payload).hexdigest()}

    def verify(self, rows=None):
        (self.bundle / 'manifest.json').write_text(json.dumps({'files': rows if rows is not None else [self.row]}))
        with contextlib.redirect_stdout(io.StringIO()):
            workflow.verify(self.bundle)

    def test_valid_bundle(self):
        self.verify()

    def test_same_length_corruption(self):
        (self.bundle / 'boot.img').write_bytes(b'X' * len(self.payload))
        with self.assertRaisesRegex(ValueError, 'verification failed'):
            self.verify()

    def test_wrong_length(self):
        self.row['bytes'] += 1
        with self.assertRaisesRegex(ValueError, 'verification failed'):
            self.verify()

    def test_path_traversal(self):
        self.row['file'] = '../boot.img'
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            self.verify()

    def test_absolute_path(self):
        self.row['file'] = str(self.bundle / 'boot.img')
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            self.verify()

    def test_symlink(self):
        (self.bundle / 'alias.img').symlink_to('boot.img')
        self.row['file'] = 'alias.img'
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.verify()

    def test_duplicate_files(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.verify([self.row, self.row])

    def test_empty_manifest(self):
        with self.assertRaisesRegex(ValueError, 'nonempty'):
            self.verify([])

    def test_missing_file(self):
        (self.bundle / 'boot.img').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing'):
            self.verify()


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(workflow, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.source = self.root / 'sources/pmaports-server'
        self.source.mkdir(parents=True)
        self.git('init', '-q')
        (self.source / 'upstream.txt').write_text('original\n')
        self.git('add', 'upstream.txt')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
        commit = self.git('rev-parse', 'HEAD').strip()
        # Preserve both staged and unstaged edits, like the actual working source.
        (self.source / 'upstream.txt').write_text('staged\n')
        self.git('add', 'upstream.txt')
        (self.source / 'upstream.txt').write_text('unstaged\n')
        self.initial_index = self.git('diff', '--cached')
        self.initial_work = self.git('diff')
        (self.root / 'config/firmware').mkdir(parents=True)
        (self.root / 'config/admin-test.pub').write_text('fixture public key\n')
        (self.root / 'project').mkdir()
        for name in workflow.RECIPES:
            directory = self.root / 'ports/candidate' / name
            directory.mkdir(parents=True)
            (directory / 'input.txt').write_text(name)
            checksum = workflow.digest(directory / 'input.txt', 'sha512')
            (directory / 'APKBUILD').write_text('sha512sums="\n' + checksum + '  input.txt\n"\n')
        blob = self.root / 'config/firmware/local.tar.gz'
        blob.write_bytes(b'local fixture firmware')
        recipe = self.root / 'ports/candidate/firmware-xiaomi-platina/APKBUILD'
        recipe.write_text(recipe.read_text().replace('\n"\n', '\n' + workflow.digest(blob, 'sha512') + '  local.tar.gz\n"\n'))
        data = {'schema': 1, 'repositories': {
            'pmbootstrap': {'path': 'sources/pmaports-server', 'commit': commit, 'url': 'unused'},
            'pmaports': {'commit': commit, 'channels_commit': commit, 'url': 'unused'}},
            'profiles': {'candidate': {'ports': 'ports/candidate'}}, 'local_firmware': ['local.tar.gz']}
        (self.root / 'project/sources.lock.json').write_text(json.dumps(data))

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.source), *args], text=True)

    def test_prepare_preserves_existing_tree_and_generates_absolute_config(self):
        with contextlib.redirect_stdout(io.StringIO()):
            workflow.prepare('candidate', False)
        self.assertEqual(self.git('diff', '--cached'), self.initial_index)
        self.assertEqual(self.git('diff'), self.initial_work)
        cfg = workflow.config_path('candidate').read_text()
        self.assertIn(str(self.root / 'sources/pmaports-managed-candidate'), cfg)
        self.assertIn(str(self.root / 'work/pmbootstrap-managed-candidate'), cfg)
        self.assertEqual((self.root / 'sources/pmaports-managed-candidate/upstream.txt').read_text(), 'original\n')
        managed = str(self.root / 'sources/pmaports-managed-candidate')
        self.assertEqual(subprocess.check_output(['git', '-C', managed, 'remote', 'get-url', 'origin'], text=True).strip(), 'unused')
        self.assertEqual(subprocess.check_output(['git', '-C', managed, 'rev-parse', 'origin/main'], text=True).strip(), self.git('rev-parse', 'HEAD').strip())
        with self.assertRaisesRegex(ValueError, 'already exists'):
            workflow.prepare('candidate', False)

    def test_missing_blob_fails_before_checkout(self):
        (self.root / 'config/firmware/local.tar.gz').unlink()
        with self.assertRaisesRegex(ValueError, 'firmware'):
            workflow.prepare('candidate', False)
        self.assertFalse((self.root / 'sources/pmaports-managed-candidate').exists())

    def test_changed_recipe_fails_before_checkout(self):
        (self.root / 'ports/candidate/device-xiaomi-platina/input.txt').write_text('modified')
        with self.assertRaisesRegex(ValueError, 'Recipe input'):
            workflow.prepare('candidate', False)
        self.assertFalse((self.root / 'sources/pmaports-managed-candidate').exists())

    def test_sync_refuses_to_overwrite_local_edits(self):
        with contextlib.redirect_stdout(io.StringIO()):
            workflow.prepare('candidate', False)
        target = self.root / 'sources/pmaports-managed-candidate/device/testing/device-xiaomi-platina/input.txt'
        target.write_text('important local change')
        with self.assertRaisesRegex(ValueError, 'edited locally'):
            workflow.sync('candidate')
        self.assertEqual(target.read_text(), 'important local change')

    def test_sync_applies_verified_snapshot_change(self):
        with contextlib.redirect_stdout(io.StringIO()):
            workflow.prepare('candidate', False)
        source = self.root / 'ports/candidate/device-xiaomi-platina/input.txt'
        source.write_text('reviewed update')
        (source.parent / 'APKBUILD').write_text('sha512sums="\n' + workflow.digest(source, 'sha512') + '  input.txt\n"\n')
        with contextlib.redirect_stdout(io.StringIO()):
            workflow.sync('candidate')
        target = self.root / 'sources/pmaports-managed-candidate/device/testing/device-xiaomi-platina/input.txt'
        self.assertEqual(target.read_text(), 'reviewed update')
        self.assertEqual(self.git('diff', '--cached'), self.initial_index)

    def test_concurrent_build_rejected(self):
        with workflow.build_slot():
            with self.assertRaisesRegex(ValueError, 'running'):
                with workflow.build_slot():
                    self.fail('Concurrent build accepted')


if __name__ == '__main__':
    unittest.main()
