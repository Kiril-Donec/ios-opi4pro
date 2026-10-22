"""Host-side RAM root integration tests. No ARM board or iOS userland needed."""
from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "a733" / "tools"))
sys.path.insert(0, str(ROOT / "tools"))

import adt  # noqa: E402
import mkpayload  # noqa: E402
from package_xnu_a733 import _validate_ramdisk_args, _validate_sdroot_args  # noqa: E402
from mkadt_a733 import build as build_adt  # noqa: E402

BASE = "debug=0xc modem=0 wifi=0 sweetbattery=0 sweetcpufreq=0"


class RamdiskPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "test.img"
        with self.path.open("wb") as f:
            f.truncate(8 * 1024 * 1024)
            f.seek(1024)
            f.write(b"HX")

    def test_valid_hfsx_md0(self) -> None:
        _validate_ramdisk_args(BASE + " rd=md0", self.path)

    def test_no_ramdisk_baseline_still_allowed(self) -> None:
        _validate_ramdisk_args(BASE, None)

    def test_no_empty_md0_boot(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires a RAM disk"):
            _validate_ramdisk_args(BASE + " rd=md0", None)

    def test_reject_other_root(self) -> None:
        for extra in ("rd=ufsroot0", "rd=md0 rd=ufsroot0", "rootdev=md0"):
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, "requires exactly rd=md0"):
                _validate_ramdisk_args(BASE + " " + extra, self.path)

    def test_reject_missing_hfs_header(self) -> None:
        with self.path.open("r+b") as f:
            f.seek(1024)
            f.write(b"XX")
        with self.assertRaisesRegex(ValueError, "HFS"):
            _validate_ramdisk_args(BASE + " rd=md0", self.path)

    def test_reject_unaligned_or_oversize(self) -> None:
        with self.path.open("r+b") as f:
            f.truncate(8 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "aligned"):
            _validate_ramdisk_args(BASE + " rd=md0", self.path)
        with self.path.open("r+b") as f:
            f.truncate(17 * 1024 * 1024)
        with self.assertRaisesRegex(ValueError, "size"):
            _validate_ramdisk_args(BASE + " rd=md0", self.path)

    def test_adt_ramdisk_map(self) -> None:
        old = build_adt().serialize()
        pa = 0x102000000
        size = 8 * 1024 * 1024
        new = mkpayload.add_ramdisk_to_adt(old, pa, size)
        root, _ = adt.parse(new)
        chosen = next(x for x in root.children if x.name == "chosen")
        mmap = next(x for x in chosen.children if x.name == "memory-map")
        self.assertEqual(mmap.prop("RAMDisk"), struct.pack("<2Q", pa, size))
        self.assertEqual(struct.unpack("<Q", chosen.prop("dram-base"))[0], 0x100000000)


class SdrootArgsTests(unittest.TestCase):
    SD = BASE + " cpus=1 rd=sdroot0 unentitled_ios_sim_launch=1"

    def setUp(self) -> None:
        self.sd_adt = build_adt(sdmmc=True).serialize()

    def test_valid_sdroot(self) -> None:
        _validate_sdroot_args(self.SD, None, self.sd_adt)

    def test_other_roots_untouched(self) -> None:
        _validate_sdroot_args(BASE + " rd=md0", None, build_adt().serialize())

    def test_requires_sdmmc_adt_node(self) -> None:
        with self.assertRaisesRegex(ValueError, "--sdmmc"):
            _validate_sdroot_args(self.SD, None, build_adt().serialize())

    def test_refuses_ramdisk_second_root_rw_and_smp(self) -> None:
        with self.assertRaisesRegex(ValueError, "RAM disk"):
            _validate_sdroot_args(self.SD, Path("x.img"), self.sd_adt)
        with self.assertRaisesRegex(ValueError, "exactly rd=sdroot0"):
            _validate_sdroot_args(self.SD + " rd=md0", None, self.sd_adt)
        for extra in (" rootrw=1", " sdrw=1", " sdrw=2 rootrw=1"):
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, "sdrw=1"):
                _validate_sdroot_args(self.SD + extra, None, self.sd_adt)
        _validate_sdroot_args(self.SD + " sdrw=1 rootrw=1", None, self.sd_adt)
        with self.assertRaisesRegex(ValueError, "--a76-pair"):
            _validate_sdroot_args(self.SD.replace("cpus=1", "cpus=2"), None, self.sd_adt)
        for bad in ("cpus=3", "cpus=8", "cpus=0"):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "cpus=1 or cpus=2"):
                _validate_sdroot_args(self.SD.replace("cpus=1", bad), None, self.sd_adt)
        pair = build_adt(sdmmc=True, a76_pair=True).serialize()
        _validate_sdroot_args(self.SD.replace("cpus=1", "cpus=2"), None, pair)
        _validate_sdroot_args(self.SD, None, pair)                      # pair ADT, still one core


if __name__ == "__main__":
    unittest.main()
