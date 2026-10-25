#!/usr/bin/env python3
"""a733/xnu-a733-no-iokitd.patch (dxb 9999v): OSKext::iokitDaemonAvailable()
is false on the SWEET board unless a733iokitd=1. Board test #16 (9999t
report): the only busy service was the root D22AP <IOPlatformExpertDevice>,
held by StartIOKitMatching until kernelmanagerd checks in; iOS has no
kernelmanagerd, so IOKit never quiesced and Settings > About hung.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from test_sdmmc_patch import check_hunk_counts, files_in_patch

A733 = Path(__file__).resolve().parents[1]
PATCH = A733 / "xnu-a733-no-iokitd.patch"


class NoIOKitDaemonPatch(unittest.TestCase):
    def test_patch(self) -> None:
        text = PATCH.read_text()
        sections = files_in_patch(text)
        self.assertEqual(set(sections), {"libkern/c++/OSKext.cpp"})
        section = sections["libkern/c++/OSKext.cpp"]
        check_hunk_counts(section)
        self.assertNotIn("\r", text)
        self.assertEqual([l for l in section if l.startswith("-") and not l.startswith("---")], [])
        added = "\n".join(l[1:] for l in section if l.startswith("+") and not l.startswith("+++"))
        self.assertTrue(added.lstrip().startswith("#if defined(ARM64_BOARD_CONFIG_SWEET)"))
        self.assertTrue(added.rstrip().endswith("#endif"))
        self.assertIn('PE_parse_boot_argn("a733iokitd", &wait_daemon, sizeof(wait_daemon));', added)
        self.assertIn("if (!wait_daemon) {\n\t\treturn false;\n\t}", added)
        # The hunk sits in iokitDaemonAvailable(), after the -restore check.
        self.assertIn("@@ -1485,6 +1485,21 @@ OSKext::iokitDaemonAvailable(void)", text)


if __name__ == "__main__":
    unittest.main()
