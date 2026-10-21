"""Fail-closed checks for the experimental REAL iOS AppleCLCD A733 path.

Tests device-tree matching and the rotated 1024x600 DDR framebuffer geometry.
They are not a substitute for the macOS XNU compile or a hardware display test.
"""
import sys
import unittest
from pathlib import Path

A733 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(A733 / "tools"))

import mkadt_a733 as adt  # noqa: E402


class IOSDisplayTests(unittest.TestCase):
    def arm_io(self, root):
        return next(child for child in root.children if child.name == "arm-io")

    def test_legacy_safe_by_default(self):
        root = adt.build()
        self.assertEqual([n.name for n in self.arm_io(root).children], ["gic"])
        self.assertIn(b"sweet-fbcon", root.serialize())
        self.assertNotIn(b"display-subsystem", root.serialize())

    def test_opt_in_real_ios_display(self):
        root = adt.build(ios_display=True)
        self.assertEqual([n.name for n in self.arm_io(root).children], ["gic", "disp0"])
        display = self.arm_io(root).children[1]
        props = dict(display.props)
        self.assertEqual(props["compatible"], b"sweet,display\x00")
        self.assertEqual(props["device_type"], b"display-subsystem\x00")
        self.assertEqual(props["canvas-width"], adt.u32(1125))
        self.assertEqual(props["canvas-height"], adt.u32(2436))
        self.assertEqual(len(root.serialize()) % 4, 0)
        self.assertEqual(adt.FRAMEBUFFER, 0xBBF11000)

    def test_clockwise_scanout_bounds(self):
        # Proven Stage0 transform, reused by AppleCLCD's first-frame CPU path.
        width, height = 1024, 600
        for portrait_x, portrait_y in (
            (0, 0), (599, 0), (0, 1023), (599, 1023),
            (63, 0), (535, 1023), (299, 512),
        ):
            index = (height - 1 - portrait_x) * width + portrait_y
            self.assertTrue(0 <= index < width * height)
        view_w = (1024 * 1125 + 2436 // 2) // 2436
        left = (600 - view_w) // 2
        self.assertEqual(view_w, 473)
        self.assertEqual(left, 63)
        self.assertLessEqual(left + view_w, 600)

    def test_no_qualcomm_mdp_on_a733(self):
        patch = (A733 / "xnu-a733-ios-framebuffer.patch").read_text()
        self.assertIn("if (fPhys != 0xBBF11000ULL)", patch)
        self.assertIn("fVig0 = NULL;", patch)
        self.assertIn("fCtl0 = NULL;", patch)
        self.assertIn("a733_cpu_present(this, rec)", patch)
        self.assertIn("sweet_surface_copy(id)", patch)
        self.assertIn("s->memory->getLength()", patch)


if __name__ == "__main__":
    unittest.main()
