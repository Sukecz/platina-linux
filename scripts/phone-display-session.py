#!/usr/bin/env python3
"""Temporary LCD power/wake session for the verified Platina 7.2.12 port.

No DRM detach, DT mutation or boot write. A matching, checksum-pinned module
must have been explicitly installed. A later proper panel port replaces this.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

BASE = Path('/usr/local/lib/platina/display')
PARAMS = Path('/sys/module/platina_panel_dcs/parameters')


def validate(base=BASE):
    identity = json.loads((base / 'module.json').read_text())
    if identity['kernel'] != os.uname().release:
        raise ValueError('LCD helper requires its exact build kernel; rebuild after upgrade')
    if b'xiaomi,platina\0' not in Path('/proc/device-tree/compatible').read_bytes():
        raise ValueError('Not a Platina phone')
    if 'mdss_dsi_tianma_fhd_nt36672a_video' not in Path('/proc/cmdline').read_text():
        raise ValueError('Not the verified Tianma panel')
    driver = Path('/sys/bus/mipi-dsi/devices/c994000.dsi.0/driver').resolve(strict=True).name
    if driver != 'panel-simple-dsi':
        raise ValueError('LCD workaround requires the original panel-simple driver')
    module = base / 'platina_panel_dcs.ko'
    if hashlib.sha256(module.read_bytes()).hexdigest() != identity['sha256']:
        raise ValueError('LCD module checksum mismatch')
    return module


def check_panel(params=PARAMS):
    values = {name: int((params / name).read_text()) for name in
              ('io_enabled', 'read_result', 'wake_result', 'power_after')}
    if (values['io_enabled'] != 1 or values['read_result'] != 1 or
            values['wake_result'] != 0 or values['power_after'] & 0x14 != 0x14):
        raise ValueError('LCD did not acknowledge sleep-out/display-on: ' + str(values))
    return values


def session(arguments):
    # Own the whole power/render/cleanup sequence, including manual invocations.
    with Path('/run/platina-display-session.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        module = validate()
        owned = False
        try:
            if not PARAMS.exists():
                # Mark ownership before insmod so a signal also cleans up a
                # module whose init completed just before the signal arrived.
                owned = True
                subprocess.run(['insmod', str(module), 'enable_iovcc=1', 'wake=1'], check=True)
            print(json.dumps({'panel_ready': check_panel()}), flush=True)
            renderer = subprocess.Popen(['/usr/local/sbin/platina-splash', *arguments])
            try:
                return renderer.wait()
            finally:
                if renderer.poll() is None:
                    renderer.terminate()
                    try:
                        renderer.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        renderer.kill()
                        renderer.wait()
        finally:
            if owned and PARAMS.exists():
                # Brightness is cleared even if the renderer failed or timed out.
                Path('/sys/class/backlight/backlight/brightness').write_text('0\n')
                subprocess.run(['rmmod', 'platina_panel_dcs'], check=True)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        raise SystemExit(session(sys.argv[1:]))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print('platina-display-session:', error, file=sys.stderr)
        raise SystemExit(1)
