#!/usr/bin/env python3
"""Static and host checks for the A733 microSD (SMHC0) XNU overlay.

The kernel driver lives only inside a733/xnu-a733-sdmmc.patch (it is applied
to the patched XNU tree in the macOS workflow). These tests extract the new
bsd/dev/a733_sdmmc.c from the patch, then:
- build and run the pure helper tests (clock, CSD/CID, MBR/GPT, HFS+);
- syntax-check the kernel part against XNU-signature stubs with -Werror;
- check the patch wiring (build file list, rd=sdroot0 root hook).
None of this proves the driver works on the Orange Pi.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

A733 = Path(__file__).resolve().parents[1]
PATCH = A733 / "xnu-a733-sdmmc.patch"
TESTS = A733 / "tests"
CC = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
KERNEL_HEADERS = (
    "sys/param.h", "sys/systm.h", "sys/buf.h", "sys/conf.h", "sys/disk.h",
    "sys/errno.h", "sys/proc.h", "sys/uio.h", "miscfs/devfs/devfs.h",
    "kern/locks.h", "kern/clock.h", "machine/machine_routines.h",
    "pexpert/pexpert.h", "pexpert/device_tree.h", "libkern/libkern.h",
)


def files_in_patch(text: str) -> dict[str, list[str]]:
    """Map each 'b/' path to the lines of its diff section."""
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"diff --git a/(\S+) b/(\S+)", line)
        if m:
            current = m.group(2)
            sections[current] = []
        elif current:
            sections[current].append(line)
    return sections


def new_file_source(section: list[str]) -> str:
    """Body of a new-file diff section (every line starts with '+')."""
    assert any(l.startswith("new file mode") for l in section), "not a new file"
    body, in_hunk = [], False
    for line in section:
        if line.startswith("@@"):
            in_hunk = True
            continue
        if in_hunk:
            assert line.startswith("+"), f"unexpected line in new file: {line!r}"
            body.append(line[1:])
    return "\n".join(body) + "\n"


def check_hunk_counts(section: list[str]) -> None:
    """Each hunk's header line counts must match its body."""
    i = 0
    while i < len(section):
        m = re.match(r"@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@", section[i])
        if not m:
            i += 1
            continue
        old = int(m.group(1) or 1)
        new = int(m.group(2) or 1)
        i += 1
        o = n = 0
        while i < len(section) and not section[i].startswith("@@") and (o < old or n < new):
            line = section[i]
            if line.startswith("-"):
                o += 1
            elif line.startswith("+"):
                n += 1
            elif line.startswith(" ") or line == "":
                o += 1
                n += 1
            elif line.startswith("\\"):
                pass
            else:
                break
            i += 1
        assert (o, n) == (old, new), f"hunk counts {old},{new} but body {o},{n}"


class SdmmcPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = PATCH.read_text()
        cls.sections = files_in_patch(cls.text)
        cls.source = new_file_source(cls.sections["bsd/dev/a733_sdmmc.c"])

    def test_patch_touches_only_expected_files(self) -> None:
        self.assertEqual(set(self.sections), {
            "bsd/conf/files", "bsd/dev/a733_sdmmc.c", "iokit/bsddev/IOKitBSDInit.cpp"})
        for section in self.sections.values():
            check_hunk_counts(section)
        self.assertNotIn("\r", self.text)

    def test_build_and_root_hook(self) -> None:
        files = "\n".join(self.sections["bsd/conf/files"])
        self.assertIn("+bsd/dev/a733_sdmmc.c\t\t\tstandard", files)
        self.assertIn(" bsd/dev/sweet_ufs.c\t\t\tstandard", files)
        hook = "\n".join(self.sections["iokit/bsddev/IOKitBSDInit.cpp"])
        self.assertIn('+\tif (strcmp(rdBootVar, "sdroot0") == 0) {', hook)
        self.assertIn("+\t\tint sd_error = a733_sd_rootdev(root);", hook)
        self.assertIn("+\t\tgoto iofrootx;", hook)
        self.assertIn('+\t\tIOLog("A733 ROOT: rd=sdroot0, starting the SMHC0 microSD PIO driver\\n");', hook)

    def test_no_string_literal_split_across_lines(self) -> None:
        # CI run 39673536036 failed on IOLog("...\n") whose \n had become a real newline.
        for path, section in self.sections.items():
            for line in section:
                if line.startswith("+") and not line.startswith("+++"):
                    code = line[1:].split("//")[0]
                    quotes = len(re.findall(r'(?<!\\)"', code.replace("'\"'", "")))
                    self.assertEqual(quotes % 2, 0, f"{path}: unbalanced quotes in {line!r}")

    def test_driver_safety_properties(self) -> None:
        src = self.source
        self.assertTrue(src.startswith("/*"))
        self.assertIn("#if defined(ARM64_BOARD_CONFIG_SWEET) || defined(A733_SD_HOST_TEST)", src)
        # Read-only: no write commands, every write entry point refuses.
        for write_cmd in (r"smhc_cmd\(24\b", r"smhc_cmd\(25\b", r"smhc_cmd\(38\b", "CMD_WRITE"):
            self.assertIsNone(re.search(write_cmd, src), write_cmd)
        self.assertIn("return (flags & FWRITE) ? EROFS : 0;", src)
        self.assertIn("error = EROFS;", src)
        # The CCU and pin controller are only read.
        self.assertNotIn("ccu_wr", src)
        self.assertIsNone(re.search(r"\*\(volatile uint32_t \*\)\(sd\.ccu[^;]*\) =", src))
        # No IDMAC / interrupts, CPU FIFO access through 0x200 (v5p3x).
        self.assertIn("#define SMHC_FIFO       0x200", src)
        self.assertIn("smhc_wr(SMHC_DMAC, 0);", src)
        self.assertIn("v |= GCTRL_ACCESS_BY_AHB;", src)
        self.assertIn('"A733 SD: sdroot0 ready, read-only PIO\\n"', src)
        # Boot partition is never the default root.
        self.assertIn("uint32_t idx = 2,", src)

    @unittest.skipUnless(CC, "no host C compiler")
    def test_helpers_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp, "a733_sdmmc.c")
            src.write_text(self.source)
            exe = Path(tmp, "test_sdmmc_logic")
            subprocess.run([CC, "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
                            "-Wno-unused-function", "-DA733_SD_HOST_TEST",
                            "-include", str(src), str(TESTS / "test_sdmmc_logic.c"),
                            "-o", str(exe)], check=True)
            out = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
            self.assertIn("PASS", out.stdout)

    @unittest.skipUnless(CC, "no host C compiler")
    def test_kernel_part_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inc = Path(tmp, "inc")
            for header in KERNEL_HEADERS:
                path = inc / header
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("/* stub: see sdmmc_kernel_stubs.h */\n")
            src = Path(tmp, "a733_sdmmc.c")
            src.write_text(self.source)
            flags = ["-std=gnu11", "-fsyntax-only", "-Wall", "-Wextra", "-Werror",
                     "-Wno-unused-parameter", "-DARM64_BOARD_CONFIG_SWEET", "-I" + str(inc),
                     # XNU's own eno_* initialisers cast through empty_fcn_t
                     "-Wno-cast-function-type",
                     "-include", str(TESTS / "sdmmc_kernel_stubs.h")]
            if "clang" in Path(CC).name:
                flags += ["-Wshorten-64-to-32", "-Wno-cast-function-type-mismatch",
                          "-Wno-unknown-warning-option"]
            subprocess.run([CC, *flags, str(src)], check=True)


if __name__ == "__main__":
    unittest.main()
