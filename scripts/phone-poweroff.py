#!/usr/bin/env python3
"""Show the verified Power off screen, then request an orderly init shutdown."""
import argparse
import fcntl
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import time


def request_shutdown():
    subprocess.run(['/usr/sbin/poweroff'], check=True, timeout=10)
    print('platina-poweroff: init accepted shutdown; keeping screen until shutdown', flush=True)
    # Shutdown should terminate this process. If it does not, restore the display
    # instead of leaving an indefinite claim that the phone is already off.
    time.sleep(30)
    raise RuntimeError('Shutdown did not finish within 30 seconds')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', action='store_true', help='Show the screen for 5s without shutting down')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise ValueError('Run on the phone as root')
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    control = runpy.run_path('/usr/local/sbin/platina-display', run_name='poweroff_display')
    directory = Path('/usr/local/share/platina/current/poweroff')
    with Path('/run/platina-poweroff.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with control['device']() as fb:
            control['show'](fb, directory, 5 if args.preview else 3, 25,
                            after_display=None if args.preview else request_shutdown)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print('platina-poweroff:', error, file=sys.stderr)
        raise SystemExit(1)
