#!/usr/bin/env python3
"""a733_bootpart.py: build on a real ext4 image (needs mkfs.ext4/debugfs/e2fsck),
write on a sparse image of the whole card (no real disk)."""
from __future__ import annotations

import hashlib
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import zlib
from pathlib import Path

A733 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(A733 / "tools"))
import a733_bootpart as bp  # noqa: E402
import a733_sdcard_layout as lay  # noqa: E402
from uimage_format import FORMAT, MAGIC, validate  # noqa: E402

S = lay.SECTOR
CARD_INFO = {"Number": 1, "FriendlyName": "Generic STORAGE DEVICE", "SerialNumber": "TEST-CARD-SERIAL",
             "Size": lay.CARD_BYTES, "BusType": "USB", "IsSystem": False, "IsBoot": False,
             "IsOffline": False, "IsReadOnly": False, "PartitionStyle": "MBR", "LogicalSectorSize": 512}
HAVE_E2FS = all(shutil.which(t) for t in ("mkfs.ext4", "debugfs", "e2fsck"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fake_ext4(seed: int) -> bytes:
    data = bytearray(hashlib.sha256(bytes([seed])).digest() * (bp.PART_BYTES // 32))
    struct.pack_into("<H", data, bp.EXT_MAGIC_OFFSET, 0xEF53)
    return bytes(data)


def stage0_image() -> bytes:
    payload = b"\x00" * 64 + b"stage0 test body"
    header = struct.pack(FORMAT, MAGIC, 0, int(time.time()), len(payload), 0x41000000, 0x41000000,
                         zlib.crc32(payload) & 0xffffffff, 5, 2, 2, 0, b"test stage0".ljust(32, b"\0"))
    return header[:4] + struct.pack(">I", zlib.crc32(header) & 0xffffffff) + header[8:] + payload


class Write(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.card = self.tmp / "card.img"
        with self.card.open("wb") as f:
            f.truncate(lay.CARD_BYTES)
        sec = bytearray(S)
        sec[446:462] = lay.mbr_entry(lay.BOOT)
        sec[462:478] = lay.mbr_entry(lay.IOS)
        sec[478:494] = lay.mbr_entry(lay.LOG)
        sec[510:512] = b"\x55\xaa"
        self.base, self.new = fake_ext4(1), fake_ext4(2)
        dev = lay.Device(str(self.card), writable=True)
        dev.write(0, bytes(sec))
        dev.write(16, b"BOOTLOADER" * 400 + b"\0" * (8192 - 4000))
        dev.write(lay.BOOT.start, self.base)
        dev.write(lay.IOS.start, b"H+ios root".ljust(S, b"\0"))
        dev.close()
        self.outside = self.read_outside()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def read_outside(self) -> str:
        dev = lay.Device(str(self.card))
        try:
            return sha(dev.read(0, lay.BOOT.start) + dev.read(lay.BOOT.end, 4096))
        finally:
            dev.close()

    def part1(self) -> bytes:
        dev = lay.Device(str(self.card))
        try:
            return dev.read(lay.BOOT.start, lay.BOOT.count)
        finally:
            dev.close()

    def write(self, image: bytes, expect: str, confirm=True) -> str:
        dev = lay.Device(str(self.card), writable=True)
        try:
            return bp.write_boot(dev, CARD_INFO, image, expect, self.tmp / "backups",
                                 lambda: confirm, log=lambda *_: None)
        finally:
            dev.close()

    def test_writes_only_partition_1_and_keeps_a_backup(self) -> None:
        self.assertEqual(self.write(self.new, sha(self.base)), "written")
        self.assertEqual(self.part1(), self.new)
        self.assertEqual(self.read_outside(), self.outside)
        backups = list((self.tmp / "backups").glob("*.bin"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), self.base)

    def test_rollback_with_the_base_image(self) -> None:
        self.write(self.new, sha(self.base))
        self.assertEqual(self.write(self.base, sha(self.new)), "written")
        self.assertEqual(self.part1(), self.base)
        self.assertEqual(self.read_outside(), self.outside)

    def test_wrong_current_hash_refuses_without_writing(self) -> None:
        with self.assertRaises(lay.LayoutError):
            self.write(self.new, sha(b"something else"))
        self.assertEqual(self.part1(), self.base)
        self.assertFalse((self.tmp / "backups").exists())

    def test_no_confirmation_writes_nothing(self) -> None:
        with self.assertRaises(lay.LayoutError):
            self.write(self.new, sha(self.base), confirm=False)
        self.assertEqual(self.part1(), self.base)

    def test_same_image_is_a_no_op(self) -> None:
        self.assertEqual(self.write(self.base, "unused"), "unchanged")

    def test_rejects_wrong_size_and_non_ext4(self) -> None:
        with self.assertRaises(bp.BootPartError):
            self.write(self.new[:-S], sha(self.base))
        with self.assertRaises(bp.BootPartError):
            self.write(b"\0" * bp.PART_BYTES, sha(self.base))

    def test_other_partition_1_is_refused(self) -> None:
        dev = lay.Device(str(self.card), writable=True)
        sec = bytearray(dev.read(0, 1))
        struct.pack_into("<I", sec, 446 + 12, lay.BOOT.count * 2)
        dev.write(0, bytes(sec))
        dev.close()
        with self.assertRaises(lay.LayoutError):
            self.write(self.new, sha(self.base))


@unittest.skipUnless(HAVE_E2FS, "mkfs.ext4, debugfs and e2fsck are needed")
class Build(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.base = self.tmp / "base.img"
        with self.base.open("wb") as f:
            f.truncate(bp.PART_BYTES)
        subprocess.run(["mkfs.ext4", "-q", "-b", "1024", "-L", "UEFI_STAGE0", str(self.base)], check=True)
        for name, data in (("boot.scr", b"old uefi script"), ("boot.cmd", b"echo old uefi\n"),
                           ("uefi_stage0.uimg", b"U" * 300000)):
            (self.tmp / name).write_bytes(data)
            bp.debugfs(self.base, f"write {self.tmp / name} /{name}", write=True)
        self.stage0 = self.tmp / "stage0.uimg"
        self.stage0.write_bytes(stage0_image())
        self.payload = self.tmp / "payload"
        self.payload.write_bytes(b"\0" * 4096 + b" ".join(bp.PAYLOAD_MARKERS) + b"\0" * 100000)
        self.cmd = self.tmp / "boot.cmd.new"
        self.cmd.write_bytes(b"echo SDROOT\r\nbootm 0x42000000 - 0x43000000\r\n")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def build(self, out: str = "new.img") -> dict:
        return bp.build(self.base, self.tmp / out, self.stage0, self.payload, self.cmd, log=lambda *_: None)

    def test_build_installs_files_and_keeps_the_old_script(self) -> None:
        before = self.base.read_bytes()
        manifest = self.build()
        self.assertEqual(self.base.read_bytes(), before)
        out = self.tmp / "new.img"
        self.assertEqual(manifest["output_sha256"], sha(out.read_bytes()))
        work = self.tmp / "dumps"
        work.mkdir()
        self.assertEqual(bp.dump(out, "/boot-uefi-v59.scr", work), b"old uefi script")
        self.assertEqual(bp.dump(out, "/boot-uefi-v59.cmd", work), b"echo old uefi\n")
        self.assertEqual(bp.dump(out, "/uefi_stage0.uimg", work), b"U" * 300000)
        self.assertEqual(bp.dump(out, "/ios-a733/a733-xnu.payload", work), self.payload.read_bytes())
        scr = bp.dump(out, "/boot.scr", work)
        validate(scr, 6)
        self.assertIn(b"echo SDROOT\nbootm", scr)
        self.assertEqual(subprocess.run(["e2fsck", "-fn", str(out)], capture_output=True).returncode, 0)

    def test_refuses_existing_output_and_already_built_base(self) -> None:
        self.build()
        with self.assertRaises(bp.BootPartError):
            self.build()
        self.base = self.tmp / "new.img"
        with self.assertRaises(bp.BootPartError):
            self.build("again.img")

    def test_refuses_a_payload_without_the_sdroot_driver(self) -> None:
        self.payload.write_bytes(b"rd=md0 cpus=1" + b"\0" * 1000)
        with self.assertRaises(bp.BootPartError):
            self.build()
        self.assertFalse((self.tmp / "new.img").exists())


if __name__ == "__main__":
    unittest.main()
