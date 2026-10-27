#!/usr/bin/env python3
"""Always available controls; capture is explicitly enabled and defaults OFF."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import secrets
import select
import signal
import socket
import subprocess
import threading
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

DEFAULTS = dict(focus=310, gamma=1.0, contrast=1.0, saturation=1.14, automatic=True,
                red=2.09, blue=1.49, rotation=90, scale=2, quality=50, fps=30,
                exposure_auto=True, exposure_us=10000, analogue_gain=1.0, zoom=1.0)
RANGES = dict(focus=(0, 1023), gamma=(.5, 4), contrast=(.5, 1.8),
              saturation=(0, 2), red=(.25, 4), blue=(.25, 4), quality=(10, 95), fps=(10, 30),
              exposure_us=(100, 100000), analogue_gain=(1, 8), zoom=(1, 10))
EXPOSURE_DEFAULTS = {key: DEFAULTS[key] for key in ('exposure_auto', 'exposure_us', 'analogue_gain')}


def load_settings(path):
    value = json.loads(path.read_text())
    # Migrate only complete historical schemas; reject corrupt/unknown fields.
    if isinstance(value, dict) and set(value) == set(DEFAULTS) - set(EXPOSURE_DEFAULTS) - {'zoom'}:
        value = dict(value, **EXPOSURE_DEFAULTS)
    if isinstance(value, dict) and set(value) == set(DEFAULTS) - {'zoom'}:
        value = dict(value, zoom=1.0)
    return validate(value)
SCALES = {1: '12 MP', 1.5: '5,4 MP', 2: '3 MP', 3: '1,3 MP', 4: '0,75 MP', 6: '0,33 MP'}


def validate(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULTS):
        raise ValueError('Unexpected settings fields')
    for key, item in value.items():
        if key in ('automatic', 'exposure_auto'):
            if type(item) is not bool:
                raise ValueError('Invalid ' + key)
        elif key == 'rotation':
            if type(item) is not int or item not in (0, 90, 180, 270):
                raise ValueError('Invalid rotation')
        elif key == 'scale':
            if type(item) not in (int, float) or item not in SCALES:
                raise ValueError('Invalid scale')
        else:
            if type(item) not in (int, float) or not math.isfinite(item):
                raise ValueError('Invalid ' + key)
            low, high = RANGES[key]
            if not low <= item <= high or (key in ('focus', 'quality', 'fps', 'exposure_us') and type(item) is not int):
                raise ValueError('Out of range: ' + key)
    result = dict(value)
    result['fps'] = 30
    result['scale'] = 1.5 if value['scale'] == 1.5 else int(value['scale'])
    return result


def atomic(path, data):
    temporary = path.with_name(path.name + '.new')
    temporary.write_bytes(data)
    temporary.chmod(0o600)
    temporary.replace(path)


class Camera:
    def __init__(self, args):
        self.args = args
        self.lock = threading.RLock()
        self.settings = load_settings(args.config) if args.config.exists() else dict(DEFAULTS)
        self.saved = dict(self.settings)
        self.capture = None
        self.focus_fd = None
        self.focus_device = None
        self.focus_applied = False
        self.error = None
        self.generation = 0
        self.started = 0
        self.args.frame.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.clear_frames()

    def clear_frames(self):
        for suffix in ('', '.new', '.meta', '.meta.new', '.controls', '.controls.new'):
            Path(str(self.args.frame) + suffix).unlink(missing_ok=True)

    def controls(self, value):
        fields = [value['gamma'], value['contrast'], value['saturation'],
                  int(value['automatic']), value['red'], value['blue'],
                  value['rotation'], value['scale'], value['quality'], value['fps'],
                  int(value['exposure_auto']), value['exposure_us'], value['analogue_gain'], value['zoom']]
        atomic(Path(str(self.args.frame) + '.controls'), (' '.join(map(str, fields)) + '\n').encode())

    def focus(self, position):
        subprocess.run(['v4l2-ctl', '-d', self.focus_device,
                        '--set-ctrl=focus_absolute=' + str(position)], check=True, timeout=5)

    def configure(self, payload, save=False):
        if not isinstance(payload, dict) or not set(payload) <= set(DEFAULTS):
            raise ValueError('Unexpected settings fields')
        with self.lock:
            value = validate(dict(self.settings, **payload))
            if self.capture is not None and self.capture.poll() is None:
                if self.focus_applied and value['focus'] != self.settings['focus']:
                    self.focus(value['focus'])
                self.controls(value)
                if any(value[k] != self.settings[k] for k in ('scale', 'rotation')):
                    self.started = time.monotonic()
            if save:
                self.args.config.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                atomic(self.args.config, (json.dumps(value, indent=2) + '\n').encode())
                self.saved = dict(value)
            self.settings = value
            return dict(value)

    def set_enabled(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('Expected enabled: true or false')
        with self.lock:
            if not enabled:
                self.stop()
            elif self.capture is None or self.capture.poll() is not None:
                self.stop()
                self.error = None
                try:
                    matches = [p for p in Path('/sys/class/video4linux').glob('v4l-subdev*')
                               if (p / 'name').read_text().strip() == 'dw9714 2-000c']
                    if len(matches) != 1:
                        raise OSError('Rear camera is not available in this kernel')
                    self.focus_device = '/dev/' + matches[0].name
                    self.focus_fd = os.open(self.focus_device, os.O_RDWR | os.O_CLOEXEC)
                    self.controls(self.settings)
                    env = dict(os.environ,
                               LD_LIBRARY_PATH='/usr/lib/platina-camera/lib:/usr/lib/platina-camera/gpu/lib:/usr/lib/platina-camera/gpu/lib/dri',
                               LIBCAMERA_SOFTISP_MODE='cpu' if self.args.cpu else 'gpu',
                               PLATINA_JPEG_THREADS='2' if self.args.cpu else '4',
                               LIBCAMERA_LOG_LEVELS='*:WARN')
                    # Experimental DMA paths must never be enabled by a stale shell environment.
                    for key in ('PLATINA_GPU_INPUT_DMABUF', 'PLATINA_GPU_FLAT_DMABUF', 'PLATINA_GPU_PROFILE'):
                        env.pop(key, None)
                    self.capture = subprocess.Popen([self.args.capture, str(self.args.frame)], env=env)
                    self.started = time.monotonic()
                    self.generation += 1
                except (OSError, subprocess.SubprocessError):
                    self.stop()
                    self.error = 'Kameru nelze spustit. Zkontrolujte ovladač a záznam služby.'
                    raise OSError(self.error) from None
            return self.status()

    def stop(self):
        with self.lock:
            self.generation += 1
            if self.capture is not None:
                if self.capture.poll() is None:
                    self.capture.terminate()
                    try:
                        self.capture.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        self.capture.kill()
                        self.capture.wait(timeout=3)
                self.capture = None
            if self.focus_fd is not None:
                os.close(self.focus_fd)
                self.focus_fd = None
            self.focus_applied = False
            self.focus_device = None
            self.clear_frames()
            self.error = None

    def tick(self):
        with self.lock:
            if self.capture is None:
                return
            code = self.capture.poll()
            if code is not None:
                self.stop()
                self.error = 'Snímání se zastavilo. Kameru lze znovu zapnout.'
                print('Capture exited with status ' + str(code), flush=True)
            elif not self.focus_applied and self.args.frame.exists():
                try:
                    self.focus(self.settings['focus'])
                    self.focus_applied = True
                except (OSError, subprocess.SubprocessError):
                    self.stop()
                    self.error = 'Nastavení ostření selhalo. Kameru lze znovu zapnout.'
            elif time.monotonic() - self.started > 20:
                try:
                    self.latest()
                except (OSError, ValueError, KeyError):
                    self.stop()
                    self.error = 'Kamera nedodává aktuální obraz. Kameru lze znovu zapnout.'

    def latest(self):
        with self.lock:
            if self.capture is None or self.capture.poll() is not None:
                raise OSError('Camera is off')
            with self.args.frame.open('rb') as stream:
                stat = os.fstat(stream.fileno())
                age = time.time() - stat.st_mtime
                if age > 2:
                    raise OSError('Camera frame expired')
                data = stream.read(8 * 1024 * 1024 + 1)
            meta = json.loads(Path(str(self.args.frame) + '.meta').read_text())
            marker = re.search(rb'platina_capture_ns=([0-9]+)', data[:1024])
            if not marker:
                raise OSError('Missing frame timestamp')
            meta['captured_ns'] = int(marker.group(1))
            meta['sensor_age_ms'] = (time.monotonic_ns() - meta['captured_ns']) / 1_000_000
            if meta['sensor_age_ms'] > 2000:
                raise OSError('Sensor frame expired')
            if len(data) > 8 * 1024 * 1024 or not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
                raise OSError('Incomplete frame')
            return data, age, stat.st_mtime_ns, meta

    def status(self):
        with self.lock:
            enabled = self.capture is not None and self.capture.poll() is None
            result = dict(ok=True, enabled=enabled, state='starting' if enabled else 'error' if self.error else 'off',
                          error=self.error, settings=dict(self.settings), generation=self.generation)
            if enabled:
                try:
                    _, age, _, meta = self.latest()
                    result.update(state='on', age_seconds=round(age, 3), **meta)
                except (OSError, ValueError, KeyError):
                    pass
            return result


class Audio:
    """One on-demand PCM listener; restore the mixer on every exit path."""
    rate = 48000

    def __init__(self):
        self.lock = threading.Lock()
        self.tokens = {}
        self.capture = None
        self.closed = False
        self.released = threading.Event()
        self.released.set()

    def ticket(self):
        with self.lock:
            if self.closed:
                raise ValueError('Audio is stopping')
            if self.capture is not None:
                raise ValueError('Mikrofon právě používá jiný posluchač.')
            # Keep only the latest short-lived, single-use authorization.
            token = secrets.token_urlsafe(24)
            self.tokens = {token: time.monotonic() + 10}
            return dict(token=token, rate=self.rate, channels=1, format='s16le')

    def open(self, token):
        with self.lock:
            expires = self.tokens.pop(token, 0)
            if self.closed or expires < time.monotonic() or self.capture is not None:
                raise ValueError('Poslech vypršel nebo je mikrofon obsazený.')
            if 'Xiaomi Mi 8 Lite' not in Path('/proc/asound/cards').read_text():
                raise ValueError('Mikrofon telefonu není dostupný.')
            directory = tempfile.TemporaryDirectory(prefix='platina-audio-')
            state = str(Path(directory.name) / 'mixer.state')
            saved = False
            try:
                self.command(['alsactl', '-f', state, 'store', '0'])
                saved = True
                for name, value in (
                    ('MultiMedia1 Mixer LPI_MI2S_TX_3', '1'),
                    ('Digital CIC1 MUX', 'AMIC'),
                    ('Digital DEC1 MUX', 'ADC2'), ('ADC2 MUX', 'INP3'),
                    ('ADC3 Volume', '6'), ('Digital TX1 Digital Volume', '114')):
                    self.command(['amixer', '-q', '-c', '0', 'cset', 'name=' + name, value])
                process = subprocess.Popen(
                    ['arecord', '-q', '-D', 'hw:0,0', '-t', 'raw', '-f', 'S16_LE',
                     '-r', str(self.rate), '-c', '1', '--period-size=960', '--buffer-size=3840'],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                self.capture = process
                self.released.clear()
                return process, directory, state
            except Exception:
                if saved:
                    self.command(['alsactl', '-f', state, 'restore', '0'], check=False)
                directory.cleanup()
                raise

    @staticmethod
    def command(args, check=True):
        return subprocess.run(args, check=check, timeout=5, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)

    def release(self, session):
        process, directory, state = session
        with self.lock:
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                process.stdout.close()
            finally:
                try:
                    self.command(['alsactl', '-f', state, 'restore', '0'], check=False)
                finally:
                    directory.cleanup()
                    self.capture = None
                    self.released.set()

    def close(self):
        with self.lock:
            self.closed = True
            self.tokens.clear()
            if self.capture is not None and self.capture.poll() is None:
                self.capture.terminate()
        self.released.wait(timeout=8)


def make_handler(camera, shutdown, audio=None):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(2)
            self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        def log_message(self, *_):
            pass

        def reply(self, status, content_type, payload):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(payload)

        def json(self, status, value):
            self.reply(status, 'application/json', json.dumps(value).encode())

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == '/':
                    self.reply(200, 'text/html; charset=utf-8', Path(__file__).with_name('preview.html').read_bytes())
                elif path == '/settings':
                    with camera.lock:
                        self.json(200, dict(camera.settings))
                elif path in ('/status', '/health'):
                    self.json(200, camera.status())
                elif path == '/audio.pcm' and audio is not None:
                    from urllib.parse import parse_qs
                    origin = self.headers.get('Origin')
                    if origin not in (None, 'http://' + self.headers.get('Host', '')):
                        self.json(403, dict(error='Origin rejected'))
                        return
                    try:
                        session = audio.open(parse_qs(urlsplit(self.path).query).get('token', [''])[0])
                    except (OSError, ValueError, subprocess.SubprocessError) as error:
                        self.json(409, dict(error=str(error)))
                        return
                    try:
                        process = session[0]
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/octet-stream')
                        self.send_header('Cache-Control', 'no-store')
                        self.send_header('Connection', 'close')
                        self.end_headers()
                        self.close_connection = True
                        while not shutdown.is_set():
                            if not select.select([process.stdout], [], [], 3)[0]:
                                break
                            data = os.read(process.stdout.fileno(), 3840)
                            if not data:
                                break
                            self.wfile.write(data)
                            self.wfile.flush()
                    finally:
                        audio.release(session)
                elif path in ('/snapshot.jpg', '/stream.mjpg'):
                    try:
                        data, _, stamp, meta = camera.latest()
                    except (OSError, ValueError, KeyError):
                        self.json(503, dict(ok=False, error='Camera is off or starting'))
                        return
                    if path == '/snapshot.jpg':
                        self.reply(200, 'image/jpeg', data)
                        return
                    generation = camera.generation
                    self.send_response(200)
                    self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    while not shutdown.is_set() and camera.generation == generation:
                        self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' + str(len(data)).encode() + b'\r\nX-Frame-Age-Ms: ' + str(round(meta['sensor_age_ms'], 2)).encode() + b'\r\n\r\n' + data + b'\r\n')
                        self.wfile.flush()
                        while not shutdown.wait(.005) and camera.generation == generation:
                            if camera.args.frame.stat().st_mtime_ns == stamp:
                                continue
                            data, _, stamp, meta = camera.latest()
                            break
                else:
                    self.json(404, dict(error='Not found'))
            except (OSError, ValueError, KeyError):
                self.close_connection = True

        def do_POST(self):
            path = urlsplit(self.path).path
            if path not in ('/settings', '/save', '/restore', '/camera', '/audio'):
                self.json(404, dict(error='Not found'))
                return
            if self.headers.get('Origin') not in (None, 'http://' + self.headers.get('Host', '')):
                self.json(403, dict(error='Origin rejected'))
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2048 or self.headers.get_content_type() != 'application/json':
                    raise ValueError('Expected small JSON body')
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError('Expected JSON object')
                if path == '/audio':
                    if payload or audio is None:
                        raise ValueError('Expected empty object and available audio')
                    self.json(200, audio.ticket())
                    return
                with camera.lock:
                    if path == '/camera':
                        if set(payload) != {'enabled'}:
                            raise ValueError('Expected enabled field')
                        value = camera.set_enabled(payload['enabled'])
                    elif path == '/save':
                        if payload:
                            raise ValueError('Expected empty object')
                        value = camera.configure({}, save=True)
                    elif path == '/restore':
                        if payload:
                            raise ValueError('Expected empty object')
                        value = camera.configure(dict(camera.saved))
                    else:
                        value = camera.configure(payload)
                    self.json(200, value)
            except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
                self.json(400, dict(error=str(error)))
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu', action='store_true')
    parser.add_argument('--listen', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8082)
    parser.add_argument('--frame', type=Path, default=Path('/run/platina-camera/latest.jpg'))
    parser.add_argument('--capture', default='/usr/lib/platina-camera/bin/platina-camera-capture')
    parser.add_argument('--config', type=Path, default=Path('/etc/platina-camera/preview.json'))
    parser.add_argument('--mqtt-config', type=Path, default=Path('/etc/platina-camera/mqtt.json'))
    parser.add_argument('--seconds', type=float)
    args = parser.parse_args()
    os.umask(0o077)
    shutdown = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: shutdown.set())
    camera = Camera(args)
    audio = Audio()
    bridge = None
    server = ThreadingHTTPServer((args.listen, args.port), make_handler(camera, shutdown, audio))
    server.daemon_threads = True
    server.timeout = .1
    try:
        if args.mqtt_config.exists():
            from camera_mqtt import Bridge
            try:
                bridge = Bridge(camera, args.mqtt_config)
                bridge.start()
            except (OSError, ValueError, ImportError, KeyError, AttributeError):
                bridge = None
                print('MQTT configuration unavailable; web controls remain available', flush=True)
        print(f'Platina controls listening on {args.listen}:{args.port}; camera OFF', flush=True)
        deadline = time.monotonic() + args.seconds if args.seconds else None
        while not shutdown.is_set():
            if deadline and time.monotonic() >= deadline:
                break
            camera.tick()
            if bridge:
                bridge.tick()
            server.handle_request()
    finally:
        shutdown.set()
        audio.close()
        camera.stop()
        if bridge:
            bridge.close()
        server.server_close()


if __name__ == '__main__':
    main()
