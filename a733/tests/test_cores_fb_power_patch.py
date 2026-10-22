#!/usr/bin/env python3
"""a733/xnu-a733-cores-fb-power.patch (dxb 9999q, after 9999p):

- SweetCPU accepts the six Cortex-A55 cores (MPIDR 0x000-0x500) besides the
  two A76s;
- a733_cpu_present() scales in physical row order (sequential 64-bit stores
  into the write-combined framebuffer) and presents at 30 Hz by default;
- bsd/dev/a733_power.c: power button on the PMICs (R_TWI0), PSCI
  SYSTEM_OFF/RESET as PE_halt_restart, CPU clock report.

Host checks: the new scaler against the old loop pixel for pixel, the power
logic, a syntax check of the kernel part with XNU-signature stubs, and the
wiring. None of this proves the A55s, the button or PSCI work on the board.
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
PATCH = A733 / "xnu-a733-cores-fb-power.patch"
TESTS = A733 / "tests"
CXX = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")


def new_side(section: list[str]) -> str:
    """Text of the patched file covered by the hunks (context + added lines)."""
    out, in_hunk = [], False
    for line in section:
        if line.startswith("@@"):
            in_hunk = True
            continue
        if in_hunk and (line.startswith(" ") or line.startswith("+") or line == ""):
            out.append(line[1:] if line else "")
    return "\n".join(out) + "\n"


class CoresFbPowerPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = PATCH.read_text()
        cls.sections = files_in_patch(cls.text)
        cls.power = new_file_source(cls.sections["bsd/dev/a733_power.c"])
        cls.code = re.sub(r"/\*.*?\*/", "", cls.power, flags=re.S)
        cls.fb = new_side(cls.sections["iokit/Kernel/arm/SweetFramebuffer.cpp"])

    def test_patch_shape(self) -> None:
        self.assertEqual(set(self.sections), {
            "bsd/conf/files", "bsd/dev/a733_power.c", "iokit/Kernel/arm/SweetCPU.cpp",
            "iokit/Kernel/arm/SweetFramebuffer.cpp", "iokit/bsddev/IOKitBSDInit.cpp"})
        for section in self.sections.values():
            check_hunk_counts(section)
        self.assertNotIn("\r", self.text)
        for path, section in self.sections.items():
            for line in section:
                if line.startswith("+") and not line.startswith("+++"):
                    code = line[1:].split("//")[0]
                    quotes = len(re.findall(r'(?<!\\)"', code.replace("'\"'", "")))
                    self.assertEqual(quotes % 2, 0, f"{path}: unbalanced quotes in {line!r}")

    def test_cpu_whitelist(self) -> None:
        cpu = "\n".join(self.sections["iokit/Kernel/arm/SweetCPU.cpp"])
        self.assertIn("-\tif ((cpu->phys_id != 0x600 && cpu->phys_id != 0x700) ||", cpu)
        self.assertIn("+\tif ((cpu->phys_id & ~0x700u) != 0 || topology->num_cpus > SWEET_SMP_MAX_CPUS) {", cpu)
        # exactly MPIDR 0x000..0x700 in steps of 0x100 pass
        ok = [m for m in range(0, 0x10000, 0x100) if (m & ~0x700) == 0] + [m for m in range(1, 0x100) if (m & ~0x700) == 0]
        self.assertEqual(sorted(ok), [i * 0x100 for i in range(8)])
        self.assertIn('"Cortex-A76" : "Cortex-A55"', cpu)
        # the boot CPU requirement (0x600, logical 0) stays
        self.assertNotIn("boot_cpu", "".join(l for l in self.sections["iokit/Kernel/arm/SweetCPU.cpp"]
                                             if l.startswith(("+", "-"))))

    def test_wiring(self) -> None:
        files = "\n".join(self.sections["bsd/conf/files"])
        self.assertIn("+bsd/dev/a733_power.c\t\t\tstandard", files)
        self.assertIn(" bsd/dev/a733_usbtouch.c\t\t\tstandard", files)     # after 9999p
        hook = "\n".join(self.sections["iokit/bsddev/IOKitBSDInit.cpp"])
        self.assertIn("+\t\textern void a733_power_start(void);", hook)
        self.assertIn("+\t\ta733_power_start();", hook)
        self.assertIn("\t\ta733_usbtouch_start();", hook)
        self.assertIn("uint32_t hz = fPhys == 0xBBF11000ULL ? 30 : 10;", self.fb)
        self.assertIn('PE_parse_boot_argn("sweetfb_hz", &hz, sizeof(hz));', self.fb)

    def test_power_safety(self) -> None:
        src, code = self.power, self.code
        self.assertIn("#if defined(ARM64_BOARD_CONFIG_SWEET) || defined(A733_POWER_HOST_TEST)", src)
        # PSCI only for halt (0) and restart (1); every panic type keeps the old path.
        self.assertIn("if (type != 0 && type != 1) {\n\t\treturn -1;", src)
        self.assertEqual(sorted(set(re.findall(r"0x8400000[0-9a-f]u", code))), ["0x84000008u", "0x84000009u"])
        self.assertIn("a733_sd_log_panic_flush();\n\tint32_t rc = pw_psci(", src)
        # PMIC writes: only the power-key IRQ enable / status registers of the two PMICs.
        writes = re.findall(r"twi_write\(([^;]*)\);", code)
        self.assertEqual(len(writes), 4)                # definition + 3 calls
        for w in writes[1:]:
            self.assertRegex(w, r"pk_chips\[c\]\.addr, pk_chips\[c\]\.(en_reg|st_reg),")
        self.assertIn("{ AXP8191_ADDR, AXP8191_IRQ_EN2, AXP8191_IRQ_ST2, AXP8191_PRESS, AXP8191_RELEASE", src)
        self.assertRegex(src, r"#define AXP8191_IRQ_EN2\s+0x41\b")
        self.assertRegex(src, r"#define AXP8191_IRQ_ST2\s+0x49\b")
        self.assertRegex(src, r"#define AXP515_INTEN4\s+0x43\b")
        self.assertRegex(src, r"#define AXP515_INTSTS4\s+0x4b\b")
        # R_CCU: only the R_TWI0 gate/reset bits are set; CPU PLL block is read only.
        self.assertEqual(re.findall(r"wr32\(pw\.rccu, (\w+),", code), ["RCCU_TWI_BGR"])
        self.assertNotIn("wr32(pw.cpupll", code)
        self.assertIn("twi_ccr_for(in_hz, 100000, &scl)", src)

    def build(self, tmp: str, compiler: str, flags: list[str], src_name: str, source: str, test: Path) -> Path:
        src = Path(tmp, src_name)
        src.write_text(source)
        exe = Path(tmp, test.stem)
        subprocess.run([compiler, *flags, "-include", str(src), str(test), "-o", str(exe)], check=True)
        return exe

    @unittest.skipUnless(CC, "no host C compiler")
    def test_power_logic_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exe = self.build(tmp, CC, ["-std=c11", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                                       "-DA733_POWER_HOST_TEST"], "a733_power.c", self.power,
                             TESTS / "test_power_logic.c")
            out = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    @unittest.skipUnless(CXX, "no host C++ compiler")
    def test_scaler_matches_old_loop(self) -> None:
        start = self.fb.index("\t/*\n\t * CPU scaling, nearest neighbour.")
        end = self.fb.index("\t__asm__ volatile(\"dsb sy\" ::: \"memory\");\n\t/* From now on console text")
        block = self.fb[start:end]
        self.assertNotIn("dst[(physical_h - 1u - x) * stride + y]", block)
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "scaler_block.inc").write_text(block)
            exe = Path(tmp, "test_fb_scaler")
            subprocess.run([CXX, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-variable",
                            "-I", tmp, str(TESTS / "test_fb_scaler.cpp"), "-o", str(exe)], check=True)
            out = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            self.assertIn("PASS", out.stdout)

    @unittest.skipUnless(CC, "no host C compiler")
    def test_power_kernel_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inc = Path(tmp, "inc")
            for header in KERNEL_HEADERS + ("kern/cpu_number.h",):
                path = inc / header
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("/* stub */\n")
            src = Path(tmp, "a733_power.c")
            src.write_text(self.power)
            flags = ["-std=gnu11", "-fsyntax-only", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                     "-DARM64_BOARD_CONFIG_SWEET", "-I" + str(inc), "-Wno-cast-function-type",
                     "-include", str(TESTS / "sdmmc_kernel_stubs.h"),
                     "-include", str(TESTS / "usbtouch_kernel_stubs.h"),
                     "-include", str(TESTS / "power_kernel_stubs.h")]
            is_clang = "clang" in subprocess.run([CC, "--version"], capture_output=True, text=True).stdout
            if is_clang:
                flags += ["-Wshorten-64-to-32", "-Wno-cast-function-type-mismatch", "-Wno-unknown-warning-option",
                          "--target=aarch64-linux-gnu"]
            elif subprocess.run([CC, "-dumpmachine"], capture_output=True, text=True).stdout.startswith("aarch64"):
                pass
            else:
                self.skipTest("the SMC inline assembly needs an arm64 compiler (clang --target or native gcc)")
            subprocess.run([CC, *flags, str(src)], check=True)


if __name__ == "__main__":
    unittest.main()
