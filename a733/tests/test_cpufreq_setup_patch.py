#!/usr/bin/env python3
"""a733/xnu-a733-cpufreq-setup.patch (dxb 9999r, after 9999q):

- bsd/dev/a733_power.c: the vendor Linux cpufreq ported (efuse speed bin,
  OPP tables of sun60iw2p1-cpu-vf.dtsi, AXP8191 DCDC3/DCDC5 rails, in-place
  CPU PLL retune), THS thermal stepping, triple press -> clean shutdown;
- bsd/dev/a733_sdmmc.c: a733_sd_log_sync() (log flushed before each step);
- bsd/dev/a733_firstboot.c + bsd_init hook: one-time Setup-skip preferences;
- SweetFramebuffer: 20 Hz.

Host checks: the pure logic on the real vendor tables, kernel syntax with
XNU-signature stubs, and safety limits. Nothing here proves the clocks,
rails or the Setup skip on the board.
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
PATCH = A733 / "xnu-a733-cpufreq-setup.patch"
PATCH_Q = A733 / "xnu-a733-cores-fb-power.patch"
TESTS = A733 / "tests"
VF_DTSI_ROWS = {   # (cluster, MHz) -> mV per bin from sun60iw2p1-cpu-vf.dtsi (24 MHz), spot checks
    ("cf_a76", 1992): [1050, 0, 0, 0, 1050, 1000, 0, 1000, 960],
    ("cf_a76", 1608): [850, 950, 850, 900, 840, 820, 850, 820, 820],
    ("cf_a55", 1800): [1000, 0, 1050, 0, 1000, 950, 0, 950, 900],
    ("cf_dsu", 1056): [0, 950, 850, 860, 840, 800, 840, 800, 800],
}


def patched_power() -> str:
    """bsd/dev/a733_power.c of 9999q with the 9999r hunks applied (git apply)."""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp, "bsd/dev/a733_power.c")
        src.parent.mkdir(parents=True)
        src.write_text(new_file_source(files_in_patch(PATCH_Q.read_text())["bsd/dev/a733_power.c"]))
        subprocess.run(["git", "apply", "--include=bsd/dev/a733_power.c", str(PATCH)], cwd=tmp, check=True)
        return src.read_text()


class CpufreqSetupPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = PATCH.read_text()
        cls.sections = files_in_patch(cls.text)
        cls.power = patched_power()
        cls.pcode = re.sub(r"/\*.*?\*/", "", cls.power, flags=re.S)
        cls.firstboot = new_file_source(cls.sections["bsd/dev/a733_firstboot.c"])

    def test_patch_shape(self) -> None:
        self.assertEqual(set(self.sections), {
            "bsd/conf/files", "bsd/dev/a733_firstboot.c", "bsd/dev/a733_power.c", "bsd/dev/a733_sdmmc.c",
            "bsd/kern/bsd_init.c", "iokit/Kernel/arm/SweetFramebuffer.cpp"})
        for section in self.sections.values():
            check_hunk_counts(section)
        self.assertNotIn("\r", self.text)
        for path, section in self.sections.items():
            for line in section:
                if line.startswith("+") and not line.startswith("+++"):
                    # drop complete string literals first ("//" may sit inside one), then no quote is left
                    code = re.sub(r'"(?:\\.|[^"\\])*"', "", line[1:].replace("'\"'", ""))
                    self.assertNotIn('"', code.split("//")[0], f"{path}: unbalanced quotes in {line!r}")

    def test_wiring(self) -> None:
        files = "\n".join(self.sections["bsd/conf/files"])
        self.assertIn("+bsd/dev/a733_firstboot.c\t\tstandard", files)
        init = "\n".join(self.sections["bsd/kern/bsd_init.c"])
        self.assertIn("+\t\ta733_firstboot_tweaks();", init)
        sd = "\n".join(self.sections["bsd/dev/a733_sdmmc.c"])
        self.assertIn("+a733_sd_log_sync(void)", sd)
        self.assertIn("+\tlck_mtx_lock(&a733_sd_lock);", sd)
        fb = "\n".join(self.sections["iokit/Kernel/arm/SweetFramebuffer.cpp"])
        self.assertIn("+\tuint32_t hz = fPhys == 0xBBF11000ULL ? 20 : 10;", fb)

    def test_vendor_tables_copied(self) -> None:
        for (name, mhz), mv in VF_DTSI_ROWS.items():
            body = self.power[self.power.index(f"static const struct cf_opp {name}[]"):]
            body = body[:body.index("};")]
            row = re.search(rf"\{{\s*{mhz}, \{{([^}}]*)\}} \}}", body)
            self.assertIsNotNone(row, (name, mhz))
            self.assertEqual([int(v) for v in row.group(1).split(",")], mv, (name, mhz))

    def test_power_safety(self) -> None:
        code = self.pcode
        # Only the two CPU rails are ever written, never above the vendor tables' 1.05 V.
        writes = re.findall(r"twi_write\(AXP8191_ADDR, (\w+),", code)
        self.assertEqual(sorted(set(writes)), ["reg"])                       # only inside cf_set_mv
        self.assertEqual(re.findall(r"cf_set_mv\((AXP8191_DC\d_VOL)", code),
                         ["AXP8191_DC3_VOL", "AXP8191_DC5_VOL", "AXP8191_DC3_VOL", "AXP8191_DC5_VOL"])
        self.assertIn("#define CF_MAX_MV               1050", self.power)
        self.assertIn("if (mv > CF_MAX_MV || mv < 700) {", self.power)
        self.assertRegex(self.power, r"#define AXP8191_DC3_VOL\s+0x14\b")
        self.assertRegex(self.power, r"#define AXP8191_DC5_VOL\s+0x16\b")
        # Rails go up before the PLLs and down after them.
        apply = code[code.index("\ncf_apply("):]
        apply = apply[:apply.index("\n}\n")]
        order = [m.group(0) for m in re.finditer(r"w[35] [<>] cf\.v[35]|cf_set_pll", apply)]
        self.assertEqual(order, ["w3 > cf.v3", "w5 > cf.v5", "cf_set_pll", "cf_set_pll", "cf_set_pll",
                                 "w3 < cf.v3", "w5 < cf.v5"])
        # PLL writes only to the three CPU PLL registers; N within the vendor 28..94.
        self.assertEqual(sorted(set(re.findall(r"wr32\(pw\.cpupll, (\w+),", code))), ["off"])
        self.assertEqual(sorted(set(re.findall(r"cf_set_pll\((CPUPLL_\w+)", code))),
                         ["CPUPLL_A55", "CPUPLL_A76", "CPUPLL_DSU"])
        self.assertIn("return (n >= 28 && n <= 94) ? n : 0;", self.power)
        # The PLL is only retuned when its CPU clock runs from it with P = 1.
        self.assertIn("((clk >> 24) & 7) != 3 || ((clk >> 16) & 3) != 0", self.power)
        # Efuse / PLL block are read only; CCU only gets the THS / GPADC gate bits.
        self.assertNotIn("wr32(cf.sid", code)
        self.assertEqual(sorted(set(re.findall(r"wr32\(cf\.ccu, (\w+),", code))),
                         ["CCU_GPADC0_24M", "CCU_GPADC0_BGR", "CCU_THS0_BGR"])
        # Every step is logged and flushed to the card before it happens.
        for fn in ("\ncf_set_mv(", "\ncf_set_pll("):
            body = code[code.index(fn):]
            body = body[:body.index("\n}\n")]
            self.assertLess(body.index("cf_sync();"), body.index("twi_write" if "mv" in fn else "wr32"))
        # Shutdown: the regular BSD path, halt only.
        self.assertIn("reboot_kernel(RB_HALT, msg)", self.power)
        self.assertIn('PE_parse_boot_argn("a733cpufreq", &level, sizeof(level));', self.power)

    def test_firstboot_safety(self) -> None:
        src = self.firstboot
        self.assertIn("#if defined(ARM64_BOARD_CONFIG_SWEET)", src)
        # Writes only under the mobile preferences, the known container, and the marker.
        paths = re.findall(r'fb_write\(([^,]+),', re.sub(r"/\*.*?\*/", "", src, flags=re.S))
        self.assertEqual([p.strip() for p in paths[1:]],
                         ["path", 'FB_ARK_DIR "/Library/internal/data_ark.plist"', "FB_MARKER"])
        self.assertIn('#define FB_PREFS        "/private/var/mobile/Library/Preferences/"', src)
        for key in ("SetupDone", "SetupFinishedAllSteps", "LastSystemVersion", "BKNoWatchdogs",
                    "LockdownActivationIndicatesCloudConfigurationAvailable", "-ActivationState",
                    "ReduceMotionEnabled", "EnhancedBackgroundContrastEnabled"):
            self.assertIn(f"<key>{key}</key>", src)
        self.assertIn('if (mode != 2 && fb_exists(FB_MARKER)) {', src)
        self.assertIn("if (failed == 0) {", src)                    # marker only after success

    def build_logic(self, tmp: str) -> Path:
        src = Path(tmp, "a733_power.c")
        src.write_text(self.power)
        exe = Path(tmp, "test_power_logic_r")
        subprocess.run([CC, "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                        "-DA733_POWER_HOST_TEST", "-include", str(src), str(TESTS / "test_power_logic_r.c"),
                        "-o", str(exe)], check=True)
        return exe

    @unittest.skipUnless(CC, "no host C compiler")
    def test_logic_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run([str(self.build_logic(tmp))], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def kernel_flags(self, inc: Path) -> list[str] | None:
        flags = ["-std=gnu11", "-fsyntax-only", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                 "-DARM64_BOARD_CONFIG_SWEET", "-I" + str(inc), "-Wno-cast-function-type",
                 "-include", str(TESTS / "sdmmc_kernel_stubs.h")]
        if "clang" not in subprocess.run([CC, "--version"], capture_output=True, text=True).stdout:
            return None
        return flags + ["-Wshorten-64-to-32", "-Wno-cast-function-type-mismatch", "-Wno-unknown-warning-option",
                        "--target=aarch64-linux-gnu"]

    def stub_headers(self, tmp: str, extra: tuple[str, ...]) -> Path:
        inc = Path(tmp, "inc")
        for header in KERNEL_HEADERS + extra:
            path = inc / header
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("/* stub */\n")
        return inc

    @unittest.skipUnless(CC, "no host C compiler")
    def test_power_kernel_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flags = self.kernel_flags(self.stub_headers(tmp, ("kern/cpu_number.h", "sys/reboot.h")))
            if flags is None:
                self.skipTest("needs clang --target=aarch64 (SMC inline assembly)")
            src = Path(tmp, "a733_power.c")
            src.write_text(self.power)
            subprocess.run([CC, *flags, "-include", str(TESTS / "usbtouch_kernel_stubs.h"),
                            "-include", str(TESTS / "power_kernel_stubs.h"), str(src)], check=True)

    @unittest.skipUnless(CC, "no host C compiler")
    def test_firstboot_kernel_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inc = self.stub_headers(tmp, ("sys/fcntl.h", "sys/vnode.h", "sys/vnode_internal.h", "sys/namei.h",
                                          "sys/kauth.h"))
            flags = self.kernel_flags(inc) or ["-std=gnu11", "-fsyntax-only", "-Wall", "-Wextra", "-Werror",
                                               "-Wno-unused-parameter", "-DARM64_BOARD_CONFIG_SWEET",
                                               "-I" + str(inc), "-include", str(TESTS / "sdmmc_kernel_stubs.h")]
            src = Path(tmp, "a733_firstboot.c")
            src.write_text(self.firstboot)
            subprocess.run([CC, *flags, "-include", str(TESTS / "firstboot_kernel_stubs.h"), str(src)], check=True)


if __name__ == "__main__":
    unittest.main()
