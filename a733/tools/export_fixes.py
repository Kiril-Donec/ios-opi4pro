"""Create a narrow, byte-verified handoff archive; preserve all originals."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / 'build/ios-a733-v3-fixes-20261019.zip'


def inputs():
    for name in ('Makefile', 'linker.ld', 'README.md', 'SD-IMAGE.md', 'FIXES-v3-RU.md'):
        yield ROOT / name
    for directory in ('src', 'tools', 'tests'):
        for path in sorted((ROOT / directory).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                yield path
    for name in ('stage0.elf', 'stage0.bin', 'stage0.uimg', 'stage0.map',
                 'a733-early.adt', 'portrait-preview.png',
                 'ios-a733-stage0-auto-v3-sd.img',
                 'ios-a733-stage0-auto-v3-sd.json',
                 'ios-a733-stage0-auto-v3-sd.sha256'):
        yield ROOT / 'build' / name


def main():
    manifest = []
    with zipfile.ZipFile(DESTINATION, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in inputs():
            data = path.read_bytes()
            name = path.relative_to(ROOT).as_posix()
            archive.writestr(name, data)
            manifest.append({'path': name, 'bytes': len(data),
                             'sha256': hashlib.sha256(data).hexdigest()})
        archive.writestr('MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))
    with zipfile.ZipFile(DESTINATION) as archive:
        assert archive.testzip() is None
        for item in manifest:
            data = archive.read(item['path'])
            assert len(data) == item['bytes']
            assert hashlib.sha256(data).hexdigest() == item['sha256']
    digest = hashlib.sha256(DESTINATION.read_bytes()).hexdigest()
    DESTINATION.with_suffix('.zip.sha256').write_text(f'{digest}  {DESTINATION.name}\n', encoding='ascii')
    print(json.dumps({'archive': str(DESTINATION), 'bytes': DESTINATION.stat().st_size,
                      'files': len(manifest), 'sha256': digest, 'all_entry_checks': 'PASS'}))


if __name__ == '__main__':
    main()
