#!/usr/bin/env python3
"""Static and host checks for the A733 USB touch screen XNU overlay.

a733/xnu-a733-usbtouch.patch (applied after the sdmmc patch) adds
bsd/dev/a733_usbtouch.c: a polled USB1 OHCI host driver for the HDMI
display's touch controller, feeding SweetHIDTouch. These tests:
- build and run the pure part (HID descriptor, reports, portrait mapping)
  on the display's real descriptor and recorded reports;
- syntax-check the kernel part against XNU-signature stubs with -Werror;
- check the wiring (build list, IOFindBSDRoot hook) and safety limits.
None of this proves the USB host works on the Orange Pi.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_sdmmc_patch import CC, KERNEL_HEADERS, check_hunk_counts, files_in_patch, new_file_source

A733 = Path(__file__).resolve().parents[1]
PATCH = A733 / "xnu-a733-usbtouch.patch"
TESTS = A733 / "tests"


class UsbTouchPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = PATCH.read_text()
        cls.sections = files_in_patch(cls.text)
        cls.source = new_file_source(cls.sections["bsd/dev/a733_usbtouch.c"])
        cls.code = re.sub(r"/\*.*?\*/", "", cls.source, flags=re.S)

    def test_patch_touches_only_expected_files(self) -> None:
        self.assertEqual(set(self.sections), {
            "bsd/conf/files", "bsd/dev/a733_usbtouch.c", "iokit/bsddev/IOKitBSDInit.cpp"})
        for section in self.sections.values():
            check_hunk_counts(section)
        self.assertNotIn("\r", self.text)

    def test_build_and_start_hook(self) -> None:
        files = "\n".join(self.sections["bsd/conf/files"])
        self.assertIn("+bsd/dev/a733_usbtouch.c\t\t\tstandard", files)
        self.assertIn(" bsd/dev/a733_sdmmc.c\t\t\tstandard", files)      # needs the sdmmc patch first
        hook = "\n".join(self.sections["iokit/bsddev/IOKitBSDInit.cpp"])
        self.assertIn("+\t\textern void a733_usbtouch_start(void);", hook)
        self.assertIn("+\t\ta733_usbtouch_start();", hook)
        added = [l for l in self.sections["iokit/bsddev/IOKitBSDInit.cpp"] if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
        self.assertTrue(all(l.startswith("+") for l in added))           # nothing removed
        self.assertIn('"/a733-usb"', self.source)
        self.assertIn('PE_parse_boot_argn("a733usb", &on, sizeof(on));', self.source)

    def test_no_string_literal_split_across_lines(self) -> None:
        for path, section in self.sections.items():
            for line in section:
                if line.startswith("+") and not line.startswith("+++"):
                    code = line[1:].split("//")[0]
                    quotes = len(re.findall(r'(?<!\\)"', code.replace("'\"'", "")))
                    self.assertEqual(quotes % 2, 0, f"{path}: unbalanced quotes in {line!r}")

    def test_safety_properties(self) -> None:
        src, code = self.source, self.code
        self.assertIn("#if defined(ARM64_BOARD_CONFIG_SWEET) || defined(A733_USBTOUCH_HOST_TEST)", src)
        # DMA only inside the ADT window, below 4 GiB, page aligned; mapped once.
        self.assertIn("dma[0] + DMA_SIZE > 0x100000000ull", src)
        self.assertIn("(dma[0] & 0xfff)", src)
        self.assertEqual(len(re.findall(r"\bml_io_map\(", code)), 4)      # extern + hci, ccu, dma
        # The DMA window is only touched with 32-bit accesses through wr32/rd32.
        self.assertIsNone(re.search(r"\(volatile uint(8|16|64)_t \*\)", code))
        self.assertIsNone(re.search(r"mem(set|cpy)\(\s*\(void \*\)\s*ut\.dma", code))
        # Only the USB1 clock/reset bits of the CCU are changed (vendor open_clock).
        ccu_writes = re.findall(r"wr32\(ut\.ccu, (\w+),", code)
        self.assertEqual(sorted(set(ccu_writes)), sorted(
            {"CCU_MSI_LITE2", "CCU_AHB_MASTER", "CCU_USB_REF", "CCU_USB1_BGR", "CCU_USB1"}))
        for reg, off in (("CCU_MSI_LITE2", "0x05a4"), ("CCU_AHB_MASTER", "0x05c0"),
                         ("CCU_USB1", "0x1308"), ("CCU_USB1_BGR", "0x130c"), ("CCU_USB_REF", "0x1340")):
            self.assertRegex(src, rf"#define {reg}\s+{off}\b")
        # Every CCU write is a read-modify-write that only sets bits (never clears gates of others),
        # except the usb_ref mux field.
        for m in re.finditer(r"wr32\(ut\.ccu, (\w+), ([^;]*)\);", code):
            reg, expr = m.groups()
            self.assertIn(f"rd32(ut.ccu, {reg})", expr, reg)
            if reg != "CCU_USB_REF":
                self.assertNotIn("&", expr, reg)
        # SET_ADDRESS in one place: 1 on the root port, 2..16 behind one hub level.
        self.assertEqual(len(re.findall(r"ut_control\([^;]*, 0x00, 5, ", code)), 1)
        self.assertEqual(re.findall(r"ut_address_device\(&d, ([^,]+),", code), ["1 + p", "1"])
        self.assertIn("unsigned ports = ut_buf[2] > 15 ? 15 : ut_buf[2];", src)
        self.assertIn("has another hub", src)
        # Every control transfer is bounded by the 1 KiB buffer and a timeout.
        self.assertIn("if (length > sizeof(ut_buf)) {\n\t\treturn -EINVAL;", src)
        self.assertIn("uint64_t deadline = ut_deadline_ms(500);", src)
        # Lost device: all fingers are released before re-enumeration.
        poll = code[code.index("\nut_poll(void)"):]
        poll = poll[:poll.index("\n}\n")]
        self.assertTrue(poll.rstrip().endswith("ut_release_all();"))
        # Polling thread only; no interrupt handler registration.
        self.assertNotIn("ml_install_interrupt_handler", code)
        self.assertNotIn("IOInterrupt", code)

    def build_logic(self, tmp: str) -> Path:
        src = Path(tmp, "a733_usbtouch.c")
        src.write_text(self.source)
        exe = Path(tmp, "test_usbtouch_logic")
        subprocess.run([CC, "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-function", "-DA733_USBTOUCH_HOST_TEST",
                        "-include", str(src), str(TESTS / "test_usbtouch_logic.c"),
                        "-o", str(exe)], check=True)
        return exe

    @unittest.skipUnless(CC, "no host C compiler")
    def test_logic_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run([str(self.build_logic(tmp))], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            self.assertIn("PASS", out.stdout)

    @unittest.skipUnless(CC, "no host C compiler")
    def test_kernel_part_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inc = Path(tmp, "inc")
            for header in KERNEL_HEADERS:
                path = inc / header
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("/* stub: see sdmmc_kernel_stubs.h */\n")
            src = Path(tmp, "a733_usbtouch.c")
            src.write_text(self.source)
            flags = ["-std=gnu11", "-fsyntax-only", "-Wall", "-Wextra", "-Werror",
                     "-Wno-unused-parameter", "-DARM64_BOARD_CONFIG_SWEET", "-I" + str(inc),
                     "-Wno-cast-function-type",
                     "-include", str(TESTS / "sdmmc_kernel_stubs.h"),
                     "-include", str(TESTS / "usbtouch_kernel_stubs.h")]
            if "clang" in Path(CC).name:
                flags += ["-Wshorten-64-to-32", "-Wno-cast-function-type-mismatch",
                          "-Wno-unknown-warning-option"]
            subprocess.run([CC, *flags, str(src)], check=True)


if __name__ == "__main__":
    unittest.main()
