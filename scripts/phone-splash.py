#!/usr/bin/env python3
"""Show the installed Platina release on fbdev briefly, then turn backlight off."""
import argparse
import fcntl
import gzip
import hashlib
import json
import mmap
import os
from pathlib import Path
import signal
import struct
import sys
import time

CURRENT = Path('/usr/local/share/platina/current')


def load_frame(directory):
    # Pin the immutable release before reading several files across a deploy.
    directory = directory.resolve(strict=True)
    manifest = json.loads((directory / 'release.json').read_text())
    if manifest.get('schema') != 1 or manifest.get('name') != 'Platina Linux':
        raise ValueError('Unrecognized release manifest')
    display = manifest['display']
    if (display['width'], display['height'], display['format']) != (1080, 2280, 'BGRX8888'):
        raise ValueError('Unsupported release display layout')
    if display['frame'] != 'frame.bgrx.gz' or display['raw_bytes'] != 1080 * 2280 * 4:
        raise ValueError('Invalid frame manifest')
    frame_path = directory / display['frame']
    if frame_path.stat().st_size > 12_000_000:
        raise ValueError('Oversized compressed frame')
    compressed = frame_path.read_bytes()
    if hashlib.sha256(compressed).hexdigest() != display['compressed_sha256']:
        raise ValueError('Frame checksum mismatch')
    with gzip.open(frame_path, 'rb') as source:
        raw = source.read(display['raw_bytes'] + 1)
    if len(raw) != display['raw_bytes'] or hashlib.sha256(raw).hexdigest() != display['raw_sha256']:
        raise ValueError('Decoded frame checksum/length mismatch')
    return manifest, raw


def geometry(variable, fixed):
    v = struct.unpack_from('=40I', variable)
    memory = struct.unpack_from('=I', fixed, 24)[0]
    stride = struct.unpack_from('=I', fixed, 48)[0]
    width, height, virtual_width, virtual_height, xoff, yoff, bpp = v[:7]
    if (width, height, bpp) != (1080, 2280, 32):
        raise ValueError('Framebuffer resolution/pixel depth differs from release')
    if (v[8:10], v[11:13], v[14:16]) != ((16, 8), (8, 8), (0, 8)):
        raise ValueError('Framebuffer does not use BGRX byte order')
    if xoff + width > virtual_width or yoff + height > virtual_height:
        raise ValueError('Framebuffer viewport exceeds virtual dimensions')
    if stride < (xoff + width) * 4 or not 0 < memory <= 64_000_000:
        raise ValueError('Invalid framebuffer memory layout')
    offset = yoff * stride + xoff * 4
    if offset + (height - 1) * stride + width * 4 > memory:
        raise ValueError('Framebuffer viewport exceeds mapped memory')
    return width, height, stride, offset, memory


def paint(target, raw, layout):
    width, height, stride, offset, _ = layout
    row = width * 4
    for y in range(height):
        start = offset + y * stride
        target[start:start + row] = raw[y * row:(y + 1) * row]


def show(directory, seconds, brightness, boot):
    if os.geteuid() != 0:
        raise ValueError('Run on the phone as root')
    with Path('/run/platina-splash.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        done = Path('/run/platina-splash.done')
        if boot and done.exists() and done.read_text().strip() == boot_id:
            return
        manifest, raw = load_frame(directory)
        backlight = Path('/sys/class/backlight/backlight')
        power = backlight / 'bl_power'
        previous_power = power.read_text()
        level = max(1, int((backlight / 'max_brightness').read_text()) * brightness // 100)
        fb = os.open('/dev/fb0', os.O_RDWR | os.O_CLOEXEC)
        tty, previous = None, None
        try:
            var, fixed = bytearray(160), bytearray(80)
            fcntl.ioctl(fb, 0x4600, var, True)  # FBIOGET_VSCREENINFO
            fcntl.ioctl(fb, 0x4602, fixed, True)  # FBIOGET_FSCREENINFO
            layout = geometry(var, fixed)
            tty = os.open('/dev/tty0', os.O_RDWR | os.O_CLOEXEC)
            mode = bytearray(4)
            fcntl.ioctl(tty, 0x4B3B, mode, True)  # KDGETMODE
            previous = struct.unpack('=i', mode)[0]
            fcntl.ioctl(tty, 0x4B3A, 1)  # KD_GRAPHICS: console does not overwrite logo.
            fcntl.ioctl(fb, 0x4611, 0)  # FBIOBLANK / UNBLANK after the VT mode change.
            with mmap.mmap(fb, layout[4], access=mmap.ACCESS_WRITE) as screen:
                paint(screen, raw, layout)
                # FBIOBLANK can leave the backlight's independent power state off.
                power.write_text('0\n')
                (backlight / 'brightness').write_text(str(level) + '\n')
                # This confirms a memory write, not physical panel illumination.
                print(json.dumps({'framebuffer_written': manifest['version'], 'seconds': seconds,
                                  'brightness': level, 'boot_id': boot_id}), flush=True)
                time.sleep(seconds)
                (backlight / 'brightness').write_text('0\n')
                screen[:] = b'\0' * layout[4]
            if boot:
                done.write_text(boot_id + '\n')
        finally:
            (backlight / 'brightness').write_text('0\n')
            power.write_text(previous_power)
            if tty is not None:
                try:
                    if previous is not None:
                        fcntl.ioctl(tty, 0x4B3A, previous)
                finally:
                    os.close(tty)
            os.close(fb)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=CURRENT)
    parser.add_argument('--seconds', type=float, default=7)
    parser.add_argument('--brightness', type=int, default=25)
    parser.add_argument('--boot', action='store_true')
    parser.add_argument('--check', action='store_true', help='Validate installed assets without touching display')
    args = parser.parse_args()
    if not 1 <= args.seconds <= 10 or not 1 <= args.brightness <= 50:
        parser.error('Require 1–10 seconds and 1–50 percent brightness')
    if args.check:
        manifest, _ = load_frame(args.directory)
        print(manifest['name'], manifest['version'])
        return
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    show(args.directory, args.seconds, args.brightness, args.boot)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print('platina-splash:', str(error), file=sys.stderr)
        raise SystemExit(1)
