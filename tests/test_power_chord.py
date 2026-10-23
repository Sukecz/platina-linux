"""Verify physical chord decisions and shutdown dispatch without real device I/O."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('power_chord', ROOT / 'scripts/phone-power-chord.py')
chord = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chord)
P, U = chord.KEY_POWER, chord.KEY_VOLUMEUP


class ChordTests(unittest.TestCase):
    def gesture(self, policy=None, order=(P, U), releases=(P, U), duration=3.2):
        policy = policy or chord.ChordPolicy()
        self.assertIsNone(policy.event(order[0], 1, 100))
        self.assertIsNone(policy.event(order[1], 1, 100.1))
        self.assertIsNone(policy.event(releases[0], 0, 100.1 + duration))
        return policy.event(releases[1], 0, 100.2 + duration)

    def test_both_press_and_release_orders_work_once(self):
        for presses in ((P, U), (U, P)):
            for releases in ((P, U), (U, P)):
                self.assertEqual(self.gesture(order=presses, releases=releases), 'poweroff')

    def test_single_keys_and_short_chord_do_nothing(self):
        for key in (P, U):
            policy = chord.ChordPolicy()
            self.assertIsNone(policy.event(key, 1, 100))
            self.assertIsNone(policy.event(key, 0, 106))
        self.assertIsNone(self.gesture(duration=2.9))

    def test_duration_starts_only_when_both_are_pressed(self):
        p = chord.ChordPolicy()
        p.event(U, 1, 100)
        p.event(P, 1, 104)
        self.assertIsNone(p.event(P, 0, 105))
        self.assertIsNone(p.event(U, 0, 105.1))

    def test_repeat_or_duplicate_press_does_not_change_hold(self):
        p = chord.ChordPolicy()
        p.event(P, 1, 100)
        p.event(U, 1, 100.1)
        p.event(P, 2, 102)
        p.event(U, 1, 103)
        self.assertIsNone(p.event(U, 0, 103.2))
        self.assertEqual(p.event(P, 0, 103.3), 'poweroff')

    def test_held_at_start_and_lost_events_cancel(self):
        p = chord.ChordPolicy(held=(P, U))
        self.assertIsNone(p.event(P, 0, 100))
        self.assertIsNone(p.event(U, 0, 101))
        p.event(P, 1, 200)
        p.event(U, 1, 200.1)
        self.assertIsNone(p.event(P, 0, 203.2))
        self.assertEqual(p.event(U, 0, 203.3), 'poweroff')
        p = chord.ChordPolicy()
        p.event(P, 1, 100)
        p.event(U, 1, 101)
        p.resync((P, U))
        self.assertIsNone(p.event(P, 0, 105))
        self.assertIsNone(p.event(U, 0, 106))

    def test_repress_before_both_released_cancels(self):
        p = chord.ChordPolicy()
        p.event(P, 1, 100)
        p.event(U, 1, 100.1)
        p.event(U, 0, 103.2)
        p.event(U, 1, 103.3)
        self.assertIsNone(p.event(P, 0, 107))
        self.assertIsNone(p.event(U, 0, 108))

    def test_backwards_clock_and_synthetic_press_cancel(self):
        p = chord.ChordPolicy()
        p.event(P, 1, 100)
        p.event(U, 1, 101)
        p.event(P, 0, 99)
        self.assertIsNone(p.event(U, 0, 110))
        p = chord.ChordPolicy()
        p.event(P, 1, 100)
        p.event(U, 1, 101)
        p.event(U, 0, 101)
        self.assertIsNone(p.event(P, 0, 105))

    def test_dry_run_never_launches_helper(self):
        with patch.object(chord.subprocess, 'Popen') as child:
            chord.dispatch(True)
            child.assert_not_called()

    def test_dispatch_uses_only_screen_and_orderly_shutdown_helper(self):
        with patch.object(chord.subprocess, 'Popen') as child:
            child.return_value.wait.return_value = 0
            chord.dispatch(False)
            child.assert_called_once_with(['/usr/local/sbin/platina-poweroff'], start_new_session=True)

    def test_device_identity_does_not_depend_on_event_number(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            for n, name in ((7, 'pm8941_pwrkey'), (9, 'Volume up')):
                (base / f'event{n}/device').mkdir(parents=True)
                (base / f'event{n}/device/name').write_text(name)
            self.assertEqual(chord.find_devices(base), {P: Path('/dev/input/event7'), U: Path('/dev/input/event9')})


if __name__ == '__main__':
    unittest.main()
