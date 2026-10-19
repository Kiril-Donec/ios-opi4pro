"""Static regression checks for observable boot ordering and load guards."""
from pathlib import Path
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] / 'tools/sd-boot-auto.cmd').read_text()


class BootScriptTests(unittest.TestCase):
    def test_screen_setup_precedes_handoff(self):
        self.assertLess(SCRIPT.index('\nscreen_char\n'), SCRIPT.index('setenv stdout'))
        self.assertLess(SCRIPT.index('setenv stdout'), SCRIPT.index('bootm 0x42000000'))

    def test_loads_remain_conditional(self):
        self.assertIn('if ext4load mmc 0:1 0x42000000 /ios-a733/stage0.uimg; then', SCRIPT)
        self.assertIn('if ext4load mmc 0:1 0x43000000 /dtb/allwinner/', SCRIPT)
        self.assertEqual(SCRIPT.count('bootm 0x42000000 - 0x43000000'), 1)

    def test_markers_in_order(self):
        positions = [SCRIPT.index(f'[{step}/4]') for step in range(1, 5)]
        self.assertEqual(positions, sorted(positions))
        self.assertGreaterEqual(SCRIPT.count('sleep 2'), 3)


if __name__ == '__main__':
    unittest.main()
