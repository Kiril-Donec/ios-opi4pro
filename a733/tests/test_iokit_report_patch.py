#!/usr/bin/env python3
"""a733/xnu-a733-iokit-report.patch (dxb 9999t, after 9999s): a report of busy
IOKit services (iokit/Kernel/arm/A733IOKitReport.cpp), called from the power
thread 60 s and 180 s after boot. Board test #15: Settings > About waited in
SystemConfiguration's __wait_for_IOKit_to_quiesce. Static checks only: the
report itself only reads the registry.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from test_sdmmc_patch import check_hunk_counts, files_in_patch, new_file_source

A733 = Path(__file__).resolve().parents[1]
PATCH = A733 / "xnu-a733-iokit-report.patch"


class IOKitReportPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = PATCH.read_text()
        cls.sections = files_in_patch(cls.text)
        cls.report = new_file_source(cls.sections["iokit/Kernel/arm/A733IOKitReport.cpp"])

    def test_shape(self) -> None:
        self.assertEqual(set(self.sections), {"bsd/dev/a733_power.c", "iokit/Kernel/arm/A733IOKitReport.cpp",
                                              "iokit/conf/files.arm64"})
        for section in self.sections.values():
            check_hunk_counts(section)
            removed = [l for l in section if l.startswith("-") and not l.startswith("---")]
            self.assertEqual(removed, [])
        self.assertNotIn("\r", self.text)

    def test_wiring(self) -> None:
        files = "\n".join(self.sections["iokit/conf/files.arm64"])
        self.assertIn("+iokit/Kernel/arm/A733IOKitReport.cpp                             optional iokitcpp", files)
        power = "\n".join(self.sections["bsd/dev/a733_power.c"])
        self.assertIn("+extern void a733_iokit_busy_report(unsigned int seconds);", power)
        self.assertIn("+\t\tif (tick == 1200 || tick == 3600) {", power)
        self.assertIn("+\t\t\ta733_iokit_busy_report(tick / 20);", power)

    def test_report_reads_only(self) -> None:
        src = self.report
        self.assertIn("#if defined(SWEET)", src)
        self.assertIn('extern "C" void a733_iokit_busy_report(unsigned int seconds);', src)
        code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        for forbidden in ("terminate(", "adjustBusy(", "registerService(", "setProperty(", "removeProperty("):
            self.assertNotIn(forbidden, code)
        self.assertIn("it->release();", code)
        self.assertIn("kids->release();", code)
        self.assertIn("if (shown < 48) {", code)


if __name__ == "__main__":
    unittest.main()
