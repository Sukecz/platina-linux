#!/usr/bin/env python3
"""Local project workflow: checks, pinned builds and offline audits; no deployment."""
import argparse
import configparser
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ('device-xiaomi-platina', 'firmware-xiaomi-platina', 'linux-postmarketos-qcom-sdm660')
ARCHIVES = {'linux-v6.19.10-sdm660.tar.gz',
            'linux-dd1ed52c8ceef4f16715118ed0252fe75adbe71d.tar.gz'}


def run(command, **kwargs):
    return subprocess.run(command, cwd=ROOT, check=True, **kwargs)


def lock():
    data = json.loads((ROOT / 'project/sources.lock.json').read_text())
    if data['schema'] != 1:
        raise ValueError('Unsupported source lock schema')
    return data


def digest(path, algorithm='sha256'):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def child(directory, name):
    relative = Path(name)
    if not name or relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Unsafe manifest path')
    target = directory / relative
    if not target.resolve().is_relative_to(directory.resolve()):
        raise ValueError('Manifest path escapes bundle')
    if any((directory / Path(*relative.parts[:i])).is_symlink()
           for i in range(1, len(relative.parts) + 1)):
        raise ValueError('Manifest symlinks are not accepted')
    if not target.is_file():
        raise ValueError('Missing manifest file: ' + name)
    return target


def verify(directory):
    directory = directory.resolve()
    files = json.loads((directory / 'manifest.json').read_text())['files']
    if not isinstance(files, list) or not files:
        raise ValueError('Manifest needs a nonempty files list')
    seen = set()
    for row in files:
        name = row['file']
        target = child(directory, name)
        canonical = str(target.relative_to(directory))
        if canonical in seen:
            raise ValueError('Duplicate manifest file')
        seen.add(canonical)
        if not re.fullmatch(r'[a-f0-9]{64}', row['sha256']):
            raise ValueError('Invalid SHA256')
        if target.stat().st_size != row['bytes'] or digest(target) != row['sha256']:
            raise ValueError('Artifact verification failed: ' + name)
    print(f'OK: {len(files)} artifact hashes and lengths; hardware status unchanged')


def checksums(recipe):
    rows = re.findall(r'^([a-f0-9]{128})[ \t]+([^\r\n]+)$', recipe.read_text(), re.M)
    if not rows:
        raise ValueError('No recipe checksums: ' + recipe.parent.name)
    return {name.strip(): value for value, name in rows}


def recipe_checks(directory, external):
    # Parse only: never evaluate arbitrary APKBUILD shell code on the host.
    for name in RECIPES:
        recipe = directory / name / 'APKBUILD'
        for filename, expected in checksums(recipe).items():
            if filename in external:
                continue
            if '/' in filename or filename in ('.', '..'):
                raise ValueError('Unsafe recipe source path')
            source = recipe.parent / filename
            if not source.is_file() or source.is_symlink() or digest(source, 'sha512') != expected:
                raise ValueError('Recipe input missing or changed: ' + name + '/' + filename)
        install = re.search(r'^install="\$pkgname([^"\n]+)"$', recipe.read_text(), re.M)
        if install and not (recipe.parent / (name + install[1])).is_file():
            raise ValueError('Missing package install hook: ' + name)


