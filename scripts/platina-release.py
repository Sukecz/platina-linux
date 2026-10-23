#!/usr/bin/env python3
"""Single source of the project version and local splash/release bundle builder."""
import argparse
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'project/release.json'


def version_tuple(value):
    if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
        raise ValueError('Expected an explicit major.minor.patch version')
    return tuple(map(int, value.split('.')))


def load_release(path=RELEASE):
    data = json.loads(path.read_text())
    if data['schema'] != 1 or data['name'] != 'Platina Linux':
        raise ValueError('Unknown project release identity')
    version_tuple(data['version'])
    return data


def next_version(value, part):
    major, minor, patch = version_tuple(value)
    return {'major': f'{major + 1}.0.0', 'minor': f'{major}.{minor + 1}.0',
            'patch': f'{major}.{minor}.{patch + 1}'}[part]


def build(output, release=None):
    # Pillow is needed only on the build host. The phone uses the standard library.
    from PIL import Image, ImageDraw, ImageFont
    release = release or load_release()
    if output.exists():
        raise ValueError('Preserve existing release bundles; choose a new output path')
    logo_path = ROOT / 'project/branding/platina-linux-logo.png'
    provenance = json.loads((logo_path.parent / 'provenance.json').read_text())
    if hashlib.sha256(logo_path.read_bytes()).hexdigest() != provenance['sha256']:
        raise ValueError('Logo differs from its recorded provenance')
    width, height = 1080, 2280
    screen = Image.new('RGB', (width, height), '#000000')
    # Render the reusable generated logo as a UI asset; its source is unchanged.
    with Image.open(logo_path) as source:
        logo = source.convert('RGB')
        logo.thumbnail((960, 960), Image.Resampling.LANCZOS)
        screen.paste(logo, ((width - logo.width) // 2, 410))
    draw = ImageDraw.Draw(screen)
    font_path = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    font = ImageFont.truetype(str(font_path), 44)
    label = 'v' + release['version']
    box = draw.textbbox((0, 0), label, font=font)
    text_width, text_height = box[2] - box[0], box[3] - box[1]
    center_y = 1485
    draw.rounded_rectangle((width // 2 - text_width // 2 - 36, center_y - 44,
                            width // 2 + text_width // 2 + 36, center_y + 44),
                           radius=36, fill='#090f13', outline='#24353e', width=2)
    draw.text(((width - text_width) // 2 - box[0], center_y - text_height // 2 - box[1]),
              label, font=font, fill='#d7e3eb')
    output.mkdir(parents=True)
    screen.save(output / 'preview.png')
    raw = screen.tobytes('raw', 'BGRX')
    frame = gzip.compress(raw, compresslevel=9, mtime=0)
    (output / 'frame.bgrx.gz').write_bytes(frame)
    (output / 'version').write_text(release['name'] + ' ' + release['version'] + '\n')
    manifest = dict(release, display={
        'width': width, 'height': height, 'format': 'BGRX8888', 'seconds': 7,
        'brightness_percent': 25, 'frame': 'frame.bgrx.gz',
        'raw_bytes': len(raw), 'raw_sha256': hashlib.sha256(raw).hexdigest(),
        'compressed_sha256': hashlib.sha256(frame).hexdigest(),
    }, logo_sha256=provenance['sha256'],
        renderer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        font_sha256=hashlib.sha256(font_path.read_bytes()).hexdigest())
    (output / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Built locally:', output, '(not deployed)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('show')
    bump = sub.add_parser('bump', help='Advance the local project version; never deploy')
    bump.add_argument('part', choices=('major', 'minor', 'patch'))
    command = sub.add_parser('build', help='Build a local versioned screen; never deploy')
    command.add_argument('--output', type=Path)
    args = parser.parse_args()
    release = load_release()
    if args.command == 'show':
        print(release['version'])
    elif args.command == 'bump':
        release['version'] = next_version(release['version'], args.part)
        release['released'] = datetime.date.today().isoformat()
        RELEASE.write_text(json.dumps(release, indent=2) + '\n')
        print('Local version:', release['version'], '; rebuild and deploy with the approved update')
    else:
        build(args.output or ROOT / ('artifacts/platina-linux-' + release['version']), release)


if __name__ == '__main__':
    main()
