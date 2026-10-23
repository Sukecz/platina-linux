"""No power action is permitted in preview or before the shutdown frame is shown."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('poweroff_screen', ROOT / 'scripts/phone-poweroff.py')
poweroff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poweroff)


class PoweroffTests(unittest.TestCase):
    def test_orderly_command_and_bounded_failure_cleanup(self):
        with patch.object(poweroff.subprocess, 'run') as run, patch.object(poweroff.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'did not finish'):
                poweroff.request_shutdown()
            run.assert_called_once_with(['/usr/sbin/poweroff'], check=True, timeout=10)

    def test_preview_has_no_poweroff_callback(self):
        @contextmanager
        def device():
            yield 12
        show = Mock()
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(poweroff.sys, 'argv', ['platina-poweroff', '--preview']), \
             patch.object(poweroff.os, 'geteuid', return_value=0), \
             patch.object(poweroff.signal, 'signal'), \
             patch.object(poweroff.runpy, 'run_path', return_value={'device': device, 'show': show}), \
             patch.object(poweroff, 'Path', side_effect=lambda _: Path(temp) / 'lock'), \
             patch.object(poweroff.subprocess, 'run') as command:
            poweroff.main()
            self.assertIsNone(show.call_args.kwargs['after_display'])
            command.assert_not_called()

    def test_display_failure_cannot_request_shutdown(self):
        @contextmanager
        def device():
            raise ValueError('panel missing')
            yield
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(poweroff.sys, 'argv', ['platina-poweroff']), \
             patch.object(poweroff.os, 'geteuid', return_value=0), \
             patch.object(poweroff.signal, 'signal'), \
             patch.object(poweroff.runpy, 'run_path', return_value={'device': device, 'show': Mock()}), \
             patch.object(poweroff, 'Path', side_effect=lambda _: Path(temp) / 'lock'), \
             patch.object(poweroff.subprocess, 'run') as command:
            with self.assertRaisesRegex(ValueError, 'panel missing'):
                poweroff.main()
            command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
