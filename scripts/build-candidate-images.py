#!/usr/bin/env python3
"""Build and audit isolated candidate images locally; never writes to a phone."""
import argparse
import configparser
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work/pmbootstrap-candidate-7.2'
OUTPUT = ROOT / 'artifacts/candidate-7.2'
KERNEL_RELEASE = '7.2.12-sdm660'
STATUS = ROOT / 'logs/candidate-image-status.json'
PMB = ['nice', '-n', '10', 'python3', str(ROOT / 'tools/pmbootstrap/pmbootstrap.py'),
       '-c', str(ROOT / 'config/pmbootstrap-candidate-7.2.cfg'), '-j', '2']


def provenance(config_path, config):
    def revision(directory):
        result = subprocess.run(['git', '-C', str(directory), 'rev-parse', 'HEAD'],
                                capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    recipes = Path(config['pmbootstrap']['aports']) / 'device/testing'
    inputs = {}
    for package in ('device-xiaomi-platina', 'firmware-xiaomi-platina',
                    'linux-postmarketos-qcom-sdm660'):
        for path in sorted((recipes / package).iterdir()):
            if path.is_file():
                with path.open('rb') as stream:
                    inputs[str(path.relative_to(recipes))] = hashlib.file_digest(stream, 'sha256').hexdigest()
    dirty = subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain'],
                           capture_output=True, text=True)
    return {'project_commit': revision(ROOT),
            'project_dirty': bool(dirty.stdout.strip()) if dirty.returncode == 0 else None,
            'pmaports_commit': revision(recipes.parents[1]),
            'pmbootstrap_commit': revision(ROOT / 'tools/pmbootstrap'),
            'config_sha256': hashlib.sha256(config_path.read_bytes()).hexdigest(),
            'recipe_inputs_sha256': inputs}


def record(phase, **details):
    row = {'time': datetime.datetime.now().astimezone().isoformat(),
           'phase': phase, 'flashed': False, **details}
    STATUS.write_text(json.dumps(row, indent=2) + '\n')
    print(phase, flush=True)


def run(*args, script=None):
    if script:
        with (ROOT / 'scripts' / script).open() as stream:
            subprocess.run(PMB + list(args), cwd=ROOT, stdin=stream, check=True)
    else:
        subprocess.run(PMB + list(args), cwd=ROOT, check=True)


def main():
    global OUTPUT, WORK, PMB, KERNEL_RELEASE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/pmbootstrap-candidate-7.2.cfg',
                        help='Absolute project pmbootstrap config; work is derived from it')
    parser.add_argument('--resume-image', action='store_true',
                        help='Resume hardening/audit of the already created candidate image')
    parser.add_argument('--output-name', default='candidate-7.2',
                        help='New candidate-* directory under artifacts; existing output is preserved')
    args = parser.parse_args()
    config_path = args.config.resolve()
    config = configparser.ConfigParser()
    if not config.read(config_path):
        raise ValueError('Missing pmbootstrap config')
    WORK = Path(config['pmbootstrap']['work'])
    if not WORK.is_absolute() or not WORK.resolve().is_relative_to(ROOT / 'work'):
        raise ValueError('Build work must be an absolute path inside project work/')
    PMB = ['nice', '-n', '10', 'python3', str(ROOT / 'tools/pmbootstrap/pmbootstrap.py'),
           '-c', str(config_path), '-j', '2']
    (ROOT / 'logs').mkdir(exist_ok=True)
    (ROOT / 'artifacts').mkdir(exist_ok=True)
    if not re.fullmatch(r'candidate-[A-Za-z0-9][A-Za-z0-9._-]*', args.output_name):
        raise ValueError('Output name must be a simple candidate-* directory name')
    OUTPUT = ROOT / 'artifacts' / args.output_name
    if OUTPUT.exists():
        raise RuntimeError('Preserve existing candidate artifacts; use a new output directory')
    build_sources = provenance(config_path, config)
    recipe = Path(config['pmbootstrap']['aports']) / 'device/testing/linux-postmarketos-qcom-sdm660/APKBUILD'
    recipe_text = recipe.read_text()
    version = re.search(r'^pkgver=([0-9][0-9.]*)$', recipe_text, re.M)
    release = re.search(r'^pkgrel=([0-9]+)$', recipe_text, re.M)
    if not version or not release:
        raise ValueError('Cannot determine kernel version from APKBUILD')
    KERNEL_RELEASE = version[1] + '-sdm660'
    apk_version = version[1] + '-r' + release[1]
    packages = list((WORK / 'packages').glob('**/linux-postmarketos-qcom-sdm660-' + apk_version + '.apk'))
    if not packages:
        raise RuntimeError('Kernel APK must finish successfully before building images')
    if args.resume_image:
        assert (WORK / 'chroot_native/home/pmos/rootfs/xiaomi-platina.img').is_file()
    else:
        record('building-device-and-firmware')
        run('build', '--lax', '--arch', 'aarch64',
            'firmware-xiaomi-platina', 'device-xiaomi-platina')
        record('creating-rootfs')
        # Disposable, public build placeholder; the account is locked before export.
        run('install', '--single-partition', '--no-sparse', '--no-recommends',
            '--password', 'locked-before-export',
            '--add', 'python3,iw,iperf3,mmc-utils,avahi-tools')
    record('hardening-and-auditing-image')
    # Each pmbootstrap chroot entry restores build DNS/repositories. Configure
    # and audit in one entry, then export without entering the image again.
    scripts = '\n'.join((ROOT / 'scripts' / name).read_text()
                        for name in ('Harden-Server-Image.sh', 'Audit-Server-Image.sh'))
    subprocess.run(PMB + ['chroot', '--image', '--', 'sh', '-s'],
                   cwd=ROOT, input=scripts, text=True, check=True)
    record('exporting')
    links = ROOT / 'artifacts' / (OUTPUT.name + '-links')
    run('export', '--no-install', str(links))
    # Stop all mounts before copying/hashing the mutable filesystem image.
    run('shutdown')
    OUTPUT.mkdir()
    files = []
    for source in sorted(links.rglob('*')):
        if not source.is_file():
            continue
        target = OUTPUT / source.relative_to(links)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        with target.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        files.append({'file': str(target.relative_to(OUTPUT)),
                      'bytes': target.stat().st_size, 'sha256': digest})
    assert {'boot.img', 'xiaomi-platina.img', 'initramfs', 'vmlinuz'} <= {f['file'] for f in files}
    if provenance(config_path, config) != build_sources:
        raise RuntimeError('Build sources changed during the build; review before publishing artifacts')
    manifest = {'kernel': KERNEL_RELEASE, 'hardware_tested': False,
                'build_sources': build_sources,
                'flashed': False, 'files': files}
    (OUTPUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    record('exported-offline-audit-passed-hardware-test-pending', files=len(files))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        record('failed-needs-review', error=type(exc).__name__,
               returncode=getattr(exc, 'returncode', None))
        raise SystemExit(1)
