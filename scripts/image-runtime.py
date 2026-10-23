#!/usr/bin/env python3
"""Prepare or audit the runtime overlay for a new offline Platina image."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import runpy
import shutil
import stat
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'usr/local/share/platina/image-runtime.json'
HELPERS = {
    'scripts/phone-splash.py': 'usr/local/sbin/platina-splash',
    'scripts/phone-display.py': 'usr/local/sbin/platina-display',
    'scripts/phone-display-session.py': 'usr/local/sbin/platina-display-session',
    'scripts/phone-poweroff.py': 'usr/local/sbin/platina-poweroff',
    'scripts/phone-power-chord.py': 'usr/local/sbin/platina-power-chord',
    'scripts/phone-power-chord.openrc': 'etc/init.d/platina-power-chord',
    'scripts/phone-headless.start': 'etc/local.d/platina-headless.start',
    'scripts/phone-usb-power.py': 'usr/local/sbin/platina-usb-power',
    'scripts/phone-usb-power-dispatcher.sh': 'etc/NetworkManager/dispatcher.d/90-platina-usb-power',
    'scripts/image-runtime.py': 'usr/local/libexec/platina-image-runtime',
}
CONFIG = 'etc/conf.d/platina-power-chord'


def layout(version):
    if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version):
        raise ValueError('Invalid runtime release')
    base = 'usr/local/share/platina/releases/' + version
    modes = {name: 0o755 for name in HELPERS.values()}
    modes[CONFIG] = 0o644
    for sub in ('', 'poweroff/'):
        for name in ('release.json', 'version', 'frame.bgrx.gz'):
            modes[base + '/' + sub + name] = 0o644
    links = {'usr/local/share/platina/current': 'releases/' + version,
             'etc/platina-release': '../usr/local/share/platina/current/version',
             'etc/runlevels/default/platina-power-chord': '../../init.d/platina-power-chord'}
    return base, modes, links


def source_inputs():
    names = list(HELPERS) + ['scripts/phone-power-chord.conf',
                            'scripts/platina-release.py', 'project/release.json',
                            'project/branding/platina-linux-logo.png',
                            'project/branding/provenance.json']
    return {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in names}


def audit_contents(manifest, read):
    """Also used against the exported ext4 image, with a read-only debugfs reader."""
    if manifest.get('schema') != 1 or manifest.get('name') != 'Platina Linux image runtime':
        raise ValueError('Unknown image runtime manifest')
    version = manifest['version']
    base, modes, links = layout(version)
    if set(manifest['files']) != set(modes) or manifest['symlinks'] != links:
        raise ValueError('Image runtime file set differs from the supported layout')
    payload = {}
    for name, mode in modes.items():
        data = read(name)
        row = manifest['files'][name]
        if row['mode'] != mode or row['bytes'] != len(data) or row['sha256'] != hashlib.sha256(data).hexdigest():
            raise ValueError('Image runtime checksum/metadata mismatch: ' + name)
        payload[name] = data
    if b'hold_seconds=3\n' not in payload[CONFIG] or b'dry_run=no\n' not in payload[CONFIG]:
        raise ValueError('Shutdown chord must use the verified active policy')
    for sub in ('', 'poweroff/'):
        prefix = base + '/' + sub
        release = json.loads(payload[prefix + 'release.json'])
        if release['name'] != 'Platina Linux' or release['version'] != version:
            raise ValueError('Runtime and screen release differ')
        if payload[prefix + 'version'] != ('Platina Linux ' + version + '\n').encode():
            raise ValueError('Screen version file differs')
        display = release['display']
        if (display['width'], display['height'], display['format'], display['raw_bytes'], display['frame']) != (
                1080, 2280, 'BGRX8888', 1080 * 2280 * 4, 'frame.bgrx.gz'):
            raise ValueError('Unsupported image screen layout')
        compressed = payload[prefix + 'frame.bgrx.gz']
        if hashlib.sha256(compressed).hexdigest() != display['compressed_sha256']:
            raise ValueError('Screen compressed checksum mismatch')
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            raw = stream.read(display['raw_bytes'] + 1)
        if len(raw) != display['raw_bytes'] or hashlib.sha256(raw).hexdigest() != display['raw_sha256']:
            raise ValueError('Screen decoded checksum mismatch')
    return {'version': version, 'runtime_files': len(modes), 'screens_verified': 2,
            'power_chord_active': True, 'usb_poweroff_requires_unplug': True}


def audit(root):
    root = root.resolve()
    manifest = json.loads((root / MANIFEST).read_text())
    result = audit_contents(manifest, lambda n: (root / n).read_bytes())
    _, modes, links = layout(manifest['version'])
    for name, mode in modes.items():
        path = root / name
        if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != mode:
            raise ValueError('Runtime file mode/type mismatch: ' + name)
        if not path.resolve().is_relative_to(root):
            raise ValueError('Runtime file escapes image root')
    for name, target in links.items():
        path = root / name
        if not path.is_symlink() or str(path.readlink()) != target or not path.exists():
            raise ValueError('Runtime symlink mismatch: ' + name)
    return result


def prepare(output):
    if output.exists():
        raise ValueError('Preserve existing runtime overlay; choose a new directory')
    before = source_inputs()
    release = runpy.run_path(str(ROOT / 'scripts/platina-release.py'))
    version = release['load_release']()['version']
    base, modes, links = layout(version)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Build completely in a private sibling directory before publishing the overlay.
    with tempfile.TemporaryDirectory(prefix='.platina-runtime-', dir=output.parent) as temporary:
        stage = Path(temporary) / 'rootfs'
        stage.mkdir()
        screens = Path(temporary) / 'screens'
        release['build'](screens)
        for source, target in HELPERS.items():
            dest = stage / target
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / source, dest)
        conf = (ROOT / 'scripts/phone-power-chord.conf').read_bytes()
        if conf.count(b'dry_run=yes\n') != 1:
            raise ValueError('Manual deployment config changed; review image activation')
        dest = stage / CONFIG
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(conf.replace(b'dry_run=yes\n', b'dry_run=no\n'))
        for sub in ('', 'poweroff/'):
            for name in ('release.json', 'version', 'frame.bgrx.gz'):
                dest = stage / base / sub / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(screens / sub / name, dest)
        for name, mode in modes.items():
            (stage / name).chmod(mode)
        for name, target in links.items():
            dest = stage / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.symlink_to(target)
        for directory in stage.rglob('*'):
            if directory.is_dir() and not directory.is_symlink():
                directory.chmod(0o755)
        manifest = {'schema': 1, 'name': 'Platina Linux image runtime', 'version': version,
                    'source_inputs_sha256': before, 'symlinks': links,
                    'files': {name: {'mode': mode, 'bytes': (stage / name).stat().st_size,
                                    'sha256': hashlib.sha256((stage / name).read_bytes()).hexdigest()}
                              for name, mode in modes.items()}}
        (stage / MANIFEST).write_text(json.dumps(manifest, indent=2) + '\n')
        (stage / MANIFEST).chmod(0o644)
        result = audit(stage)
        if source_inputs() != before:
            raise ValueError('Runtime sources changed during asset generation')
        stage.rename(output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('prepare', help='Build local rootfs overlay; never deploy')
    build.add_argument('--output', type=Path, required=True)
    check = sub.add_parser('audit', help='Verify installed files without accessing hardware')
    check.add_argument('--root', type=Path, default=Path('/'))
    args = parser.parse_args()
    print(json.dumps(prepare(args.output.resolve()) if args.command == 'prepare' else audit(args.root)))


if __name__ == '__main__':
    main()
