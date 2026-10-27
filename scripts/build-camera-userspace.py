#!/usr/bin/env python3
"""Build scoped camera userspace components locally; never deploy or flash."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def hashes(directory):
    result = {}
    for path in sorted(directory.iterdir()):
        if path.name == '__pycache__' and path.is_dir() and not path.is_symlink():
            continue
        if not path.is_file() or path.is_symlink():
            raise ValueError('Unexpected camera recipe entry: ' + path.name)
        result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component', choices=('userspace', 'mesa'), default='userspace')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--lax', action='store_true', help='Reuse existing build chroots')
    args = parser.parse_args()
    folder, package = {'userspace': ('libcamera-headless', 'platina-libcamera'),
                       'mesa': ('mesa-freedreno', 'platina-mesa-freedreno')}[args.component]
    source = ROOT / 'project/camera' / folder
    managed = ROOT / 'sources/pmaports-managed-candidate'
    destination = managed / 'device/testing' / package
    stamp = managed / ('.platina-camera-' + args.component + '.json')
    config = ROOT / 'config/pmbootstrap-managed-candidate.cfg'
    if not config.is_file() or not (managed / '.platina-managed.json').is_file():
        raise ValueError('Prepare the managed candidate profile first')
    expected = hashes(source)
    if destination.exists():
        if not stamp.is_file() or hashes(destination) != json.loads(stamp.read_text())['files']:
            raise ValueError('Preserve/review existing camera recipe edits before updating')
    else:
        destination.mkdir()
    for path in destination.iterdir():
        if path.name not in expected:
            path.unlink()
    for name in expected:
        shutil.copyfile(source / name, destination / name)
    stamp.write_text(json.dumps({'files': expected}, indent=2) + '\n')
    if not args.prepare_only:
        command = ['python3', str(ROOT / 'tools/pmbootstrap/pmbootstrap.py'),
                   '-c', str(config), 'build', '--arch', 'aarch64', package]
        if args.lax:
            command.append('--lax')
        subprocess.run(command, check=True)
    print('Camera runtime prepared/built locally; no phone action performed.')


if __name__ == '__main__':
    main()
