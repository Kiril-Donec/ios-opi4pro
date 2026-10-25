#!/usr/bin/env python3
"""a733/xnu-a733-eth.patch (dxb 9999w, after 9999v): gmac0 Ethernet.

- bsd/dev/a733_eth.c: DWMAC 5.20 + sunxi-gmac-210 glue, clocks/resets, PH0-PH15
  as rgmii0, MDIO + clause-22 autonegotiation, one polled TX/RX ring in the
  ADT "dma-reg" window, a BSD ifnet en3 and a kernel DHCP client;
- bsd/dev/a733_power.c: AXP8191 DC1SW1/DC1SW2 (PHY and PH pin rails) on;
- IOFindBSDRoot starts it after the power button.

Host checks: syscon/PHY/MAC/checksum/DHCP logic, a syntax check of the kernel
part with XNU-signature stubs, register-write whitelist and wiring. Whether the
PHY links and DHCP answers is only proven by a board test.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_sdmmc_patch import CC, KERNEL_HEADERS, check_hunk_counts, files_in_patch, new_file_source

A733 = Path(__file__).resolve().parents[1]
PATCH = A733 / "xnu-a733-eth.patch"
TESTS = A733 / "tests"
NET_HEADERS = ("sys/errno.h", "kern/locks.h", "sys/kpi_mbuf.h", "sys/kpi_socket.h", "sys/sockio.h", "net/if.h",
               "net/if_types.h", "net/ethernet.h", "net/if_ether.h", "net/ether_if_module.h",
               "net/kpi_interface.h", "net/kpi_protocol.h", "netinet/in.h")


class EthPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = PATCH.read_text()
        cls.sections = files_in_patch(cls.text)
        cls.eth = new_file_source(cls.sections["bsd/dev/a733_eth.c"])
        cls.code = re.sub(r"/\*.*?\*/", "", cls.eth, flags=re.S)

    def test_shape(self) -> None:
        self.assertEqual(set(self.sections), {"bsd/conf/files", "bsd/dev/a733_eth.c", "bsd/dev/a733_power.c",
                                              "iokit/bsddev/IOKitBSDInit.cpp"})
        for path, section in self.sections.items():
            check_hunk_counts(section)
            self.assertEqual([l for l in section if l.startswith("-") and not l.startswith("---")], [], path)
        self.assertNotIn("\r", self.text)
        self.assertIn("#if defined(ARM64_BOARD_CONFIG_SWEET) || defined(A733_ETH_HOST_TEST)", self.eth)

    def test_wiring(self) -> None:
        files = "\n".join(self.sections["bsd/conf/files"])
        self.assertIn("+bsd/dev/a733_eth.c\t\t\tstandard", files)
        hook = "\n".join(self.sections["iokit/bsddev/IOKitBSDInit.cpp"])
        self.assertIn("+\t\textern void a733_eth_start(void);", hook)
        self.assertIn("+\t\ta733_eth_start();", hook)
        self.assertIn("\t\ta733_power_start();", hook)
        power = "\n".join(l[1:] for l in self.sections["bsd/dev/a733_power.c"] if l.startswith("+"))
        self.assertIn("volatile int a733_eth_power;", power)
        self.assertIn("extern volatile int a733_eth_power;", self.eth)
        self.assertIn('PE_parse_boot_argn("a733eth", &on, sizeof(on));', self.eth)

    def test_yt8531_clkout(self) -> None:
        # Board test #17: PHY 4f51:e91b (Motorcomm YT8531), RX fine, TX unanswered; CLK_OUT 125 MHz.
        self.assertRegex(self.code, r"#define YT8531_PHY_ID1\s+0x4f51")
        self.assertRegex(self.code, r"#define YT8531_SYNCE_CFG\s+0xa012")
        self.assertIn("eth.clk_ext = true;\n\teth_apply_variant(0);", self.eth)
        # YT8531 extended registers: only CLK_OUT (0xA012). Test #18: turning the PHY delays off
        # (mainline motorcomm.c for "rgmii") broke RX, so they stay as strapped.
        self.assertEqual(re.findall(r"\(void\)phy_ext_write\(([^;]*)\);", self.code),
                         ["YT8531_SYNCE_CFG, yt8531_clkout(old, v->phy125)"])
        self.assertIn("if (eth.phy_id1 == YT8531_PHY_ID1 && phy_ext_read(YT8531_SYNCE_CFG, &old) == 0) {", self.eth)

    def test_power_rails(self) -> None:
        power = "\n".join(l[1:] for l in self.sections["bsd/dev/a733_power.c"] if l.startswith("+"))
        self.assertRegex(power, r"#define AXP8191_DCDC_CTL2\s+0x11\b")
        self.assertRegex(power, r"#define AXP8191_DC1SW1\s+\(1u << 3\)")
        self.assertRegex(power, r"#define AXP8191_DC1SW2\s+\(1u << 4\)")
        # Read-modify-write: only sets the two switch bits, never clears DCDC enables.
        self.assertIn("uint8_t want = ctl | AXP8191_DC1SW1 | AXP8191_DC1SW2;", power)
        self.assertEqual(re.findall(r"twi_write\(([^;]*)\);", power),
                         ["AXP8191_ADDR, AXP8191_DCDC_CTL2, want"])
        self.assertIn("if (rc == 0 && want != ctl) {", power)

    def test_register_writes(self) -> None:
        code = self.code
        # CCU: only the gmac0 gates/resets, PTP and PHY clock, mbus gate bit 11 with the vendor key.
        self.assertEqual(sorted(set(re.findall(r"wr32\(eth\.ccu, (\w+),", code))),
                         ["CCU_GMAC0_BGR", "CCU_GMAC0_PHY", "CCU_GMAC_PTP", "CCU_MBUS_GATE"])
        self.assertRegex(code, r"#define CCU_MBUS_GATE\s+0x05e4")
        self.assertRegex(code, r"#define CCU_GMAC0_BGR\s+0x141c")
        self.assertRegex(code, r"#define CCU_GMAC0_PHY\s+0x1410")
        self.assertRegex(code, r"#define CCU_GMAC_PTP\s+0x1400")
        self.assertIn("rd32(eth.ccu, CCU_MBUS_GATE) | (1u << 11) | CCU_MBUS_GATE_KEY", code)
        self.assertRegex(code, r"#define CCU_MBUS_GATE_KEY\s+0x00040302u")
        # PIO: bank H registers only.
        self.assertEqual(sorted(set(re.findall(r"wr32\(eth\.pio, (\w+),", code))),
                         ["PIO_PH_CFG0", "PIO_PH_CFG1", "PIO_PH_DRV0", "PIO_PH_DRV1", "PIO_PH_PULL0"])
        for name, off in (("CFG0", "0x400"), ("CFG1", "0x404"), ("DRV0", "0x420"), ("DRV1", "0x424"),
                          ("PULL0", "0x430")):
            self.assertRegex(code, rf"#define PIO_PH_{name}\s+{off}\b")
        # SID is read only; syscon gets the computed value.
        self.assertNotIn("wr32(eth.sid", code)
        writes = re.findall(r"wr32\(eth\.syscon, ([^;]*)\);", code)
        self.assertGreaterEqual(len(writes), 4)
        for w in writes:
            self.assertRegex(w, r"^0, eth_syscon\([^()]*\)$")
        # Calibration: PHY loopback with forced speed, autonegotiation only afterwards.
        self.assertIn("(void)mdio_write(eth.phy_addr, 0, (1u << 14) | (1u << 8) | (k ? (1u << 6) : (1u << 13)));",
                      code)
        self.assertIn("\teth_calibrate();\n\teth_if_create();", code)
        self.assertIn("eth_mmc_report(\"after loopback calibration\");\n\teth.link = false;", code)
        # The DMA window must sit below 4 GiB (32-bit descriptors) and be page aligned.
        self.assertIn("dma[0] + ETH_DMA_SIZE > 0x100000000ull || (dma[0] & 0xfff)", code)
        self.assertIn("eth.dma = ml_io_map_wcomb(dma[0], ETH_DMA_SIZE);", code)
        # Layout fits the window.
        size = int(re.search(r"#define ETH_DMA_SIZE\s+(0x[0-9a-f]+)", code).group(1), 16)
        rxbuf = int(re.search(r"#define D_RXBUF\s+(0x[0-9a-f]+)", code).group(1), 16)
        txbuf = int(re.search(r"#define D_TXBUF\s+(0x[0-9a-f]+)", code).group(1), 16)
        rxdesc = int(re.search(r"#define D_RXDESC\s+(0x[0-9a-f]+)", code).group(1), 16)
        rx = int(re.search(r"#define RX_RING\s+(\d+)", code).group(1))
        tx = int(re.search(r"#define TX_RING\s+(\d+)", code).group(1))
        buf = int(re.search(r"#define BUF_SIZE\s+(\d+)", code).group(1))
        self.assertLessEqual(16 * tx, rxdesc)
        self.assertLessEqual(rxdesc + 16 * rx, txbuf)
        self.assertLessEqual(txbuf + buf * tx, rxbuf)
        self.assertLessEqual(rxbuf + buf * rx, size)

    def test_adt_node(self) -> None:
        tool = (A733 / "tools" / "mkadt_a733.py").read_text()
        self.assertIn('extra.append(Node("a733-eth", [', tool)
        for prop in ("reg", "syscon-reg", "ccu-reg", "pio-reg", "sid-reg", "dma-reg"):
            self.assertIn(f'("{prop}", u64(', tool[tool.index('Node("a733-eth"'):])
            self.assertIn(f'ETH_REG("{prop}", ', self.eth)
        self.assertIn("ETH_DMA_BASE = 0x60100000", tool)
        # Must not overlap the USB OHCI window.
        usb = re.search(r"USB_DMA_BASE = (0x[0-9a-fA-F]+)\nUSB_DMA_SIZE = (0x[0-9a-fA-F]+)", tool)
        self.assertLessEqual(int(usb.group(1), 16) + int(usb.group(2), 16), 0x60100000)
        self.assertNotIn('"interrupts"', tool[tool.index('Node("a733-eth"'):tool.index("return Node(\"device-tree\"")])

    @unittest.skipUnless(CC, "no host C compiler")
    def test_logic_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp, "a733_eth.c")
            src.write_text(self.eth)
            exe = Path(tmp, "test_eth_logic")
            subprocess.run([CC, "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                            "-DA733_ETH_HOST_TEST", "-include", str(src), str(TESTS / "test_eth_logic.c"),
                            "-o", str(exe)], check=True)
            out = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            self.assertIn("PASS", out.stdout)

    @unittest.skipUnless(CC, "no host C compiler")
    def test_kernel_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inc = Path(tmp, "inc")
            for header in KERNEL_HEADERS + NET_HEADERS:
                path = inc / header
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("/* stub */\n")
            src = Path(tmp, "a733_eth.c")
            src.write_text(self.eth)
            flags = ["-std=gnu11", "-fsyntax-only", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                     "-DARM64_BOARD_CONFIG_SWEET", "-I" + str(inc),
                     "-include", str(TESTS / "sdmmc_kernel_stubs.h"),
                     "-include", str(TESTS / "usbtouch_kernel_stubs.h"),
                     "-include", str(TESTS / "power_kernel_stubs.h"),
                     "-include", str(TESTS / "eth_kernel_stubs.h")]
            if "clang" in subprocess.run([CC, "--version"], capture_output=True, text=True).stdout:
                flags += ["-Wshorten-64-to-32"]
            subprocess.run([CC, *flags, str(src)], check=True)


if __name__ == "__main__":
    unittest.main()
