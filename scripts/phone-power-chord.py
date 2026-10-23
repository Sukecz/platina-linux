#!/usr/bin/env python3
"""Power + Volume Up, held together and fully released, requests orderly shutdown."""
import argparse
import fcntl
import os
from pathlib import Path
import select
import signal
import stat
import struct
import subprocess
import sys

KEY_POWER, KEY_VOLUMEUP = 116, 115
KEYS = {KEY_POWER, KEY_VOLUMEUP}
DEVICES = {KEY_POWER: 'pm8941_pwrkey', KEY_VOLUMEUP: 'Volume up'}
EVENT = struct.Struct('@llHHi')


class ChordPolicy:
    def __init__(self, seconds=3, held=()):
        if not 1 <= seconds <= 5:
            raise ValueError('Choose a hold of 1 to 5 seconds, below the PMIC emergency reset')
        self.seconds = seconds
        self.last = None
        self.resync(held)

    def resync(self, held):
        self.pressed = set(held) & KEYS
        self.blocked = bool(self.pressed)
        self.started = None
        self.qualified = False

    def event(self, key, value, timestamp):
        if key not in KEYS or value not in (0, 1):
            return None
        if self.last is not None and timestamp < self.last:
            self.resync(self.pressed | {key})
        self.last = timestamp
        if value == 1:
            if key in self.pressed:
                return None
            if self.qualified:  # A re-press before both releases cancels the gesture.
                self.blocked, self.qualified = True, False
            self.pressed.add(key)
            if self.pressed == KEYS and not self.blocked:
                self.started = timestamp
            return None
        if key not in self.pressed:
            return None
        if self.started is not None:
            self.qualified = not self.blocked and timestamp - self.started >= self.seconds
            self.started = None
        self.pressed.remove(key)
        if not self.pressed:
            action = 'poweroff' if self.qualified and not self.blocked else None
            self.resync(())
            return action
        return None


def find_devices(sys_input=Path('/sys/class/input'), dev_input=Path('/dev/input')):
    result = {}
    for key, name in DEVICES.items():
        matches = []
        for entry in sys_input.glob('event*'):
            try:
                if (entry / 'device/name').read_text().strip() == name:
                    matches.append(dev_input / entry.name)
            except OSError:
                continue
        if len(matches) != 1:
            raise ValueError('Expected exactly one physical input: ' + name)
        result[key] = matches[0]
    return result


def key_held(fd, key):
    bits = bytearray(96)
    fcntl.ioctl(fd, 0x80004518 | (len(bits) << 16), bits, True)
    return bool(bits[key // 8] & (1 << (key % 8)))


def log(message):
    print('platina-power-chord:', message, flush=True)


def dispatch(dry_run):
    if dry_run:
        log('TEST ONLY: Power + Volume Up accepted; would show Power off and shut down')
        return
    # A separate session keeps the renderer alive while OpenRC stops this monitor.
    child = subprocess.Popen(['/usr/local/sbin/platina-poweroff'], start_new_session=True)
    code = child.wait()
    if code:
        raise RuntimeError('Shutdown helper failed; exit ' + str(code))


def monitor(seconds, dry_run):
    if os.geteuid() != 0:
        raise ValueError('Run on the phone as root')
    if b'xiaomi,platina\0' not in Path('/proc/device-tree/compatible').read_bytes():
        raise ValueError('This service requires Platina')
    descriptors, dropped = {}, set()
    try:
        for key, device in find_devices().items():
            fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            descriptors[fd] = key
            if not stat.S_ISCHR(os.fstat(fd).st_mode):
                raise ValueError('Input is not a character device')
            name = bytearray(128)
            fcntl.ioctl(fd, 0x80004506 | (len(name) << 16), name, True)
            if bytes(name).split(b'\0')[0].decode() != DEVICES[key]:
                raise ValueError('Input identity changed')
            fcntl.ioctl(fd, 0x400445A0, struct.pack('i', 1))  # Monotonic timestamps.
            fcntl.ioctl(fd, 0x40044590, 1)  # EVIOCGRAB; no console actions.
        def held():
            return {key for fd, key in descriptors.items() if key_held(fd, key)}
        policy = ChordPolicy(seconds, held())
        log(('TEST ONLY' if dry_run else 'ACTIVE') + f'; hold both >= {seconds:g}s; release BOTH to power off')
        while True:
            ready, _, _ = select.select(list(descriptors), [], [])
            events = []
            for fd in ready:
                data = os.read(fd, EVENT.size * 64)
                if not data or len(data) % EVENT.size:
                    raise ValueError('Disconnected or truncated input')
                for offset in range(0, len(data), EVENT.size):
                    sec, usec, typ, code, value = EVENT.unpack_from(data, offset)
                    events.append((sec + usec / 1e6, fd, typ, code, value))
            for timestamp, fd, typ, code, value in sorted(events):
                if typ == 0 and code == 3:  # SYN_DROPPED: cancel both keys.
                    dropped.add(fd)
                    policy.resync(KEYS)
                    log('lost input events; pending chord cancelled')
                elif typ == 0 and code == 0 and fd in dropped:
                    dropped.remove(fd)
                    policy.resync(held())
                elif typ == 1 and code == descriptors[fd] and not dropped:
                    action = policy.event(code, value, timestamp)
                    if value in (0, 1):
                        log(DEVICES[code] + (' pressed' if value else ' released'))
                    if action:
                        log('complete chord accepted')
                        dispatch(dry_run)
    finally:
        for fd in descriptors:
            os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hold-seconds', type=float, default=3)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    ChordPolicy(args.hold_seconds)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    monitor(args.hold_seconds, args.dry_run)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        log(str(error))
        raise SystemExit(1)
