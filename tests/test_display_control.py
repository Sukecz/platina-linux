"""Offline power-order, cleanup and image roundtrip tests for the native panel path."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock, call

ROOT = Path(__file__).resolve().parents[1]


def load(name, script):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


control = load('display_control', 'phone-display.py')
splash = load('display_splash', 'phone-splash.py')


class ControlTests(unittest.TestCase):
    def test_powerdown_clears_backlight_before_drm(self):
        events = MagicMock()
        with patch.object(control, 'brightness', events.brightness), \
             patch.object(control.fcntl, 'ioctl', events.ioctl):
            control.off(12)
        self.assertEqual(events.mock_calls, [call.brightness(0), call.ioctl(12, control.FBIOBLANK, 4)])

    def test_renderer_failure_still_powers_down(self):
        helper = {'load_frame': lambda _: ({'version': '0.1.1'}, b'frame'),
                  'geometry': MagicMock(side_effect=ValueError('bad framebuffer'))}
        with patch.object(control.runpy, 'run_path', return_value=helper), \
             patch.object(control, 'Path') as path, \
             patch.object(control.fcntl, 'ioctl'), \
             patch.object(control, 'off') as off:
            path.return_value.read_text.return_value = 'boot-id'
            with self.assertRaisesRegex(ValueError, 'bad framebuffer'):
                control.show(12, ROOT, 1, 25)
        off.assert_called_once_with(12)

    def test_brightness_scales_and_zero_is_exact(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(control, 'BACKLIGHT', Path(temp)):
            (Path(temp) / 'max_brightness').write_text('4095')
            for percent, expected in [(0, 0), (1, 40), (25, 1023), (100, 4095)]:
                control.brightness(percent)
                self.assertEqual(int((Path(temp) / 'brightness').read_text()), expected)
            with self.assertRaises(ValueError):
                control.brightness(101)

    def test_old_driver_rejected_before_any_device_changes(self):
        with patch.object(control, 'Path') as path, patch.object(control, 'DRIVER') as driver:
            path.return_value.read_bytes.return_value = b'xiaomi,platina\0'
            driver.resolve.return_value.name = 'panel-simple-dsi'
            with self.assertRaisesRegex(ValueError, 'Integrated Tianma'):
                control.validate()

    def test_status_never_opens_framebuffer(self):
        with patch.object(control.os, 'open', side_effect=AssertionError('device opened')), \
             patch.object(control, 'Path') as path, \
             patch.object(control, 'DRIVER') as driver, \
             patch.object(control, 'BACKLIGHT') as backlight:
            path.return_value.exists.return_value = False
            driver.exists.return_value = False
            backlight.__truediv__.return_value.exists.return_value = False
            self.assertIsNone(control.status()['driver'])

    def test_custom_frame_roundtrip(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Host-only image preparation needs Pillow')
        frame = load('prepare_frame', 'prepare-display-frame.py')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'image.png'
            Image.new('RGB', (100, 100), 'red').save(source)
            output = frame.build(source, root / 'frame')
            manifest, raw = splash.load_frame(output)
            self.assertEqual(manifest['purpose'], 'custom-display-frame')
            self.assertEqual(len(raw), 1080 * 2280 * 4)
            self.assertEqual(raw[:4], b'\0\0\0\0')  # black letterbox
            center = (1140 * 1080 + 540) * 4
            self.assertEqual(raw[center:center + 4], b'\0\0\xff\0')
            with self.assertRaisesRegex(ValueError, 'immutable'):
                frame.build(source, output)


if __name__ == '__main__':
    unittest.main()
