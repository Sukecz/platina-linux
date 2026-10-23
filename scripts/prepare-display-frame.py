#!/usr/bin/env python3
"""Prepare an image for Platina locally; Pillow is required only on the build host."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]


def build(source, output):
    if output.exists():
        raise ValueError('Choose a new frame directory; existing bundles are immutable')
    with Image.open(source) as image:
        frame = ImageOps.pad(ImageOps.exif_transpose(image).convert('RGB'), (1080, 2280),
                             color='black', method=Image.Resampling.LANCZOS)
    raw = frame.tobytes('raw', 'BGRX')
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    manifest = json.loads((ROOT / 'project/release.json').read_text())
    manifest.update(purpose='custom-display-frame', display={
        'width': 1080, 'height': 2280, 'format': 'BGRX8888',
        'frame': 'frame.bgrx.gz', 'raw_bytes': len(raw),
        'raw_sha256': hashlib.sha256(raw).hexdigest(),
        'compressed_sha256': hashlib.sha256(compressed).hexdigest(),
    })
    output.mkdir(parents=True)
    frame.save(output / 'preview.png')
    (output / 'frame.bgrx.gz').write_bytes(compressed)
    (output / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print('Prepared locally:', build(args.image, args.output), '; no phone connection')


if __name__ == '__main__':
    main()
