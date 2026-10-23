"""Exercise public-index checks against accidentally staged local files and credentials."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('public_tree', ROOT / 'scripts/check-public-tree.py')
public = importlib.util.module_from_spec(spec)
spec.loader.exec_module(public)


class PublicBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)

    def stage(self, name, content='fixture\n'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        subprocess.run(['git', '-C', str(self.root), 'add', '--', name], check=True)

    def check(self):
        with contextlib.redirect_stdout(io.StringIO()):
            public.check(self.root)

    def test_plain_source_is_allowed(self):
        self.stage('scripts/example.py', 'print("hello")\n')
        self.check()

    def test_nested_agent_instructions_rejected(self):
        self.stage('docs/AGENTS.md')
        with self.assertRaisesRegex(ValueError, 'path'):
            self.check()

    def test_notes_and_configuration_rejected(self):
        for name in ('notes.txt', 'config/phone.conf', 'backups/backup.md'):
            with self.subTest(name=name):
                self.stage(name)
                with self.assertRaisesRegex(ValueError, 'path'):
                    self.check()
                subprocess.run(['git', '-C', str(self.root), 'rm', '--cached', '-q', name], check=True)

    def test_accidental_token_value_rejected_without_echoing_it(self):
        value = 'ghp_' + 'x' * 36
        self.stage('README.md', 'credential: ' + value)
        with self.assertRaisesRegex(ValueError, 'suppressed') as caught:
            self.check()
        self.assertNotIn(value, str(caught.exception))

    def test_external_symlink_rejected(self):
        (self.root / 'external').symlink_to(self.root.parent / 'other')
        subprocess.run(['git', '-C', str(self.root), 'add', '--', 'external'], check=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.check()


if __name__ == '__main__':
    unittest.main()
