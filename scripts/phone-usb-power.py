#!/usr/bin/env python3
"""Apply an explicitly configured phone SDP limit only for a pinned USB host.

Install on the phone, not on either server. Unconfigured systems are unchanged.
The RPi hardware budget must be rechecked when its USB devices/PSU change.
"""
import json
import os
from pathlib import Path
import subprocess

CONFIG = Path('/etc/platina/usb-power.json')
SUPPLY = Path('/sys/class/power_supply/pm660-charger')


def apply(config, supply=SUPPLY, run=subprocess.run):
    if (supply / 'online').read_text().strip() != '1':
        return 'offline; unchanged'
    if '[SDP]' not in (supply / 'usb_type').read_text():
        return 'non-SDP supply; automatic charger policy unchanged'
    requested = config['max_current_uA']
    if requested not in (500000, 750000, 900000):
        raise ValueError('Unsupported SDP current limit')
    expected = config['rpi_host_ed25519'].split()
    if len(expected) < 2 or expected[0] != 'ssh-ed25519':
        raise ValueError('Invalid pinned host key')
    if config['other_usb_max_mA'] + requested // 1000 > config['rpi_usb_budget_mA']:
        raise ValueError('Configured RPi USB budget exceeded')
    route = run(['ip', 'route', 'get', '172.16.42.2'], capture_output=True, text=True, timeout=3)
    direct_usb = route.returncode == 0 and 'dev usb0' in route.stdout.splitlines()[0]
    matched = False
    if direct_usb:
        scan = run(['ssh-keyscan', '-4', '-T', '2', '-t', 'ed25519', '172.16.42.2'],
                   capture_output=True, text=True, timeout=4)
        for line in scan.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 3 and fields[1:3] == expected[:2]:
                matched = True
                break
    # An unknown USB host gets the standard limit, never the RPi exception.
    target = requested if matched else 500000
    (supply / 'current_max').write_text(str(target) + '\n')
    return ('pinned RPi' if matched else 'unverified host') + ': SDP limit requested ' + str(target) + ' uA'


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run on the phone as root')
    if not CONFIG.exists():
        return
    metadata = CONFIG.stat()
    if metadata.st_uid != 0 or metadata.st_mode & 0o022:
        raise SystemExit('Unsafe power policy ownership/permissions')
    try:
        print('platina-usb-power:', apply(json.loads(CONFIG.read_text())))
    except (OSError, ValueError, KeyError, IndexError, subprocess.TimeoutExpired) as error:
        # Do not expose host keys or command output in dispatcher logs.
        try:
            if '[SDP]' in (SUPPLY / 'usb_type').read_text():
                (SUPPLY / 'current_max').write_text('500000\n')
        except OSError:
            pass
        print('platina-usb-power: standard SDP limit retained;', type(error).__name__)


if __name__ == '__main__':
    main()
