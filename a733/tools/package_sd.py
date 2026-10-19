"""Build a NEW SD image from the known v59 vendor bootloader container.

Only edits a private filesystem copy. Never opens any physical block device.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from uimage_format import script_image, validate
from arm64_header import validate_arm64

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def debugfs(partition, command):
    result = subprocess.run(['debugfs', '-w', '-R', command, str(partition)],
                            text=True, capture_output=True, check=True)
    if any(marker in result.stderr.lower() for marker in
           ('file not found', 'no space', 'permission denied', 'not open', 'already exists')):
        raise RuntimeError(result.stderr)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--autostart', action='store_true',
                        help='Automatically execute the experimental screen diagnostic')
    args = parser.parse_args()
    if not args.base.is_file() or args.output.exists():
        raise ValueError('Base must be a regular file; output must not exist')
    if not args.output.parent.is_dir() or args.output.suffix != '.img':
        raise ValueError('Output requires an existing directory and .img suffix')
    original = args.base.read_bytes()
    if len(original) != 64 * 1024 * 1024 or original[510:512] != b'\x55\xaa':
        raise ValueError('Unexpected v59 image layout')
    entry = original[446:462]
    start, sectors = struct.unpack_from('<II', entry, 8)
    if entry[4] != 0x83 or (start, sectors) != (65536, 65536):
        raise ValueError('Unexpected partition layout')
    offset = start * 512
    stage0 = ROOT / 'build/stage0.uimg'
    validate(stage0.read_bytes(), 2)
    runtime_size = validate_arm64(stage0.read_bytes()[64:])
    elf = (ROOT / 'build/stage0.elf').read_bytes()
    if elf[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', elf, 18)[0] != 183:
        raise ValueError('Stage0 ELF is not AArch64')
    template = 'sd-boot-auto.cmd' if args.autostart else 'sd-boot.cmd'
    boot_cmd = (ROOT / 'tools' / template).read_bytes().replace(b'\r\n', b'\n')
    image_name = 'ios-a733 AUTO stage0' if args.autostart else 'ios-a733 SAFE MANUAL stage0'
    boot_scr = script_image(boot_cmd, image_name)
    with tempfile.TemporaryDirectory(prefix='ios-a733-sd-') as temp:
        work = Path(temp)
        partition = work / 'root.ext4'
        partition.write_bytes(original[offset:])
        (work / 'boot.cmd').write_bytes(boot_cmd)
        (work / 'boot.scr').write_bytes(boot_scr)
        debugfs(partition, 'mkdir /ios-a733')
        for name in ('boot.cmd', 'boot.scr'):
            debugfs(partition, f'rm /{name}')
            debugfs(partition, f'write {work / name} /{name}')
        # Remove the inherited UEFI payload only from the NEW image.
        debugfs(partition, 'rm /uefi_stage0.uimg')
        inputs = {stage0: '/ios-a733/stage0.uimg',
                  ROOT / 'build/a733-early.adt': '/ios-a733/a733-early.adt',
                  ROOT / 'README.md': '/ios-a733/README.md',
                  ROOT / 'SD-IMAGE.md': '/ios-a733/SD-IMAGE.md'}
        for index, (source, target) in enumerate(inputs.items()):
            # Avoid whitespace/escaping in debugfs host-side file paths.
            local = work / f'input-{index}'
            local.write_bytes(source.read_bytes())
            debugfs(partition, f'write {local} {target}')
        verify = dict(inputs)
        verify[work / 'boot.scr'] = '/boot.scr'
        verify[work / 'boot.cmd'] = '/boot.cmd'
        for index, (source, target) in enumerate(verify.items()):
            exported = work / f'verified-{index}'
            debugfs(partition, f'dump {target} {exported}')
            if exported.read_bytes() != source.read_bytes():
                raise ValueError(f'Filesystem read-back mismatch: {target}')
        check = subprocess.run(['e2fsck', '-fn', str(partition)], capture_output=True, text=True)
        if check.returncode != 0:
            raise RuntimeError(check.stdout + check.stderr)
        result = original[:offset] + partition.read_bytes()
        if len(result) != len(original) or result[:offset] != original[:offset]:
            raise ValueError('Bootloader/container layout changed')
        with args.output.open('xb') as output:
            output.write(result)
    info = {'image': args.output.name, 'bytes': len(result), 'sha256': digest(result),
            'base_sha256': digest(original), 'stage0_sha256': digest(stage0.read_bytes()),
            'bootloader_first_32MiB_unchanged': True, 'ext4_check': 'PASS',
            'payload_readback': 'PASS', 'automatic_stage0_execution': args.autostart,
            'arm64_inner_header': 'PASS', 'stage0_runtime_bytes': runtime_size,
            'hardware_tested': False, 'contains_ios_or_xnu': False}
    args.output.with_suffix('.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    args.output.with_suffix('.sha256').write_text(f'{info["sha256"]}  {args.output.name}\n', encoding='ascii')
    print(json.dumps(info, indent=2))


if __name__ == '__main__':
    main()
