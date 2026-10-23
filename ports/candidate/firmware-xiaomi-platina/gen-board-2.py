#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 Sukecz
"""Index a user's local Qualcomm board files for ath10k-bdencoder."""
import argparse
import json
from pathlib import Path
import re


def index(directory):
    entries = []
    for path in sorted(directory.glob('bdwlan.*')):
        if not path.is_file():
            continue
        suffix = path.suffix[1:]
        aliases = ['bus=snoc']
        if suffix == 'bin':
            aliases.extend('bus=snoc,qmi-board-id=' + value for value in ('ff', '0'))
        else:
            value = suffix[1:] if re.fullmatch('b[0-9a-fA-F]{2}', suffix) else suffix
            if not re.fullmatch('[0-9a-fA-F]+', value):
                continue
            aliases = ['bus=snoc,qmi-board-id=' + value]
        entries.append({'names': aliases, 'data': path.name})
    if not entries:
        raise ValueError('No valid bdwlan files in the input directory')
    return entries


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(index(args.directory), indent=2))
