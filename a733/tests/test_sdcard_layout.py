#!/usr/bin/env python3
"""a733_sdcard_layout.py on a sparse image of the whole card (no real disk).

The image has the card's real geometry: 61891149824 bytes, MBR with the boot
partition (0x80, 0x83, sector 65536, 65536 sectors) and boot loader bytes at
sector 16. Results are checked with sfdisk, fsck.fat/mtools and the kernel
driver's own FAT32 log-file lookup when those tools are installed.
"""
from __future__ import annotations

import datetime
import json
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

A733 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(A733 / "tools"))
sys.path.insert(0, str(A733 / "tests"))
import a733_sdcard_layout as lay  # noqa: E402
import a733_sdlog  # noqa: E402

S = lay.SECTOR
CARD_INFO = {"Number": 1, "FriendlyName": "Generic STORAGE DEVICE", "SerialNumber": "TEST-CARD-SERIAL",
             "Size": lay.CARD_BYTES, "BusType": "USB", "IsSystem": False, "IsBoot": False,
             "IsOffline": False, "IsReadOnly": False, "PartitionStyle": "MBR", "LogicalSectorSize": 512}
NVME_INFO = {"Number": 0, "FriendlyName": "KINGSTON SNV3S1000G", "SerialNumber": "TEST-NVME-SERIAL",
             "Size": 1000204886016, "BusType": "NVMe", "IsSystem": True, "IsBoot": True,
             "IsOffline": False, "IsReadOnly": False, "PartitionStyle": "GPT", "LogicalSectorSize": 512}


def card_mbr() -> bytes:
    sec = bytearray(S)
    rnd = random.Random(7)
    sec[:440] = bytes(rnd.randrange(256) for _ in range(440))      # boot code area
    sec[440:444] = bytes.fromhex("12345678")                       # disk signature
    sec[446:462] = struct.pack("<B3sB3sII", 0x80, b"\x00\x02\x00", 0x83, b"\xfe\xff\xff", 65536, 65536)
    sec[510:512] = b"\x55\xaa"
    return bytes(sec)


def entry_bytes(sec: bytes, slot: int) -> bytes:
    return sec[446 + 16 * (slot - 1):462 + 16 * (slot - 1)]


