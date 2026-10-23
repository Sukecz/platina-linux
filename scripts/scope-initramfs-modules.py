#!/usr/bin/env python3
"""Rebuild initramfs module indexes for its actual files; never deploys.

mkinitfs 2.11 copies the complete rootfs module indexes into a partial module
archive. Early udev can then attempt to load drivers absent from that archive.
Run depmod against only the archived modules, preserving the kernel and cmdline.
Only the verified Android v0 layout used by this project is accepted.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import stat
import struct
import subprocess
import tempfile


def unpack(data):
    records = []
    offset = 0
    seen = set()
    while offset + 110 <= len(data):
        header = data[offset:offset + 110]
        if header[:6] != b'070701':
            raise ValueError('Expected newc archive')
        fields = [int(header[i:i + 8], 16) for i in range(6, 110, 8)]
        size, namesize = fields[6], fields[11]
        rawname = data[offset + 110:offset + 110 + namesize]
        if not rawname.endswith(b'\0'):
            raise ValueError('Invalid archive name')
        name = rawname[:-1].decode()
        start = (offset + 110 + namesize + 3) & ~3
        end = start + size
        if end > len(data):
            raise ValueError('Truncated archive')
        if name == 'TRAILER!!!':
            return records
        name = name.removeprefix('./')
        if name.startswith('/') or '..' in Path(name).parts or name in seen:
            raise ValueError('Unsafe or duplicate archive path')
        seen.add(name)
        records.append((name, fields, data[start:end]))
        offset = (end + 3) & ~3
    raise ValueError('Missing archive trailer')


def pack(records):
    output = bytearray()
    trailer = ('TRAILER!!!', [0] * 13, b'')
    for name, original, data in [*records, trailer]:
        fields = original.copy()
        encoded = name.encode() + b'\0'
        fields[6], fields[11], fields[12] = len(data), len(encoded), 0
        output.extend(b'070701' + ''.join(f'{v:08x}' for v in fields).encode())
        output.extend(encoded)
        output.extend(b'\0' * (-len(output) % 4))
        output.extend(data)
        output.extend(b'\0' * (-len(output) % 4))
    output.extend(b'\0' * (-len(output) % 512))
    return bytes(output)


def parts(boot):
    if boot[:8] != b'ANDROID!':
        raise ValueError('Not an Android boot image')
    f = struct.unpack_from('<10I', boot, 8)
    ksize, rsize, second, page, version = f[0], f[2], f[4], f[7], f[8]
    if page != 4096 or version != 0 or second != 0:
        raise ValueError('Unsupported boot layout')
    start = page + ((ksize + page - 1) // page) * page
    end = start + ((rsize + page - 1) // page) * page
    if end != len(boot):
        raise ValueError('Unexpected boot trailer or length')
    kernel, ramdisk = boot[page:page + ksize], boot[start:start + rsize]
    if boot[576:596] != boot_hash(kernel, ramdisk):
        raise ValueError('Boot payload hash mismatch')
    return kernel, ramdisk, start


def boot_hash(kernel, ramdisk):
    h = hashlib.sha1()
    for blob in (kernel, ramdisk, b''):
        h.update(blob)
        h.update(struct.pack('<I', len(blob)))
    return h.digest()


def replace_ramdisk(boot, ramdisk):
    kernel, _, start = parts(boot)
    result = bytearray(boot[:start])
    struct.pack_into('<I', result, 16, len(ramdisk))
    result[576:608] = boot_hash(kernel, ramdisk).ljust(32, b'\0')
    result.extend(ramdisk)
    result.extend(b'\0' * (-len(result) % 4096))
    if len(result) > 0x3FFC000:
        raise ValueError('Boot partition limit exceeded')
    parts(result)
    return bytes(result)


def scope(boot, release):
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+-sdm660', release):
        raise ValueError('Invalid kernel release')
    _, ramdisk, _ = parts(boot)
    records = unpack(gzip.decompress(ramdisk))
    prefix = next((v for v in (f'usr/lib/modules/{release}/', f'lib/modules/{release}/')
                   if any(name.startswith(v) for name, _, _ in records)), None)
    if not prefix:
        raise ValueError('Kernel modules absent')
    modules = {name[len(prefix):]: data for name, mode, data in records
               if name.startswith(prefix) and '.ko' in name and stat.S_ISREG(mode[1])}
    if not modules:
        raise ValueError('Empty module archive')
    with tempfile.TemporaryDirectory(prefix='platina-depmod-') as directory:
        root = Path(directory)
        target = root / 'lib/modules' / release
        target.mkdir(parents=True)
        for name, data in modules.items():
            f = target / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        for name, _, data in records:
            if name.startswith(prefix + 'modules.builtin'):
                (target / Path(name).name).write_bytes(data)
        (target / 'modules.order').write_text('\n'.join(sorted(modules)) + '\n')
        subprocess.run(['depmod', '-C', '/dev/null', '-b', directory, release],
                       check=True, capture_output=True)
        metadata = {f.name: f.read_bytes() for f in target.glob('modules.*')}
    dependencies = dict(line.split(':', 1) for line in metadata['modules.dep'].decode().splitlines())
    if set(dependencies) != set(modules) or any(d not in modules for ds in dependencies.values() for d in ds.split()):
        raise ValueError('Generated dependency index differs from archived files')
    filtered = [(n, m, d) for n, m, d in records if not n.startswith(prefix + 'modules.')]
    for i, (name, data) in enumerate(sorted(metadata.items())):
        fields = [0, stat.S_IFREG | 0o644, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        fields[0] = 100000 + i
        filtered.append((prefix + name, fields, data))
    new_ramdisk = gzip.compress(pack(filtered), mtime=0)
    new_boot = replace_ramdisk(boot, new_ramdisk)
    return new_boot, new_ramdisk, len(modules)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('boot', type=Path)
    parser.add_argument('--release', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Preserve existing output; choose a new directory')
    original = args.boot.read_bytes()
    boot, ramdisk, count = scope(original, args.release)
    args.output.mkdir(parents=True)
    files = []
    for name, data in [('boot.img', boot), ('initramfs', ramdisk)]:
        (args.output / name).write_bytes(data)
        files.append({'file': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    manifest = {'kernel': args.release, 'flashed': False, 'hardware_tested': False,
                'source_sha256': hashlib.sha256(original).hexdigest(),
                'initramfs_modules': count, 'module_indexes_scoped': True, 'files': files}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
