#!/usr/bin/env python3
"""Control the integrated Platina panel through fbdev/backlight; no module tricks."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import mmap
import os
from pathlib import Path
import runpy
import signal
import struct
import sys
import time

BACKLIGHT = Path('/sys/class/backlight/backlight')
DRIVER = Path('/sys/bus/mipi-dsi/devices/c994000.dsi.0/driver')
PANEL = b'xiaomi,platina-tianma-nt36672a'
FBIOBLANK = 0x4611


def validate():
    if b'xiaomi,platina\0' not in Path('/proc/device-tree/compatible').read_bytes():
        raise ValueError('This command requires Platina')
    if DRIVER.resolve(strict=True).name != 'panel-novatek-nt36672a':
        raise ValueError('Integrated Tianma driver required; keep using the 0.1.1 session on the old boot')
    # Follow the bound device's OF node instead of depending on the DT directory layout.
    compatible = (DRIVER.parent / 'of_node/compatible').read_bytes().split(b'\0')
    if PANEL not in compatible:
        raise ValueError('Unexpected panel variant')
    if Path('/sys/module/platina_panel_dcs').exists():
        raise ValueError('Temporary LCD module is loaded; do not mix display owners')


def status():
    result = {'kernel': os.uname().release,
              'driver': DRIVER.resolve().name if DRIVER.exists() else None,
              'temporary_module_loaded': Path('/sys/module/platina_panel_dcs').exists()}
    for name in ('brightness', 'actual_brightness', 'max_brightness', 'bl_power'):
        path = BACKLIGHT / name
        result[name] = int(path.read_text()) if path.exists() else None
    blank = Path('/sys/class/graphics/fb0/blank')
    result['fb_blank'] = int(blank.read_text()) if blank.exists() else None
    # Brightness zero alone does not establish that the panel rails are off.
    return result


def brightness(percent):
    if not 0 <= percent <= 100:
        raise ValueError('Brightness must be 0–100 percent')
    maximum = int((BACKLIGHT / 'max_brightness').read_text())
    level = max(1, maximum * percent // 100) if percent else 0
    (BACKLIGHT / 'brightness').write_text(str(level) + '\n')


def off(fb):
    brightness(0)
    fcntl.ioctl(fb, FBIOBLANK, 4)  # FB_BLANK_POWERDOWN: DRM calls panel unprepare.


def on(fb, percent):
    fcntl.ioctl(fb, FBIOBLANK, 0)
    (BACKLIGHT / 'bl_power').write_text('0\n')
    brightness(percent)


@contextmanager
def device():
    if os.geteuid() != 0:
        raise ValueError('Run display changes on the phone as root')
    validate()
    # Shares the existing splash lock: two renderers must not own fb0 together.
    with Path('/run/platina-splash.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fb = os.open('/dev/fb0', os.O_RDWR | os.O_CLOEXEC)
        try:
            yield fb
        finally:
            os.close(fb)


def show(fb, directory, seconds, percent, boot=False):
    helper = runpy.run_path('/usr/local/sbin/platina-splash', run_name='display_helpers')
    manifest, raw = helper['load_frame'](directory)
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    done = Path('/run/platina-splash.done')
    if boot and done.exists() and done.read_text().strip() == boot_id:
        return
    tty, previous = None, None
    try:
        variable, fixed = bytearray(160), bytearray(80)
        fcntl.ioctl(fb, 0x4600, variable, True)
        fcntl.ioctl(fb, 0x4602, fixed, True)
        layout = helper['geometry'](variable, fixed)
        tty = os.open('/dev/tty0', os.O_RDWR | os.O_CLOEXEC)
        mode = bytearray(4)
        fcntl.ioctl(tty, 0x4B3B, mode, True)
        previous = struct.unpack('=i', mode)[0]
        fcntl.ioctl(tty, 0x4B3A, 1)  # KD_GRAPHICS: don't interleave console text.
        with mmap.mmap(fb, layout[4], access=mmap.ACCESS_WRITE) as screen:
            # Prepare pixels while dark, then unblank the integrated panel.
            brightness(0)
            helper['paint'](screen, raw, layout)
            on(fb, percent)
            print(json.dumps({'framebuffer_written': manifest['version'], 'seconds': seconds,
                              'backend': 'integrated-tianma'}), flush=True)
            time.sleep(seconds)
            brightness(0)
            screen[:] = b'\0' * layout[4]
        if boot:
            done.write_text(boot_id + '\n')
    finally:
        try:
            if tty is not None:
                try:
                    if previous is not None:
                        fcntl.ioctl(tty, 0x4B3A, previous)
                finally:
                    os.close(tty)
        finally:
            # Restoring KD_TEXT can wake fbcon: power down after restoring it.
            off(fb)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status', help='Read sysfs only; does not open or wake the display')
    sub.add_parser('off', help='Backlight zero, then DRM panel powerdown')
    for name in ('on', 'brightness', 'show'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--brightness', type=int, default=25)
        if name == 'show':
            cmd.add_argument('--directory', type=Path, default=Path('/usr/local/share/platina/current'))
            cmd.add_argument('--seconds', type=float, default=7)
            cmd.add_argument('--boot', action='store_true')
    args = parser.parse_args()
    if not 0 <= getattr(args, 'brightness', 25) <= 100:
        parser.error('Brightness must be 0–100 percent')
    if args.command == 'show' and not 0 < args.seconds <= 3600:
        parser.error('Choose a display duration above zero and at most 3600 seconds')
    if args.command == 'status':
        print(json.dumps(status(), indent=2))
        return
    with device() as fb:
        if args.command == 'off':
            off(fb)
        elif args.command == 'on':
            try:
                on(fb, args.brightness)
            except BaseException:
                off(fb)
                raise
        elif args.command == 'brightness':
            brightness(args.brightness)
        else:
            show(fb, args.directory, args.seconds, args.brightness, args.boot)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print('platina-display:', error, file=sys.stderr)
        raise SystemExit(1)