class Guards(unittest.TestCase):
    def test_layout_constants(self) -> None:
        self.assertEqual(lay.BOOT.end, 131072)
        self.assertEqual((lay.IOS.start, lay.IOS.count), (196608, 33554432))
        self.assertEqual((lay.LOG.start, lay.LOG.count), (33751040, 524288))
        for p in (lay.IOS, lay.LOG):
            self.assertEqual(p.start % 2048, 0)                     # 1 MiB aligned
        self.assertLess(lay.LOG.end, lay.CARD_BYTES // S)
        self.assertGreater(lay.IOS.start, lay.BOOT.end)             # room to grow partition 1

    def test_disk_guards(self) -> None:
        self.assertEqual(lay.check_disk(CARD_INFO, 1, lay.CARD_BYTES), [])
        nvme = lay.check_disk(NVME_INFO, 0, lay.CARD_BYTES)
        self.assertTrue(any("disk 0" in p for p in nvme))
        self.assertTrue(any("system or boot" in p for p in nvme))
        self.assertTrue(any("NVMe" in p for p in nvme))
        for key, value, word in (("Size", lay.CARD_BYTES - S, "size"), ("BusType", "SATA", "bus"),
                                 ("PartitionStyle", "GPT", "MBR"), ("IsSystem", True, "system"),
                                 ("IsReadOnly", True, "read-only"), ("Number", 2, "not 1")):
            with self.subTest(key=key):
                bad = dict(CARD_INFO, **{key: value})
                self.assertTrue(any(word in p for p in lay.check_disk(bad, 1, lay.CARD_BYTES)), key)

    def test_mbr_states(self) -> None:
        total = lay.CARD_BYTES // S
        mbr = card_mbr()
        self.assertEqual(lay.check_mbr(lay.parse_mbr(mbr), total), "ready")
        new = lay.build_mbr(mbr)
        self.assertEqual(new[:462], mbr[:462])
        self.assertEqual(new[494:], mbr[494:])
        self.assertEqual(lay.check_mbr(lay.parse_mbr(new), total), "done")
        cases = {
            "partition 1": lambda b: b.__setitem__(slice(458, 462), struct.pack("<I", 131072)),
            "GPT": lambda b: b.__setitem__(450, 0xEE),
            "partition 4": lambda b: b.__setitem__(slice(494, 510), lay.mbr_entry(lay.Part(4, 0, 0x83, 40_000_000, 8))),
            "differ": lambda b: b.__setitem__(slice(462, 478), lay.mbr_entry(lay.Part(2, 0, 0x83, 196608, 1000))),
            "signature": lambda b: b.__setitem__(511, 0),
        }
        for word, mutate in cases.items():
            with self.subTest(word=word):
                b = bytearray(mbr)
                mutate(b)
                with self.assertRaisesRegex(lay.LayoutError, word):
                    lay.check_mbr(lay.parse_mbr(bytes(b)), total)
        half = bytearray(new)
        half[478:494] = bytes(16)                                   # only partition 2 present
        with self.assertRaisesRegex(lay.LayoutError, "differ"):
            lay.check_mbr(lay.parse_mbr(bytes(half)), total)
        with self.assertRaisesRegex(lay.LayoutError, "too small"):
            lay.check_mbr(lay.parse_mbr(mbr), lay.LOG.end - 1)

    def test_fat32_builder(self) -> None:
        data, info = lay.build_log_fat32(when=datetime.datetime(2026, 10, 22, 12, 0, 0), volume_id=0x1234)
        self.assertEqual(info["clusters"], 130553)
        self.assertGreaterEqual(info["clusters"], 65525)
        self.assertEqual(len(data), (info["file_sector"] * S) + lay.LOG_FILE_BYTES)
        self.assertEqual(data[info["file_sector"] * S:], a733_sdlog.prepared_bytes(lay.LOG_FILE_BYTES))
        self.assertEqual(data[:S], data[6 * S:7 * S])               # backup boot sector
        self.assertEqual(struct.unpack_from("<I", data, 28)[0], lay.LOG.start)   # hidden sectors
        fat1 = info["data_start"] - 2 * info["fat_sectors"]
        f1 = data[fat1 * S:(fat1 + info["fat_sectors"]) * S]
        f2 = data[(fat1 + info["fat_sectors"]) * S:info["data_start"] * S]
        self.assertEqual(f1, f2)


@unittest.skipIf(os.name == "nt", "sparse card image test runs on Linux")
class CardImage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.img = self.dir / "card.img"
        with self.img.open("wb") as f:
            f.truncate(lay.CARD_BYTES)
            f.write(card_mbr())
            f.seek(16 * S)
            self.spl = bytes(random.Random(1).randrange(256) for _ in range(32 * 1024))
            f.write(self.spl)                                        # boot loader at 8 KiB
            f.seek(lay.BOOT.start * S)
            f.write(b"ext4 partition one".ljust(4096, b"\x01"))
        self.before = self.read(0, lay.BACKUP_SECTORS)
        self.lines: list[str] = []

    def read(self, sector: int, count: int) -> bytes:
        with self.img.open("rb") as f:
            f.seek(sector * S)
            return f.read(count * S)

    def apply(self, confirm=lambda: True) -> str:
        dev = lay.Device(str(self.img), writable=True)
        try:
            return lay.apply_layout(dev, CARD_INFO, self.dir / "backups", confirm, log=self.lines.append)
        finally:
            dev.close()

    def test_apply_changes_only_the_planned_bytes(self) -> None:
        self.assertEqual(self.apply(), "applied")
        after = self.read(0, lay.BACKUP_SECTORS)
        # Sector 0: only entries 2 and 3 changed; boot loader and partition 1 untouched.
        self.assertEqual(after[:462], self.before[:462])
        self.assertEqual(after[494:], self.before[494:])
        self.assertEqual(entry_bytes(after, 2), lay.mbr_entry(lay.IOS))
        self.assertEqual(entry_bytes(after, 3), lay.mbr_entry(lay.LOG))
        self.assertEqual(self.read(16, len(self.spl) // S), self.spl)
        # Nothing between the end of the first 64 MiB and the log partition was written.
        self.assertEqual(self.read(lay.IOS.start, 2048), bytes(2048 * S))
        backups = sorted((self.dir / "backups").glob("*.bin"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), self.before)
        meta = json.loads(backups[0].with_suffix(".json").read_text())
        self.assertEqual(meta["disk"]["SerialNumber"], "TEST-CARD-SERIAL")
        # Second run: already done, no new backup, no writes.
        self.assertEqual(self.apply(), "done")
        self.assertEqual(len(list((self.dir / "backups").glob("*.bin"))), 1)

    def test_abort_writes_nothing(self) -> None:
        with self.assertRaisesRegex(lay.LayoutError, "aborted"):
            self.apply(confirm=lambda: False)
        self.assertEqual(self.read(0, lay.BACKUP_SECTORS), self.before)
        self.assertEqual(self.read(lay.LOG.start, 8), bytes(8 * S))

    @unittest.skipUnless(shutil.which("sfdisk"), "sfdisk not installed")
    def test_sfdisk_reads_the_new_table(self) -> None:
        self.apply()
        out = subprocess.run(["sfdisk", "--dump", str(self.img)], capture_output=True, text=True, check=True).stdout
        self.assertIn("label: dos", out)
        self.assertRegex(out, r"card\.img1 : start=\s*65536, size=\s*65536, type=83, bootable")
        self.assertRegex(out, r"card\.img2 : start=\s*196608, size=\s*33554432, type=af")
        self.assertRegex(out, r"card\.img3 : start=\s*33751040, size=\s*524288, type=c")

    @unittest.skipUnless(shutil.which("fsck.fat") and shutil.which("mdir") and shutil.which("mtype"),
                         "dosfstools/mtools not installed")
    def test_log_partition_is_valid_fat32_with_the_file(self) -> None:
        self.apply()
        part = self.dir / "log.img"
        part.write_bytes(self.read(lay.LOG.start, lay.LOG.count))
        fsck = subprocess.run(["fsck.fat", "-n", "-v", str(part)], capture_output=True, text=True)
        self.assertEqual(fsck.returncode, 0, fsck.stdout + fsck.stderr)
        self.assertIn("2 FATs, 32 bit entries", fsck.stdout)
        self.assertIn("130553 data clusters", fsck.stdout)
        mdir = subprocess.run(["mdir", "-i", str(part), "::"], capture_output=True, text=True, check=True).stdout
        self.assertRegex(mdir, r"A733LOG\s+TXT\s+67\s?108\s?864")
        self.assertIn("A733LOG", mdir.splitlines()[0])                 # volume label
        head = subprocess.run(["mtype", "-i", str(part), "::A733LOG.TXT"], capture_output=True, check=True).stdout
        self.assertEqual(head, a733_sdlog.prepared_bytes(lay.LOG_FILE_BYTES))
        self.assertEqual(a733_sdlog.extract(head)[1], ["The board has not written to this file yet."])

    @unittest.skipUnless(shutil.which("cc"), "no C compiler")
    def test_kernel_driver_finds_the_log_file(self) -> None:
        import test_sdmmc_patch as sp
        self.apply()
        part = self.dir / "log.img"
        part.write_bytes(self.read(lay.LOG.start, lay.LOG.count))
        src = self.dir / "a733_sdmmc.c"
        src.write_text(sp.new_file_source(sp.files_in_patch(sp.PATCH.read_text())["bsd/dev/a733_sdmmc.c"]))
        exe = self.dir / "finder"
        subprocess.run(["cc", "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                        "-DA733_SD_HOST_TEST", "-include", str(src), str(sp.TESTS / "test_sdmmc_logic.c"),
                        "-o", str(exe)], check=True)
        out = subprocess.run([str(exe), str(part)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout)
        _, info = lay.build_log_fat32()
        self.assertIn(f"FOUND sector {info['file_sector']} size {lay.LOG_FILE_BYTES}", out.stdout)

    def test_write_ios_and_restore(self) -> None:
        ios = self.dir / "ios.img"
        body = bytearray(8 << 20)
        body[1024:1026] = b"H+"
        body[-5:] = b"tail!"
        ios.write_bytes(body)
        dev = lay.Device(str(self.img), writable=True)
        try:
            with self.assertRaisesRegex(lay.LayoutError, "run apply first"):
                lay.write_ios(dev, CARD_INFO, ios, lambda: True, log=self.lines.append)
        finally:
            dev.close()
        self.apply()
        dev = lay.Device(str(self.img), writable=True)
        try:
            lay.write_ios(dev, CARD_INFO, ios, lambda: True, log=self.lines.append)
            self.assertEqual(self.read(lay.IOS.start, len(body) // S), bytes(body))
            self.assertEqual(self.read(lay.IOS.start + len(body) // S, 1), bytes(S))
            # Not a raw HFS+ volume, too large, unaligned: refused before any write.
            bad = self.dir / "bad.img"
            bad.write_bytes(bytes(8 << 20))
            with self.assertRaisesRegex(lay.LayoutError, "HFS"):
                lay.write_ios(dev, CARD_INFO, bad, lambda: True)
            with bad.open("r+b") as f:
                f.truncate(lay.IOS.count * S + S)
            with self.assertRaisesRegex(lay.LayoutError, "does not fit"):
                lay.write_ios(dev, CARD_INFO, bad, lambda: True)
            bad.write_bytes(b"x" * 1000)
            with self.assertRaisesRegex(lay.LayoutError, "multiple of 512"):
                lay.write_ios(dev, CARD_INFO, bad, lambda: True)
            # Restore the original sector 0 from the apply backup.
            backup = next((self.dir / "backups").glob("*.bin"))
            with self.assertRaisesRegex(lay.LayoutError, "different disk"):
                lay.restore_mbr(dev, dict(CARD_INFO, SerialNumber="other"), backup, lambda: True)
            lay.restore_mbr(dev, CARD_INFO, backup, lambda: True, log=self.lines.append)
        finally:
            dev.close()
        self.assertEqual(self.read(0, 1), self.before[:S])


@unittest.skipIf(os.name == "nt", "image tests run on Linux")
class HfsJournalFlag(unittest.TestCase):
    """hfs-journal: XNU recreated the journal of the root volume (board test #2)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def fake_volume(self, attrs: int = 0x80002100) -> tuple[Path, lay.Part]:
        img = self.dir / "vol.img"
        part = lay.Part(2, 0, 0xAF, 0, 65536)                       # 32 MiB "partition" at sector 0
        vh = bytearray(S)
        vh[0:2] = b"HX"
        struct.pack_into(">HIIII", vh, 2, 5, attrs, 0x482B4C78, 129, 0x11223344)   # version..createDate
        struct.pack_into(">II", vh, 40, 4096, 8192)                  # 8192 x 4 KiB = 32 MiB
        with img.open("wb") as f:
            f.truncate(part.count * S)
            f.seek(2 * S)
            f.write(vh)
            f.seek((part.count - 2) * S)
            alt = bytearray(vh)
            alt[8:12] = b"fsck"                                     # lastMountedVersion may differ
            f.write(alt)
        return img, part

    def test_clear_and_restore_only_attribute_bytes(self) -> None:
        img, part = self.fake_volume()
        before = img.read_bytes()
        dev = lay.Device(str(img), writable=True)
        try:
            self.assertEqual(lay.hfs_set_journaled(dev, CARD_INFO, False, self.dir / "b", lambda: True,
                                                   part=part, log=lambda *_: None), "changed")
            after = img.read_bytes()
            diff = [i for i in range(len(before)) if before[i] != after[i]]
            self.assertTrue(diff and all(i % S in (4, 5, 6, 7) for i in diff), diff[:8])
            for sector in (2, part.count - 2):
                self.assertEqual(struct.unpack_from(">I", after, sector * S + 4)[0], 0x80000100)
            self.assertEqual(lay.hfs_set_journaled(dev, CARD_INFO, False, self.dir / "b", lambda: True,
                                                   part=part, log=lambda *_: None), "unchanged")
            lay.hfs_set_journaled(dev, CARD_INFO, True, self.dir / "b", lambda: True, part=part,
                                  log=lambda *_: None)
        finally:
            dev.close()
        self.assertEqual(img.read_bytes(), before)
        self.assertEqual(len(list((self.dir / "b").glob("*.bin"))), 2)

    def test_refusals(self) -> None:
        img, part = self.fake_volume()
        before = img.read_bytes()
        dev = lay.Device(str(img), writable=True)
        try:
            with self.assertRaisesRegex(lay.LayoutError, "aborted"):
                lay.hfs_set_journaled(dev, CARD_INFO, False, self.dir, lambda: False, part=part,
                                      log=lambda *_: None)
            self.assertEqual(img.read_bytes(), before)
        finally:
            dev.close()
        img, part = self.fake_volume(attrs=0x80002000)              # not cleanly unmounted
        dev = lay.Device(str(img), writable=True)
        try:
            with self.assertRaisesRegex(lay.LayoutError, "cleanly unmounted"):
                lay.hfs_set_journaled(dev, CARD_INFO, False, self.dir, lambda: True, part=part,
                                      log=lambda *_: None)
            dev.write(part.count - 2, bytes(S))                      # alternate header gone
            with self.assertRaisesRegex(lay.LayoutError, "alternate"):
                lay.hfs_set_journaled(dev, CARD_INFO, False, self.dir, lambda: True, part=part)
            dev.write(2, bytes(S))
            with self.assertRaisesRegex(lay.LayoutError, "no HFS"):
                lay.hfs_set_journaled(dev, CARD_INFO, False, self.dir, lambda: True, part=part)
        finally:
            dev.close()

    @unittest.skipUnless(shutil.which("mkfs.hfsplus") and shutil.which("fsck.hfsplus"), "hfsprogs not installed")
    def test_real_journaled_hfsplus_volume(self) -> None:
        img = self.dir / "real.img"
        with img.open("wb") as f:
            f.truncate(64 << 20)
        subprocess.run(["mkfs.hfsplus", "-J", "-s", "-v", "A733TEST", str(img)], check=True, capture_output=True)
        part = lay.Part(2, 0, 0xAF, 0, (64 << 20) // S)
        dev = lay.Device(str(img), writable=True)
        try:
            _, primary, _, _ = lay.hfs_headers(dev, part)
            self.assertTrue(struct.unpack_from(">I", primary, 4)[0] & lay.HFS_JOURNALED)
            self.assertEqual(lay.hfs_set_journaled(dev, CARD_INFO, False, self.dir, lambda: True,
                                                   part=part, log=lambda *_: None), "changed")
        finally:
            dev.close()
        fsck = subprocess.run(["fsck.hfsplus", "-f", "-n", str(img)], capture_output=True, text=True)
        self.assertEqual(fsck.returncode, 0, fsck.stdout + fsck.stderr)
        self.assertIn("appears to be OK", fsck.stdout + fsck.stderr)
        self.assertNotRegex(fsck.stdout + fsck.stderr, r"Checking Journaled HFS")


class CommandLine(unittest.TestCase):
    def test_disk_zero_refused_before_anything(self) -> None:
        out = subprocess.run([sys.executable, str(A733 / "tools" / "a733_sdcard_layout.py"), "--disk", "0", "apply"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertIn("disk 0 is never touched", out.stdout)

    @unittest.skipIf(os.name == "nt", "checks the non-Windows refusal")
    def test_non_windows_refused(self) -> None:
        out = subprocess.run([sys.executable, str(A733 / "tools" / "a733_sdcard_layout.py"), "plan"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertIn("Windows", out.stdout)


if __name__ == "__main__":
    unittest.main()
