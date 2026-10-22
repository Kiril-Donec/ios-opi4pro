#!/usr/bin/env python3
"""A733 framebuffer console overlay (a733/xnu-a733-console-graphics.patch).

Board test #5 showed the first real iOS frame (Apple logo) on HDMI, but the
console painted over it and wrapped to the top instead of scrolling. The
patch makes the console scroll and, after the first iOS frame, composites
the last log lines in a band over the frame from saved frame pixels.
These tests rebuild the patched console code on the host with stubs.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

A733 = Path(__file__).resolve().parents[1]
PATCH = A733 / "xnu-a733-console-graphics.patch"
TESTS = A733 / "tests"
CC = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")

STUBS = r"""
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
static int panic_flag;
static unsigned panic_active(void) { return panic_flag; }
static bool PE_parse_boot_argn(const char *n, void *p, int s) { (void)n; (void)p; (void)s; return false; }
"""


def new_side(patch: str, path: str) -> str:
    sec = patch.split(f"diff --git a/{path} b/{path}")[1].split("\ndiff --git")[0]
    hunks = re.split(r"\n(?=@@ )", sec)[1:]
    assert len(hunks) == 1, f"{path}: expected one hunk (-U200), got {len(hunks)}"
    out = []
    for line in hunks[0].splitlines()[1:]:
        if line.startswith("-") or line.startswith("\\"):
            continue
        out.append(line[1:] if line else "")
    return "\n".join(out) + "\n"


class ConsoleGraphics(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.patch = PATCH.read_text()
        cls.serial = new_side(cls.patch, "pexpert/arm/pe_serial.c")
        cls.fb = new_side(cls.patch, "iokit/Kernel/arm/SweetFramebuffer.cpp")

    def test_patch_scope(self) -> None:
        files = re.findall(r"^diff --git a/(\S+)", self.patch, re.M)
        self.assertEqual(files, ["iokit/Kernel/arm/SweetFramebuffer.cpp", "pexpert/arm/pe_serial.c"])
        self.assertNotIn("\r", self.patch)

    def test_framebuffer_hooks(self) -> None:
        fb = self.fb
        self.assertIn("uint32_t *band = a733_fbcon_band(&band_y0);", fb)
        self.assertIn("band[(y - band_y0) * portrait_w + x] = color;", fb)
        # The switch happens after the frame is fully written, before the overlay.
        self.assertLess(fb.index("a733_fbcon_graphics_frame();"), fb.index("a733_fbcon_overlay();\n\t}"))
        self.assertLess(fb.index('__asm__ volatile("dsb sy" ::: "memory");\n\t/* From now on'),
                        fb.index("a733_fbcon_graphics_frame();"))
        serial = self.serial
        self.assertNotIn("Lines wrap back to the top", serial)
        self.assertIn('PE_parse_boot_argn("a733fb_console", &keep_console', serial)
        self.assertIn("if (a733_fbcon_graphics && panic_active()) {", serial)

    @unittest.skipUnless(CC, "no host C compiler")
    def test_console_behaviour(self) -> None:
        start = self.serial.index("extern unsigned char iso_font[256 * 16];")
        end = self.serial.index("static unsigned int\nfbcon_receive_ready(void)")
        block = self.serial[start:end].replace("extern unsigned char iso_font[256 * 16];",
                                               "static unsigned char iso_font[256 * 16];")
        block = re.sub(r"static volatile uint32_t \*fbcon_base;", "static uint32_t *fbcon_base;", block)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp, "console.c")
            src.write_text(STUBS + "#define FBCON_SCALE 1\n#define FBCON_FG 0xffffffffu\n"
                           "#define FBCON_BG 0xff000000u\n" + block)
            exe = Path(tmp, "t")
            subprocess.run([CC, "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                            "-include", str(src), str(TESTS / "test_fbcon_logic.c"), "-o", str(exe)], check=True)
            out = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            self.assertIn("PASS", out.stdout)


if __name__ == "__main__":
    unittest.main()
