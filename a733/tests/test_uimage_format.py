"""Host checks for packaged legacy images; never runs the ARM payload."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from make_uimage import pack
from uimage_format import script_image, validate


class ImageFormatTests(unittest.TestCase):
    def test_kernel(self):
        validate(pack(b'payload', 'stage0', 0x41000000), 2)

    def test_script(self):
        data = script_image(b'echo safe\r\n')
        validate(data, 6)
        self.assertEqual(data[72:], b'echo safe\n')

    def test_auto_script_label(self):
        fields = validate(script_image(b'echo auto\n', 'ios-a733 AUTO stage0'), 6)
        self.assertEqual(fields[-1].rstrip(b'\0'), b'ios-a733 AUTO stage0')

    def test_long_script_label_refused(self):
        with self.assertRaises(ValueError):
            script_image(b'echo safe\n', 'x' * 33)

    def test_header_corruption(self):
        data = bytearray(pack(b'payload', 'stage0', 0x41000000))
        data[20] ^= 1
        with self.assertRaises(ValueError):
            validate(data, 2)

    def test_payload_corruption(self):
        data = bytearray(pack(b'payload', 'stage0', 0x41000000))
        data[-1] ^= 1
        with self.assertRaises(ValueError):
            validate(data, 2)

    def test_truncation(self):
        with self.assertRaises(ValueError):
            validate(b'bad', 2)

    def test_wrong_entry(self):
        with self.assertRaises(ValueError):
            validate(pack(b'payload', 'stage0', 0x42000000), 2)

    def test_wrong_type(self):
        with self.assertRaises(ValueError):
            validate(script_image(b'echo safe\n'), 2)


if __name__ == '__main__':
    unittest.main()
