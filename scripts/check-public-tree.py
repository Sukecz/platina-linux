#!/usr/bin/env python3
"""Fail public CI when private files or host-specific data enter the Git index."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT):
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    blocked = {'config', 'backups', 'artifacts', 'work', 'sources', 'tools', 'logs', 'reports', 'archive'}
    patterns = [rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----',
                rb'(?im)^\s*(?:psk|password|TELEGRAM_BOT_TOKEN|api_key)\s*=\s*["\']?[^\s"\'\n]{6,}',
                rb'(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_]{20,}',
                rb'192\.168\.\d{1,3}\.\d{1,3}', rb'/home/(?!server/|pmos/)[A-Za-z0-9_.-]+/',
                rb'C:\\Users\\']
    for name in filter(None, paths):
        path = Path(name)
        lower = name.lower()
        if (path.parts[0] in blocked or path.name.lower().startswith('agents.') or
                path.suffix.lower() in ('.txt', '.env', '.key', '.pem', '.img', '.apk', '.bin', '.elf', '.zip') or
                any(word in lower for word in ('private', 'secret', 'handoff'))):
            raise ValueError('Private or generated path in public index: ' + name)
        file = root / path
        if file.is_symlink():
            if not file.resolve().is_relative_to(root.resolve()):
                raise ValueError('External symlink: ' + name)
        data = file.read_bytes()
        if path.suffix.lower() == '.png':
            continue
        if any(re.search(pattern, data) for pattern in patterns):
            raise ValueError('Possible private data in public file (value suppressed): ' + name)
    print('OK: public index excludes private files, credentials and maintainer host data')


if __name__ == '__main__':
    check()
