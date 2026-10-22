#!/usr/bin/env python3
"""a733/xnu-a733-smp-a76.patch: SweetCPU accepts the second Cortex-A76 (cpus=2)."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

PATCH = Path(__file__).resolve().parents[1] / "xnu-a733-smp-a76.patch"


class SmpA76Patch(unittest.TestCase):
    def test_only_the_a76_pair(self) -> None:
        text = PATCH.read_text()
        self.assertEqual(re.findall(r"^diff --git a/(\S+)", text, re.M), ["iokit/Kernel/arm/SweetCPU.cpp"])
        added = [l[1:] for l in text.splitlines() if l.startswith("+") and not l.startswith("+++")]
        removed = [l[1:] for l in text.splitlines() if l.startswith("-") and not l.startswith("---")]
        self.assertIn("\tif ((cpu->phys_id != 0x600 && cpu->phys_id != 0x700) ||", added)
        self.assertIn("\tif (cpu->phys_id != 0x600 ||", removed)
        self.assertEqual(len(added), 2)                 # comment + condition only
        # The boot CPU requirement (MPIDR 0x600, logical 0) is untouched.
        self.assertNotIn("boot_cpu", "".join(added + removed))
        self.assertNotIn("\r", text)


if __name__ == "__main__":
    unittest.main()
