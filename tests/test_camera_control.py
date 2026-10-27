"""Capture lifetime, privacy defaults and HTTP/MQTT control regressions."""
import importlib.util
import json
import os
from pathlib import Path
import queue
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'project/camera/libcamera-headless' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


serve = module('serve')
mqtt = module('camera_mqtt')


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.args = SimpleNamespace(config=root / 'settings.json', frame=root / 'run/frame.jpg',
                                    capture='unused', cpu=False)
        self.camera = serve.Camera(self.args)
        self.audio = serve.Audio()
        self.stop = threading.Event()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), serve.make_handler(self.camera, self.stop, self.audio))
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.stop.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.camera.stop()
        self.audio.close()
        self.tmp.cleanup()

    def get(self, path):
        with urlopen(self.base + path, timeout=3) as response:
            return json.load(response)

    def post(self, path, payload, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        request = Request(self.base + path, data=json.dumps(payload).encode(), headers=headers)
        with urlopen(request, timeout=3) as response:
            return json.load(response)

    def test_boot_off_and_reading_image_never_enables_capture(self):
        self.assertEqual(self.get('/status')['state'], 'off')
        for endpoint in ('/snapshot.jpg', '/stream.mjpg'):
            with self.assertRaises(HTTPError) as error:
                self.get(endpoint)
            self.assertEqual(error.exception.code, 503)
        self.assertIsNone(self.camera.capture)

    def test_settings_off_persist_but_capture_does_not(self):
        self.post('/settings', {'focus': 430, 'quality': 10, 'scale': 1.5})
        self.post('/save', {})
        after = serve.Camera(self.args)
        self.assertFalse(after.status()['enabled'])
        self.assertEqual(after.settings['focus'], 430)
        self.assertEqual(after.settings['quality'], 10)
        self.assertEqual(after.settings['scale'], 1.5)
        self.assertEqual(self.args.config.stat().st_mode & 0o777, 0o600)
        self.assertIsNone(self.camera.focus_fd)

    def test_audio_requires_explicit_same_origin_ticket(self):
        with patch.object(serve.subprocess, 'Popen') as popen:
            with self.assertRaises(HTTPError) as error:
                self.get('/audio.pcm')
            self.assertEqual(error.exception.code, 409)
            with self.assertRaises(HTTPError) as error:
                self.post('/audio', {}, 'http://other.example')
            self.assertEqual(error.exception.code, 403)
            self.assertEqual(self.post('/audio', {})['rate'], 48000)
            self.assertIsNone(self.audio.capture)
            popen.assert_not_called()

    def test_invalid_partial_settings_are_atomic(self):
        before = self.get('/settings')
        with self.assertRaises(HTTPError):
            self.post('/settings', {'quality': 9, 'focus': 999})
        self.assertEqual(self.get('/settings'), before)
        with self.assertRaises(HTTPError):
            self.post('/settings', {'scale': True})

    def test_legacy_settings_migrate_without_writing_or_starting_capture(self):
        legacy = {key: value for key, value in serve.DEFAULTS.items()
                  if key not in serve.EXPOSURE_DEFAULTS and key != 'zoom'}
        legacy.update(focus=308, quality=40, automatic=False, scale=1.5)
        original = json.dumps(legacy).encode()
        self.args.config.write_bytes(original)
        after = serve.Camera(self.args)
        self.assertEqual(after.settings, dict(legacy, **serve.EXPOSURE_DEFAULTS, zoom=1.0))
        self.assertFalse(after.status()['enabled'])
        self.assertEqual(self.args.config.read_bytes(), original)
        # A partially missing new schema is corruption, not a legacy config.
        self.args.config.write_text(json.dumps(dict(legacy, exposure_auto=False)))
        with self.assertRaises(ValueError):
            serve.Camera(self.args)

    def test_exposure_api_save_restore_and_control_wire_format(self):
        desired = dict(exposure_auto=False, exposure_us=25000, analogue_gain=2.5)
        self.post('/settings', desired)
        self.post('/save', {})
        self.post('/settings', {'exposure_auto': True, 'exposure_us': 5000})
        restored = self.post('/restore', {})
        for key, value in desired.items():
            self.assertEqual(restored[key], value)
        self.camera.controls(restored)
        fields = Path(str(self.args.frame) + '.controls').read_text().split()
        self.assertEqual(fields[-4:], ['0', '25000', '2.5', '1.0'])
        self.assertEqual(serve.Camera(self.args).settings, restored)
        self.assertFalse(self.camera.status()['enabled'])

    def test_exposure_validation_preserves_settings_on_rejection(self):
        before = self.get('/settings')
        for payload in ({'exposure_auto': 1}, {'exposure_us': 10000.5},
                        {'exposure_us': True}, {'exposure_us': 99}, {'exposure_us': 100001},
                        {'analogue_gain': 0}, {'analogue_gain': 8.01}, {'analogue_gain': float('nan')}):
            with self.subTest(payload=payload):
                with self.assertRaises(HTTPError):
                    self.post('/settings', payload)
                self.assertEqual(self.get('/settings'), before)

    def test_mqtt_exposure_changes_are_acknowledged_saved_and_do_not_start_camera(self):
        bridge = mqtt.Bridge.__new__(mqtt.Bridge)
        bridge.camera = self.camera
        bridge.command('exposure_us', '100000')
        bridge.command('analogue_gain', '8')
        bridge.command('exposure_auto', 'OFF')
        self.assertEqual(self.camera.settings['exposure_us'], 100000)
        self.assertEqual(self.camera.settings['analogue_gain'], 8)
        self.assertFalse(self.camera.settings['exposure_auto'])
        self.assertEqual(serve.Camera(self.args).settings, self.camera.settings)
        for key, value in [('exposure_auto', 'true'), ('exposure_us', '100.1'), ('analogue_gain', 'inf')]:
            with self.assertRaises(ValueError):
                bridge.command(key, value)
        self.assertFalse(self.camera.status()['enabled'])

    def test_discovery_separates_requested_controls_and_actual_telemetry(self):
        entries = mqtt.discovery(dict(topic='platina/camera', device_id='platina', web_url='http://platina:8082/'))
        entities = {topic.split('/')[-2]: payload for topic, payload in entries}
        self.assertEqual(entities['exposure_us']['max'], 100000)
        self.assertEqual(entities['analogue_gain']['min'], 1)
        self.assertIn('settings.exposure_auto', entities['exposure_auto']['value_template'])
        for key in ('exposure_us_actual', 'analogue_gain_actual'):
            self.assertNotIn('command_topic', entities[key])
            self.assertNotIn('availability_topic', entities[key])
            self.assertEqual(entities[key]['availability_mode'], 'all')
            self.assertIn("state == 'on'", entities[key]['availability'][1]['value_template'])

    def test_zoom_migrates_exposure_schema_without_changing_manual_exposure(self):
        legacy = {key: value for key, value in serve.DEFAULTS.items() if key != 'zoom'}
        legacy.update(exposure_auto=False, exposure_us=25000, analogue_gain=2.5, focus=308)
        self.args.config.write_text(json.dumps(legacy))
        before = self.args.config.read_bytes()
        after = serve.Camera(self.args)
        self.assertEqual(after.settings, dict(legacy, zoom=1.0))
        self.assertEqual(self.args.config.read_bytes(), before)
        self.assertFalse(after.status()['enabled'])

    def test_zoom_live_save_restore_and_mqtt_share_one_setting(self):
        self.post('/settings', {'zoom': 2.5})
        self.post('/save', {})
        bridge = mqtt.Bridge.__new__(mqtt.Bridge)
        bridge.camera = self.camera
        bridge.command('zoom', '4')
        self.assertEqual(self.get('/status')['settings']['zoom'], 4)
        self.assertEqual(serve.Camera(self.args).settings['zoom'], 4)
        self.post('/settings', {'zoom': 1})
        self.assertEqual(self.post('/restore', {})['zoom'], 4)
        self.camera.controls(self.camera.settings)
        self.assertEqual(Path(str(self.args.frame) + '.controls').read_text().split()[-1], '4.0')
        self.assertFalse(self.get('/status')['enabled'])

    def test_zoom_validation_is_atomic(self):
        before = self.get('/settings')
        for value in [0.99, 10.01, True, '2', None, float('nan'), float('inf')]:
            with self.subTest(value=value):
                with self.assertRaises(HTTPError):
                    self.post('/settings', {'zoom': value, 'focus': 999})
                self.assertEqual(self.get('/settings'), before)
        entries = mqtt.discovery(dict(topic='platina/camera', device_id='platina', web_url='http://platina:8082/'))
        zoom = next(payload for topic, payload in entries if topic.endswith('/zoom/config'))
        self.assertEqual((zoom['min'], zoom['max'], zoom['step']), (1, 10, .1))
        self.assertIn('settings.zoom', zoom['value_template'])

    def test_extended_zoom_and_fixed_target_fps(self):
        self.post('/settings', {'zoom': 10, 'fps': 10})
        self.assertEqual(self.get('/settings')['zoom'], 10)
        self.assertEqual(self.get('/settings')['fps'], 30)
        self.post('/save', {})
        self.assertEqual(serve.Camera(self.args).settings['fps'], 30)
        bridge = mqtt.Bridge.__new__(mqtt.Bridge)
        bridge.camera = self.camera
        bridge.command('fps', '15')
        self.assertEqual(self.camera.settings['fps'], 30)

    def test_cross_origin_rejected(self):
        with self.assertRaises(HTTPError) as error:
            self.post('/camera', {'enabled': True}, 'http://other.example')
        self.assertEqual(error.exception.code, 403)
        self.assertFalse(self.get('/status')['enabled'])

    def test_stop_releases_lens_and_removes_last_frame(self):
        frame = self.args.frame
        frame.write_bytes(b'old private image')
        lens = frame.with_name('lens')
        lens.write_bytes(b'')
        fd = os.open(lens, os.O_RDONLY)
        child = Mock()
        child.poll.return_value = None
        self.camera.capture = child
        self.camera.focus_fd = fd
        self.post('/camera', {'enabled': False})
        child.terminate.assert_called_once()
        child.wait.assert_called_once_with(timeout=8)
        self.assertFalse(frame.exists())
        with self.assertRaises(OSError):
            os.fstat(fd)
        self.assertEqual(self.get('/status')['state'], 'off')

    def test_capture_failure_keeps_controls_available(self):
        child = Mock()
        child.poll.return_value = 1
        self.camera.capture = child
        self.camera.tick()
        self.assertEqual(self.get('/status')['state'], 'error')
        self.post('/settings', {'focus': 320})
        self.assertEqual(self.get('/settings')['focus'], 320)
        self.post('/camera', {'enabled': False})
        self.assertEqual(self.get('/status')['state'], 'off')

    def test_retained_mqtt_on_is_ignored(self):
        bridge = mqtt.Bridge.__new__(mqtt.Bridge)
        bridge.commands = queue.Queue()
        message = SimpleNamespace(topic='platina/camera/set/enabled', payload=b'ON', retain=True)
        bridge.on_message(None, None, message)
        self.assertTrue(bridge.commands.empty())
        message.retain = False
        bridge.on_message(None, None, message)
        self.assertEqual(bridge.commands.get_nowait(), ('enabled', 'ON'))


class AudioTests(unittest.TestCase):
    def test_ticket_never_opens_microphone_and_expires(self):
        audio = serve.Audio()
        with patch.object(serve.subprocess, 'Popen') as popen:
            ticket = audio.ticket()
            self.assertIsNone(audio.capture)
            audio.tokens[ticket['token']] = 0
            with self.assertRaises(ValueError):
                audio.open(ticket['token'])
            with self.assertRaises(ValueError):
                audio.open('not-authorized')
            popen.assert_not_called()

    def test_capture_exclusive_single_use_and_restores_mixer(self):
        audio = serve.Audio()
        audio.command = Mock()
        process = Mock()
        process.poll.return_value = None
        token = audio.ticket()['token']
        with patch.object(serve.Path, 'read_text', return_value='Xiaomi Mi 8 Lite'), \
                patch.object(serve.subprocess, 'Popen', return_value=process):
            session = audio.open(token)
            with self.assertRaises(ValueError):
                audio.ticket()
            with self.assertRaises(ValueError):
                audio.open(token)
            audio.release(session)
        self.assertIsNone(audio.capture)
        process.terminate.assert_called_once()
        self.assertTrue(audio.released.is_set())
        self.assertEqual(audio.command.call_args.args[0][3:], ['restore', '0'])
        self.assertFalse(Path(session[1].name).exists())

    def test_failed_route_restores_original_mixer(self):
        audio = serve.Audio()
        audio.command = Mock(side_effect=[None, OSError('route failed'), None])
        with patch.object(serve.Path, 'read_text', return_value='Xiaomi Mi 8 Lite'):
            with self.assertRaises(OSError):
                audio.open(audio.ticket()['token'])
        self.assertEqual(audio.command.call_args.args[0][3:], ['restore', '0'])
        self.assertIsNone(audio.capture)

    def test_shutdown_revokes_unused_tickets(self):
        audio = serve.Audio()
        ticket = audio.ticket()
        audio.close()
        with self.assertRaises(ValueError):
            audio.open(ticket['token'])
        with self.assertRaises(ValueError):
            audio.ticket()


if __name__ == '__main__':
    unittest.main()
