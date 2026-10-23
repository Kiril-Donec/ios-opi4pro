#!/usr/bin/env python3
"""a733/xnu-a733-keychain.patch (dxb 9999s): the built-in AppleKeyStore
(iokit/Kernel/arm/SweetKeyStore.cpp) answers aks_wrap_key / aks_unwrap_key
(selectors 10 / 11) so securityd's keychain works, and lets SpringBoard's
selectors 8 / 32 succeed. Board test #14 had 69x `securityd sel 10 ... in
2/32 out 1/40 -> 0xe00002c7`. Host checks only; the keychain itself is
proven on the board.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_cores_fb_power_patch import new_side
from test_sdmmc_patch import check_hunk_counts, files_in_patch

A733 = Path(__file__).resolve().parents[1]
PATCH = A733 / "xnu-a733-keychain.patch"
TESTS = A733 / "tests"
CXX = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")


class KeychainPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = PATCH.read_text()
        cls.sections = files_in_patch(cls.text)
        cls.src = new_side(cls.sections["iokit/Kernel/arm/SweetKeyStore.cpp"])

    def test_shape(self) -> None:
        self.assertEqual(set(self.sections), {"iokit/Kernel/arm/SweetKeyStore.cpp"})
        for section in self.sections.values():
            check_hunk_counts(section)
        self.assertNotIn("\r", self.text)
        removed = [l for l in self.sections["iokit/Kernel/arm/SweetKeyStore.cpp"]
                   if l.startswith("-") and not l.startswith("---")]
        # only additions, plus the start message naming the key wrap
        self.assertEqual(removed, ['-\tIOLog("SWEET AKS: AppleKeyStore registered (no passcode, unlocked)\\n");'])
        self.assertTrue(self.src.startswith("/*\n * Built-in AppleKeyStore for SWEET"))   # whole file in the hunk

    def test_dispatch(self) -> None:
        self.assertIn("kAKSLockDevice       = 8,", self.src)
        self.assertIn("kAKSLockNotify       = 32,", self.src)
        self.assertIn("\tcase kAKSWrapKey:\n\t\tret = sweet_aks_wrap(args);", self.src)
        self.assertIn("\tcase kAKSUnwrapKey:\n\t\tret = sweet_aks_unwrap(args);", self.src)
        # Every call is still logged.
        self.assertIn('IOLog("SWEET AKS: %s sel %u arg0 %llu in %u/%u out %u/%u -> 0x%x\\n"', self.src)

    @unittest.skipUnless(CXX, "no host C++ compiler")
    def test_wrap_host(self) -> None:
        start = self.src.index("static IOReturn\nsweet_aks_struct_out(")
        end = self.src.index("\n}\n", start) + 3
        wstart = self.src.index("/*\n * Wrapped key:")
        wend = self.src.index("static uint32_t\nsweet_aks_struct_out_size(")
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "aks_block.inc").write_text(self.src[start:end] + "\n" + self.src[wstart:wend])
            exe = Path(tmp, "test_aks_wrap")
            subprocess.run([CXX, "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                            "-I", tmp, str(TESTS / "test_aks_wrap.cpp"), "-o", str(exe)], check=True)
            out = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            self.assertIn("PASS", out.stdout)


if __name__ == "__main__":
    unittest.main()
