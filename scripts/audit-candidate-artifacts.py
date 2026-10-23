#!/usr/bin/env python3
"""Check exported boot/rootfs consistency and early module dependencies, read-only."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/candidate-7.2'


def cpio_files(data):
    files = {}
    offset = 0
    while offset + 110 <= len(data):
        header = data[offset:offset + 110]
        assert header[:6] in (b'070701', b'070702'), 'Unsupported CPIO format'
        size = int(header[54:62], 16)
        namesize = int(header[94:102], 16)
        name = data[offset + 110:offset + 110 + namesize - 1].decode()
        offset = (offset + 110 + namesize + 3) & ~3
        if name == 'TRAILER!!!':
            break
        files[name.removeprefix('./').lstrip('/')] = data[offset:offset + size]
        offset = (offset + size + 3) & ~3
    return files


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=OUT)
    args = parser.parse_args()
    OUT = args.directory.resolve()
    boot = (OUT / 'boot.img').read_bytes()
    assert boot[:8] == b'ANDROID!'
    kernel_size, _, ramdisk_size = struct.unpack_from('<III', boot, 8)
    pagesize = struct.unpack_from('<I', boot, 36)[0]
    header_version = struct.unpack_from('<I', boot, 40)[0]
    assert header_version <= 2 and pagesize == 4096
    assert len(boot) <= 0x3FFC000, 'Exceeds verified boot partition size'
    cmdline = (boot[64:576].split(b'\0')[0] + b' ' + boot[608:1632].split(b'\0')[0]).decode().strip()
    uuid = re.search(r'pmos_root_uuid=([0-9a-f-]+)', cmdline).group(1)
    metadata = subprocess.check_output(['blkid', '-p', '-o', 'export',
                                        str(OUT / 'xiaomi-platina.img')], text=True)
    assert f'UUID={uuid}\n' in metadata and 'TYPE=ext4\n' in metadata
    def root_file(path):
        return subprocess.check_output(['debugfs', '-R', 'cat ' + path,
                                        str(OUT / 'xiaomi-platina.img')],
                                       stderr=subprocess.DEVNULL, text=True)
    assert root_file('/etc/resolv.conf').splitlines() == ['nameserver 1.1.1.1', 'nameserver 1.0.0.1']
    assert root_file('/etc/apk/repositories').splitlines() == [
        'https://mirror.nura.eco/postmarketos/v26.06',
        'https://cdn.alpinelinux.org/alpine/v3.24/main',
        'https://cdn.alpinelinux.org/alpine/v3.24/community']
    start = pagesize + ((kernel_size + pagesize - 1) // pagesize) * pagesize
    ramdisk = boot[start:start + ramdisk_size]
    assert ramdisk == (OUT / 'initramfs').read_bytes(), 'Boot/export initramfs mismatch'
    files = cpio_files(gzip.decompress(ramdisk))
    release = json.loads((OUT / 'manifest.json').read_text())['kernel']
    assert re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+-sdm660', release), 'Invalid declared kernel release'
    prefix = f'usr/lib/modules/{release}/'
    # Some distributions use /lib instead of /usr/lib inside initramfs.
    if not any(name.startswith(prefix) for name in files):
        prefix = f'lib/modules/{release}/'
    depfile = prefix + 'modules.dep'
    assert depfile in files, 'Missing module dependency metadata'
    dependencies = dict(line.split(':', 1) for line in files[depfile].decode().splitlines())
    included = {name[len(prefix):] for name in files if name.startswith(prefix) and '.ko' in name}
    missing = sorted({dependency for module in included
                      for dependency in dependencies.get(module, '').split()
                      if prefix + dependency not in files})
    assert not missing, f'Initramfs modules have missing dependencies: {missing}'
    required = ('qcom_pil_info', 'ath10k_core', 'snd_soc_core',
                'qcom_vadc_common', 'snd_soc_qcom_common', 'btqca')
    normal = {Path(name).name.split('.ko')[0].replace('-', '_') for name in included}
    assert set(required) <= normal, 'Missing early-boot module'
    for firmware in ('regulatory.db', 'regulatory.db.p7s'):
        assert any(name.endswith('/firmware/' + firmware) for name in files), firmware
    assert not any(name.endswith(('.nmconnection', 'id_ed25519', 'id_rsa')) for name in files)
    report = {'passed': True, 'hardware_tested': False, 'flashed': False,
              'boot_bytes': len(boot), 'boot_limit_bytes': 0x3FFC000,
              'kernel': release, 'rootfs_uuid': uuid, 'cmdline': cmdline,
              'initramfs_modules': len(included), 'missing_module_dependencies': missing,
              'initramfs_sha256': hashlib.sha256(ramdisk).hexdigest()}
    (ROOT / 'reports' / (OUT.name + '-artifact-audit.json')).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
