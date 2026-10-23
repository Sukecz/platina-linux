"""Power policy tests use a temporary sysfs fixture and fake network commands."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('phone_power', Path(__file__).resolve().parents[1] / 'scripts/phone-usb-power.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class PowerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.supply = Path(self.temp.name)
        for name, value in [('online', '1'), ('usb_type', 'Unknown [SDP] DCP CDP'), ('current_max', '500000')]:
            (self.supply / name).write_text(value)
        self.config = {'max_current_uA': 900000, 'rpi_host_ed25519': 'ssh-ed25519 fixture-host-key',
                       'other_usb_max_mA': 598, 'rpi_usb_budget_mA': 1600}
        self.calls = []

    def runner(self, command, **kwargs):
        self.calls.append(command)
        if command[0] == 'ip':
            return SimpleNamespace(returncode=0, stdout='172.16.42.2 dev usb0 src 172.16.42.1\n')
        return SimpleNamespace(returncode=0, stdout='172.16.42.2 ssh-ed25519 fixture-host-key\n')

    def test_verified_host_applies_configured_limit(self):
        policy.apply(self.config, self.supply, self.runner)
        self.assertEqual((self.supply / 'current_max').read_text(), '900000\n')

    def test_different_host_restores_standard_limit(self):
        self.config['rpi_host_ed25519'] = 'ssh-ed25519 another-host'
        (self.supply / 'current_max').write_text('900000')
        policy.apply(self.config, self.supply, self.runner)
        self.assertEqual((self.supply / 'current_max').read_text(), '500000\n')

    def test_wifi_route_cannot_authorize_rpi_exception(self):
        def runner(command, **kwargs):
            self.assertEqual(command[0], 'ip')
            return SimpleNamespace(returncode=0, stdout='172.16.42.2 via 198.51.100.1 dev wlan0\n')
        policy.apply(self.config, self.supply, runner)
        self.assertEqual((self.supply / 'current_max').read_text(), '500000\n')

    def test_dcp_keeps_automatic_policy(self):
        (self.supply / 'usb_type').write_text('Unknown SDP [DCP] CDP')
        (self.supply / 'current_max').write_text('1500000')
        policy.apply(self.config, self.supply, self.runner)
        self.assertEqual((self.supply / 'current_max').read_text(), '1500000')
        self.assertEqual(self.calls, [])

    def test_offline_keeps_policy(self):
        (self.supply / 'online').write_text('0')
        policy.apply(self.config, self.supply, self.runner)
        self.assertEqual(self.calls, [])

    def test_budget_overrun_refused_before_write(self):
        self.config['other_usb_max_mA'] = 800
        with self.assertRaisesRegex(ValueError, 'budget exceeded'):
            policy.apply(self.config, self.supply, self.runner)
        self.assertEqual((self.supply / 'current_max').read_text(), '500000')

    def test_unreviewed_higher_limit_refused(self):
        self.config['max_current_uA'] = 1500000
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            policy.apply(self.config, self.supply, self.runner)


if __name__ == '__main__':
    unittest.main()
