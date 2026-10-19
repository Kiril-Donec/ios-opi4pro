"""Inspect the actual cross-built payload; does not emulate hardware."""
from pathlib import Path
import sys
import unittest
import subprocess
import struct

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from arm64_header import validate_arm64
from uimage_format import validate


class BootImageTests(unittest.TestCase):
    def test_real_image(self):
        data = (ROOT / 'build/stage0.uimg').read_bytes()
        validate(data, 2)
        self.assertGreater(validate_arm64(data[64:]), len(data) - 64)

    def test_old_headerless_image_rejected(self):
        with self.assertRaises(ValueError):
            validate_arm64(b'\0' * 128)

    def test_bad_branch_rejected(self):
        data = bytearray((ROOT / 'build/stage0.bin').read_bytes())
        data[:4] = b'\0' * 4
        with self.assertRaises(ValueError):
            validate_arm64(data)

    def test_bad_size_rejected(self):
        data = bytearray((ROOT / 'build/stage0.bin').read_bytes())
        data[16:24] = b'\0' * 8
        with self.assertRaises(ValueError):
            validate_arm64(data)

    def test_v4_a76_handoff_is_really_linked(self):
        data = (ROOT / 'build/stage0.bin').read_bytes()
        for marker in (b'A76 ONLINE', b'A76 PROBE: MMFR0',
                       b'PSCI CPU_ON FAILURE'):
            self.assertIn(marker, data, 'Probably a stale v3 image')
        listing = subprocess.check_output([
            'aarch64-linux-gnu-nm', '-n', str(ROOT / 'build/stage0.elf')
        ], text=True)
        symbols = {}
        for line in listing.splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[0] != 'U':
                try:
                    symbols[parts[2]] = int(parts[0], 16)
                except ValueError:
                    pass
        self.assertIn('a76_secondary_entry', symbols)
        self.assertIn('stage0_a76_entry', symbols)
        self.assertIn('__secondary_stack_top', symbols)
        image_size, = struct.unpack_from('<Q', data, 16)
        self.assertEqual(image_size, symbols['__secondary_stack_top'] - 0x41000000)


if __name__ == '__main__':
    unittest.main()
