"""Verify rejection of bad DCS replies and cleanup on a failed renderer."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('display_session', ROOT / 'scripts/phone-display-session.py')
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)


class DisplaySessionTests(unittest.TestCase):
    def test_only_valid_awake_panel_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            params = Path(temp)
            values = dict(io_enabled=1, read_result=1, wake_result=0, power_after=0x9c)
            for name, value in values.items():
                (params / name).write_text(str(value))
            self.assertEqual(session.check_panel(params), values)
            for field, bad in [('power_after', 0x08), ('read_result', -110),
                               ('wake_result', -5), ('io_enabled', 0)]:
                (params / field).write_text(str(bad))
                with self.assertRaises(ValueError):
                    session.check_panel(params)
                (params / field).write_text(str(values[field]))

    def test_renderer_failure_still_releases_owned_power(self):
        params = MagicMock()
        params.exists.side_effect = [False, True]
        fake_path = MagicMock()
        with patch.object(session, 'PARAMS', params), \
             patch.object(session, 'Path', return_value=fake_path), \
             patch.object(session.fcntl, 'flock'), \
             patch.object(session, 'validate', return_value='/verified/module.ko'), \
             patch.object(session, 'check_panel', return_value={}), \
             patch.object(session.subprocess, 'run') as run, \
             patch.object(session.subprocess, 'Popen', side_effect=OSError('renderer unavailable')):
            with self.assertRaises(OSError):
                session.session(['--seconds', '7'])
        self.assertEqual(run.call_args_list[-1].args[0], ['rmmod', 'platina_panel_dcs'])
        fake_path.write_text.assert_called_once_with('0\n')


if __name__ == '__main__':
    unittest.main()
