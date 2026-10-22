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
import sys
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
    "kern/sched_prim.h", "kdp/kdp_callout.h",
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
            "bsd/conf/files", "bsd/dev/a733_sdmmc.c", "iokit/bsddev/IOKitBSDInit.cpp",
            "osfmk/kern/debug.c"})
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
        self.assertIn('PE_parse_boot_argn("a733sdlog", &sdlog, sizeof(sdlog)) && sdlog', hook)
        panic = "\n".join(self.sections["osfmk/kern/debug.c"])
        self.assertIn("+\t\ta733_sd_log_panic_flush();", panic)
        self.assertIn(" \t\tPEHaltRestart(kPEPanicDiagnosticsDone);", panic)

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
        # Root writes only with sdrw=1: every BSD write entry point checks it.
        self.assertIn("return ((flags & FWRITE) && !sd.writable) ? EROFS : 0;", src)
        self.assertIn("if (!rd && !sd.writable) {\n\t\terror = EROFS;", src)
        self.assertIn("\tif (!sd.writable) {\n\t\treturn EROFS;\n\t}\n\treturn physio(a733_sd_strategy, NULL, dev, B_WRITE", src)
        self.assertIn('PE_parse_boot_argn("sdrw", &rw, sizeof(rw));', src)
        self.assertIn("sd.writable = (rw == 1);", src)
        # No erase, switch-function or other state-changing commands.
        self.assertIsNone(re.search(r"\b(?:smhc_cmd|smhc_xfer)\((?:38|32|33|6, 0x8)", src))
        # The one write command site is sd_write_sectors(); it refuses sector 0
        # (MBR) and anything past the card.
        code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        writes = [m.start() for m in re.finditer(r"smhc_xfer\([^;]*\btrue\)", code)]
        self.assertEqual(len(writes), 1)
        func = code.rindex("\nsd_write_sectors(", 0, writes[0])
        self.assertNotIn("\n}\n", code[func:writes[0]])
        self.assertIn("lba == 0 || lba + nblk > sd.card_sectors) {\n\t\treturn EPERM;", code[func:writes[0]])
        # Only the two bounded wrappers call it (definition + 2 calls).
        self.assertEqual(len(re.findall(r"\bsd_write_sectors\(", code)), 3)
        for wrapper, bound in (("sd_write_log", "lba < sdlog.first || lba + nblk > sdlog.first + sdlog.sectors"),
                               ("sd_write_root", "!sd.writable || lba < sd.part.start || "
                                                 "lba + nblk > sd.part.start + sd.part.count")):
            body = code[code.index("\n" + wrapper + "("):]
            body = body[:body.index("\n}\n")]
            self.assertIn(bound, body, wrapper)
            self.assertIn("return EPERM;", body)
            self.assertIn("return sd_write_sectors(lba, nblk, src);", body)
        root_body = code[code.index("\nsd_write_root("):]
        self.assertIn("sdlog.first < lba + nblk", root_body[:root_body.index("\n}\n")])  # never over the log
        callers = re.findall(r"(\w+)\(sdlog\.first[^;]*sdlog_buf\)", code)
        self.assertEqual(callers, ["sd_write_log", "sd_write_log"])
        self.assertEqual(len(re.findall(r"\bsd_write_log\(", code)), 3)     # definition + 2 calls
        self.assertEqual(len(re.findall(r"\bsd_write_root\(", code)), 3)    # definition + 2 calls in strategy
        strategy = code[code.index("\na733_sd_strategy("):]
        strategy = strategy[:strategy.index("\n}\n")]
        self.assertEqual(len(re.findall(r"\bsd_write_root\(", strategy)), 2)
        # The log file must be contiguous and must not overlap the root.
        self.assertIn("is fragmented at cluster", src)
        self.assertIn("overlaps the log file", src)
        # The CCU and pin controller are only read.
        self.assertNotIn("ccu_wr", src)
        self.assertIsNone(re.search(r"\*\(volatile uint32_t \*\)\(sd\.ccu[^;]*\) =", src))
        # No IDMAC / interrupts, CPU FIFO access through 0x200 (v5p3x).
        self.assertIn("#define SMHC_FIFO       0x200", src)
        self.assertIn("smhc_wr(SMHC_DMAC, 0);", src)
        self.assertIn("v |= GCTRL_ACCESS_BY_AHB;", src)
        self.assertIn('"A733 SD: sdroot0 ready, read-only PIO\\n"', src)
        self.assertIn('"A733 SD: sdroot0 ready, READ-WRITE PIO (sdrw=1)\\n"', src)
        # Boot partition is never the default root.
        self.assertIn("uint32_t idx = 2,", src)

    def build_logic(self, tmp: str) -> Path:
        src = Path(tmp, "a733_sdmmc.c")
        src.write_text(self.source)
        exe = Path(tmp, "test_sdmmc_logic")
        subprocess.run([CC, "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-function", "-DA733_SD_HOST_TEST",
                        "-include", str(src), str(TESTS / "test_sdmmc_logic.c"),
                        "-o", str(exe)], check=True)
        return exe

    @unittest.skipUnless(CC, "no host C compiler")
    def test_helpers_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run([str(self.build_logic(tmp))], check=True, capture_output=True, text=True)
            self.assertIn("PASS", out.stdout)

    @unittest.skipUnless(CC and shutil.which("mkfs.fat") and shutil.which("mcopy") and shutil.which("mdel") and shutil.which("mdir"),
                         "needs a C compiler, mkfs.fat (dosfstools) and mtools")
    def test_log_finder_on_real_fat32_image(self) -> None:
        """The driver's own a733sd_fat_find_log() on images made by mkfs.fat + mtools."""
        sys.path.insert(0, str(A733 / "tools"))
        import a733_sdlog
        with tempfile.TemporaryDirectory() as tmp:
            exe = self.build_logic(tmp)
            log = Path(tmp, "A733LOG.TXT")
            a733_sdlog.prepare(log, 1, False)
            small = Path(tmp, "SMALL.TXT")
            small.write_bytes(b"x" * 4096)

            def image(name: str) -> Path:
                img = Path(tmp, name)
                subprocess.run(["mkfs.fat", "-F", "32", "-s", "1", "-n", "A733LOG", "-C", str(img), "40000"],
                               check=True, capture_output=True)
                return img

            def mcopy(img: Path, src: Path, dst: str) -> None:
                subprocess.run(["mcopy", "-i", str(img), str(src), "::" + dst], check=True)

            # Contiguous file after another file: found, at the right sector.
            img = image("ok.img")
            mcopy(img, small, "README.TXT")
            mcopy(img, log, "A733LOG.TXT")
            out = subprocess.run([str(exe), str(img)], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout)
            m = re.search(r"FOUND sector (\d+) size (\d+)", out.stdout)
            self.assertIsNotNone(m, out.stdout)
            sector, size = int(m.group(1)), int(m.group(2))
            self.assertEqual(size, 1 << 20)
            with img.open("rb") as f:
                f.seek(sector * 512)
                self.assertEqual(f.read(1 << 20), log.read_bytes())

            # Free space = a 64 KiB hole left by a deleted file + a tail smaller
            # than the log, so the log must be split: it has to be refused.
            img = image("frag.img")
            hole = Path(tmp, "HOLE.BIN")
            hole.write_bytes(b"h" * (64 << 10))
            mcopy(img, hole, "A.BIN")
            mdir = subprocess.run(["mdir", "-i", str(img), "::"], check=True, capture_output=True, text=True)
            free = int(re.search(r"([\d ]+) bytes free", mdir.stdout).group(1).replace(" ", ""))
            filler = Path(tmp, "FILL.BIN")
            filler.write_bytes(b"f" * ((free - (1 << 20) + (32 << 10)) // 512 * 512))
            mcopy(img, filler, "B.BIN")
            subprocess.run(["mdel", "-i", str(img), "::A.BIN"], check=True)
            mcopy(img, log, "A733LOG.TXT")
            out = subprocess.run([str(exe), str(img)], capture_output=True, text=True)
            self.assertNotEqual(out.returncode, 0, out.stdout)
            self.assertRegex(out.stdout, r"ERROR 22 bad_cluster [1-9]")

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
