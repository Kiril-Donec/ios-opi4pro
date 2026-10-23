#!/usr/bin/env python3
"""a733/xnu-a733-sched-bigpref.patch (dxb 9999u): choose_processor() prefers
an idle Cortex-A76 for interactive threads and an idle A55 for background
threads on the A733 (one SMP cluster, no Edge scheduler / CLPC). Host test of
the selection helpers plus static checks of the hooks; behaviour on the board
is only proven by a board test.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_sdmmc_patch import CC, check_hunk_counts, files_in_patch

A733 = Path(__file__).resolve().parents[1]
PATCH = A733 / "xnu-a733-sched-bigpref.patch"
TESTS = A733 / "tests"


class SchedBigPrefPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = PATCH.read_text()
        cls.sections = files_in_patch(cls.text)
        cls.added = "\n".join(l[1:] for l in cls.sections["osfmk/kern/sched_prim.c"]
                              if l.startswith("+") and not l.startswith("+++"))

    def test_shape(self) -> None:
        self.assertEqual(set(self.sections), {"osfmk/kern/sched_prim.c"})
        for section in self.sections.values():
            check_hunk_counts(section)
            self.assertEqual([l for l in section if l.startswith("-") and not l.startswith("---")], [])
        self.assertNotIn("\r", self.text)
        # Everything new is SWEET-only.
        blocks = re.findall(r"#if defined\(ARM64_BOARD_CONFIG_SWEET\)(.*?)#endif", self.added, re.S)
        self.assertEqual(len(blocks), 3)
        outside = re.sub(r"#if defined\(ARM64_BOARD_CONFIG_SWEET\).*?#endif[^\n]*", "", self.added, flags=re.S)
        self.assertEqual(outside.strip(), "")

    def test_hooks(self) -> None:
        self.assertIn("if (pref != 0 && !bit_test(pref, processor->cpu_id)) {", self.added)
        self.assertIn("return processor_array[lsb_first(pref)];", self.added)
        self.assertIn("uint64_t sweet_pref = sweet_preferred(thread, idle_primary_map);", self.added)
        self.assertIn('PE_parse_boot_argn("a733bigpref", &on, sizeof(on));', self.added)
        # Realtime threads are never redirected.
        self.assertIn("if (thread->sched_pri < BASEPRI_RTQUEUES) {", self.added)

    @unittest.skipUnless(CC, "no host C compiler")
    def test_selection_host(self) -> None:
        start = self.added.index("static uint64_t sweet_big_mask;")
        end = self.added.index("#endif /* ARM64_BOARD_CONFIG_SWEET */")
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "sched_block.inc").write_text(self.added[start:end])
            exe = Path(tmp, "test_sched_bigpref")
            subprocess.run([CC, "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror", "-I", tmp,
                            str(TESTS / "test_sched_bigpref.c"), "-o", str(exe)], check=True)
            out = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
