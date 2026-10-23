#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Package user-owned stock firmware locally, verifying the pinned recipe hashes."""
import argparse
import gzip
import hashlib
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def archive_files(directory, group):
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as archive:
            for source in sorted(directory.iterdir()):
                if not source.is_file() or source.is_symlink():
                    raise ValueError('Unexpected firmware input')
                member = tarfile.TarInfo(group + '/' + source.name)
                member.mode, member.size = 0o644, source.stat().st_size
                with source.open('rb') as stream:
                    archive.addfile(member, stream)
    return output.getvalue()


def prepare(modem, gpu, output, recipe):
    if output.exists():
        raise ValueError('Preserve existing firmware; choose a new output directory')
    if not shutil.which('mcopy'):
        raise ValueError('Install mtools on the build host first')
    spec = importlib.util.spec_from_file_location('project_workflow', ROOT / 'scripts/project.py')
    workflow = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(workflow)
    checksums = workflow.checksums(recipe)
    with tempfile.TemporaryDirectory(prefix='platina-firmware-') as temp:
        staging = Path(temp)
        for group, patterns in {
            'bdwlan': ('bdwlan.*', 'wlanmdsp.mbn'),
            'modem': ('mba.mbn', 'modem.mdt', 'modem.b*'),
        }.items():
            target = staging / group
            target.mkdir()
            for pattern in patterns:
                subprocess.run(['mcopy', '-i', str(modem.resolve()), '::/image/' + pattern, str(target)], check=True)
        files = {'a512_zap.elf': gpu.read_bytes()}
        for group in ('bdwlan', 'modem'):
            files['firmware-xiaomi-platina-' + group + '.tar.gz'] = archive_files(staging / group, group)
        for name, data in files.items():
            if hashlib.sha512(data).hexdigest() != checksums[name]:
                raise ValueError('Firmware differs from the pinned reference: ' + name)
        output.mkdir(parents=True)
        for name, data in files.items():
            (output / name).write_bytes(data)
    print('Prepared checksum-verified local firmware; no phone access or redistribution')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--modem-image', type=Path, required=True, help='NON-HLOS.bin from your matching stock ROM')
    parser.add_argument('--gpu-firmware', type=Path, required=True, help='Matching a512_zap.elf from your own vendor firmware')
    parser.add_argument('--output', type=Path, default=ROOT / 'config/firmware')
    parser.add_argument('--recipe', type=Path, default=ROOT / 'ports/candidate/firmware-xiaomi-platina/APKBUILD')
    args = parser.parse_args()
    prepare(args.modem_image, args.gpu_firmware, args.output, args.recipe)