def check():
    # Explicit roots avoid traversing build mounts, private files and external repos.
    candidates = [ROOT / name for name in
                  ('README.md', 'AGENTS.md', 'CONTRIBUTING.md', 'CHANGELOG.md',
                   'Makefile', '.gitignore', '.gitattributes', 'LICENSE', 'NOTICE')
                  if (ROOT / name).is_file()]
    for name in ('scripts', 'tests', 'ports', 'project', '.github', 'docs', 'LICENSES'):
        candidates += [p for p in (ROOT / name).rglob('*')
                       if p.is_file() and '__pycache__' not in p.parts]
    private_key = re.compile(rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----')
    credential = re.compile(rb'(?im)^\s*(?:psk|password|TELEGRAM_BOT_TOKEN|api_key)\s*=\s*["\']?[^\s"\'\n]{6,}')
    for path in candidates:
        if path.is_symlink():
            if not path.resolve().is_relative_to(ROOT) or not path.exists():
                raise ValueError('Broken or external project symlink: ' + str(path.relative_to(ROOT)))
            continue
        data = path.read_bytes()
        if private_key.search(data) or credential.search(data):
            raise ValueError('Possible secret in project file (value suppressed): ' + str(path.relative_to(ROOT)))
        if path.suffix == '.py':
            compile(data, str(path), 'exec')
        elif path.suffix in ('.sh', '.start', '.post-install') or path.name == 'APKBUILD' or data.startswith((b'#!/bin/sh', b'#!/sbin/openrc-run')):
            run(['sh', '-n', str(path)], stdout=subprocess.DEVNULL)
    release = json.loads((ROOT / 'project/release.json').read_text())
    if (release.get('schema') != 1 or release.get('name') != 'Platina Linux'
            or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', release.get('version', ''))):
        raise ValueError('Invalid Platina project version')
    branding = ROOT / 'project/branding'
    provenance = json.loads((branding / 'provenance.json').read_text())
    if digest(branding / 'platina-linux-logo.png') != provenance['sha256']:
        raise ValueError('Logo changed without updating provenance')
    data = lock()
    for profile in data['profiles'].values():
        recipe_checks(ROOT / profile['ports'], set(data['local_firmware']) | ARCHIVES)
        for package, field in zip(RECIPES, ('device_package', 'firmware_package', 'kernel_package')):
            text = (ROOT / profile['ports'] / package / 'APKBUILD').read_text()
            version = re.search(r'^pkgver=(\S+)$', text, re.M)[1]
            release = re.search(r'^pkgrel=(\d+)$', text, re.M)[1]
            if version + '-r' + release != profile[field]:
                raise ValueError('Profile version differs from recipe: ' + package)
    if (ROOT / '.git').is_dir():
        tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
        allowed = {str(p.relative_to(ROOT)) for p in candidates} | {'PLAN.md'}
        if any(name and name not in allowed for name in tracked):
            raise ValueError('Unexpected tracked path; review Git index')
        run(['git', 'diff', '--check'])
        run(['git', 'diff', '--cached', '--check'])
    run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'])
    print(f'OK: syntax, secret patterns, recipe checksums, profile versions and tests ({len(candidates)} files)')


def repo_at(path, source, fetch):
    if path.exists():
        actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != source['commit']:
            raise ValueError('Checkout differs from source lock: ' + str(path.relative_to(ROOT)))
        return
    if not fetch:
        raise ValueError('Missing checkout; use prepare --fetch for explicit source download')
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.platina-', dir=path.parent) as temporary:
        temp = Path(temporary) / 'checkout'
        run(['git', 'init', '-q', str(temp)])
        run(['git', '-C', str(temp), 'remote', 'add', 'origin', source['url']])
        run(['git', '-C', str(temp), 'fetch', '--depth=1', 'origin', source['commit']])
        run(['git', '-C', str(temp), 'checkout', '--detach', source['commit']])
        temp.rename(path)


def config_path(profile):
    return ROOT / 'config' / ('pmbootstrap-managed-' + profile + '.cfg')


def managed_path(profile):
    return ROOT / 'sources' / ('pmaports-managed-' + profile)


def port_files(directory):
    result = {}
    for name in RECIPES:
        for path in sorted((directory / name).rglob('*')):
            if path.is_symlink():
                raise ValueError('Unexpected symlink in managed recipes')
            if path.is_file():
                result[str(path.relative_to(directory))] = digest(path)
    return result


def write_stamp(profile):
    destination = managed_path(profile)
    data = {'profile': profile, 'files': port_files(destination / 'device/testing')}
    (destination / '.platina-managed.json').write_text(json.dumps(data, indent=2) + '\n')


def sync(profile):
    data = lock()
    definition = data['profiles'][profile]
    destination = managed_path(profile)
    stamp = json.loads((destination / '.platina-managed.json').read_text())
    if stamp['profile'] != profile or port_files(destination / 'device/testing') != stamp['files']:
        raise ValueError('Managed recipes were edited locally; preserve and review before sync')
    recipe_checks(ROOT / definition['ports'], set(data['local_firmware']) | ARCHIVES)
    firmware = destination / 'device/testing/firmware-xiaomi-platina'
    sums = checksums(ROOT / definition['ports'] / 'firmware-xiaomi-platina/APKBUILD')
    for name in data['local_firmware']:
        if digest(firmware / name, 'sha512') != sums[name]:
            raise ValueError('Firmware changed; prepare a new isolated profile')
    new_files = port_files(ROOT / definition['ports'])
    for name in stamp['files'].keys() - new_files.keys():
        if Path(name).name not in data['local_firmware']:
            (destination / 'device/testing' / name).unlink()
    for name in new_files:
        target = destination / 'device/testing' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / definition['ports'] / name, target)
    write_stamp(profile)
    print('Managed recipes synchronized; no build or device action performed.')


@contextmanager
def build_slot():
    (ROOT / 'logs').mkdir(exist_ok=True)
    with (ROOT / 'logs/managed-build.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another managed build/prepare/sync is running') from None
        yield


def prepare(profile, fetch):
    data = lock()
    definition = data['profiles'][profile]
    destination = managed_path(profile)
    cfg_path = config_path(profile)
    if destination.exists() or cfg_path.exists():
        raise ValueError('Managed profile already exists; preserve it and review changes manually')
    recipe_checks(ROOT / definition['ports'], set(data['local_firmware']) | ARCHIVES)
    sums = checksums(ROOT / definition['ports'] / 'firmware-xiaomi-platina/APKBUILD')
    blob_sources = []
    for name in data['local_firmware']:
        options = [ROOT / 'config/firmware' / name,
                   ROOT / 'sources/pmaports-server/device/testing/firmware-xiaomi-platina' / name]
        source = next((p for p in options if p.is_file()), None)
        if source is None or digest(source, 'sha512') != sums[name]:
            raise ValueError('Missing or incorrect local firmware: ' + name + '; see docs/DEVELOPMENT.md')
        blob_sources.append(source)
    if not list((ROOT / 'config').glob('admin-*.pub')):
        raise ValueError('Add your public SSH key as config/admin-*.pub before preparing a server image')
    repo_at(ROOT / data['repositories']['pmbootstrap']['path'], data['repositories']['pmbootstrap'], fetch)
    # Clone committed objects only; the existing pmaports index and edits are preserved.
    source = ROOT / 'sources/pmaports-server'
    if source.exists():
        run(['git', 'clone', '--no-hardlinks', '--no-checkout', str(source), str(destination)])
        run(['git', '-C', str(destination), 'checkout', '--detach', data['repositories']['pmaports']['commit']])
    else:
        repo_at(destination, data['repositories']['pmaports'], fetch)
    # The channel table lives on main, independently of the pinned release tree.
    channels = data['repositories']['pmaports'].get('channels_commit')
    if channels:
        run(['git', '-C', str(destination), 'fetch', '--depth=1',
             str(source) if source.exists() else data['repositories']['pmaports']['url'],
             channels])
        run(['git', '-C', str(destination), 'update-ref', 'refs/remotes/origin/main', channels])
    # pmbootstrap identifies the checkout by its canonical remote URL.
    run(['git', '-C', str(destination), 'remote', 'set-url', 'origin',
         data['repositories']['pmaports']['url']])
    for name in RECIPES:
        target = destination / 'device/testing' / name
        if target.exists():
            shutil.rmtree(target)  # Only in the newly created checkout above.
        shutil.copytree(ROOT / definition['ports'] / name, target)
    for source in blob_sources:
        shutil.copyfile(source, destination / 'device/testing/firmware-xiaomi-platina' / source.name)
    write_stamp(profile)
    for name in ('config', 'logs', 'reports', 'artifacts', 'work'):
        (ROOT / name).mkdir(exist_ok=True)
    cfg = configparser.ConfigParser()
    cfg['pmbootstrap'] = {
        'aports': str(destination), 'work': str(ROOT / 'work' / ('pmbootstrap-managed-' + profile)),
        'device': 'xiaomi-platina', 'hostname': 'platina', 'user': 'server', 'ui': 'none',
        'ui_extras': 'False', 'service_manager': 'openrc', 'timezone': 'Europe/Prague',
        'locale': 'C.UTF-8', 'jobs': '2', 'ssh_keys': 'True', 'extra_packages': 'chrony',
        'auto_zap_misconfigured_chroots': 'no',
        'ssh_key_glob': str(ROOT / 'config/admin-*.pub'), 'is_default_channel': 'False'}
    cfg['providers'] = {}
    cfg['mirrors'] = {}
    with cfg_path.open('x') as stream:
        cfg.write(stream)
    print('Prepared isolated ' + profile + ' profile. No build or device action performed.')


def pmb(profile):
    cfg = config_path(profile)
    if not cfg.is_file():
        raise ValueError('Run prepare --profile ' + profile + ' first')
    data = lock()
    tool = ROOT / data['repositories']['pmbootstrap']['path']
    repo_at(tool, data['repositories']['pmbootstrap'], False)
    destination = managed_path(profile)
    repo_at(destination, data['repositories']['pmaports'], False)
    config = configparser.ConfigParser()
    config.read(cfg)
    if (config['pmbootstrap']['aports'] != str(destination)
            or config['pmbootstrap']['work'] != str(ROOT / 'work' / ('pmbootstrap-managed-' + profile))):
        raise ValueError('Managed config paths changed; review before building')
    stamp = json.loads((destination / '.platina-managed.json').read_text())
    if stamp['files'] != port_files(destination / 'device/testing'):
        raise ValueError('Managed recipes changed; preserve and review local edits')
    for name, expected in port_files(ROOT / data['profiles'][profile]['ports']).items():
        if stamp['files'].get(name) != expected:
            raise ValueError('Versioned recipes changed; run sync --profile ' + profile)
    return ['nice', '-n', '10', sys.executable, str(tool / 'pmbootstrap.py'), '-c', str(cfg), '-j', '2']


def doctor():
    for name in ('git', 'python3', 'make', 'sh', 'sudo', 'debugfs', 'blkid', 'ssh'):
        print(name + ': ' + ('available' if shutil.which(name) else 'missing'))
    data = lock()
    tool = ROOT / data['repositories']['pmbootstrap']['path']
    print('pmbootstrap checkout: ' + ('present' if tool.exists() else 'missing; prepare --fetch'))
    for profile in data['profiles']:
        print(profile + ' managed config: ' + ('present' if config_path(profile).is_file() else 'not prepared'))
    print('Read-only local check; phone, USB ports and services were not probed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('check', 'doctor'):
        commands.add_parser(name)
    prep = commands.add_parser('prepare', help='Create isolated local build checkout/config')
    prep.add_argument('--profile', choices=tuple(lock()['profiles']), default='candidate')
    prep.add_argument('--fetch', action='store_true', help='Allow downloading pinned Git sources')
    syncing = commands.add_parser('sync', help='Refresh managed recipes, preserving local edits on conflict')
    syncing.add_argument('--profile', choices=tuple(lock()['profiles']), default='candidate')
    kernel = commands.add_parser('kernel', help='Build a kernel locally; no phone connection')
    kernel.add_argument('--profile', choices=tuple(lock()['profiles']), default='candidate')
    images = commands.add_parser('images', help='Build candidate images locally')
    images.add_argument('--output', required=True, help='New candidate-* artifact directory')
    for name in ('verify', 'audit'):
        command = commands.add_parser(name, help='Offline artifact ' + name)
        command.add_argument('directory', type=Path)
    args = parser.parse_args()
    if args.command == 'check':
        check()
    elif args.command == 'doctor':
        doctor()
    elif args.command == 'prepare':
        with build_slot():
            prepare(args.profile, args.fetch)
    elif args.command == 'sync':
        with build_slot():
            sync(args.profile)
    elif args.command == 'kernel':
        with build_slot():
            run(pmb(args.profile) + ['build', '--arch', 'aarch64', 'linux-postmarketos-qcom-sdm660'])
    elif args.command == 'images':
        with build_slot():
            pmb('candidate')
            run([sys.executable, str(ROOT / 'scripts/build-candidate-images.py'),
                 '--config', str(config_path('candidate')), '--output-name', args.output])
    elif args.command == 'verify':
        verify(args.directory)
    elif args.command == 'audit':
        verify(args.directory)
        (ROOT / 'reports').mkdir(exist_ok=True)
        run([sys.executable, str(ROOT / 'scripts/audit-candidate-artifacts.py'),
             '--directory', str(args.directory.resolve())])


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
