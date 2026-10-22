#!/usr/bin/env python3
"""Lay out the Orange Pi 4 Pro boot card for the microSD iOS root (Windows).

Adds two MBR partitions after the untouched boot partition 1:

  slot 1  sector     65536, 32 MiB   ext4 (0x83)  boot, NOT changed
  slot 2  sector    196608, 16 GiB   HFS+ (0xAF)  iOS root, rd=sdroot0 sdpart=2
  slot 3  sector  33751040, 256 MiB  FAT32 (0x0C) A733LOG.TXT console log

Nothing before sector 196608 is written except MBR entries 2 and 3 in
sector 0 (the Allwinner boot loader at sector 16 and partition 1 stay
byte-identical; the card must stay MBR: a GPT would overwrite the boot
loader). The FAT32 partition is written complete, with a contiguous 64 MiB
A733LOG.TXT, so Windows never has to format it.

  python a733_sdcard_layout.py plan                 dry run (default), no writes
  python a733_sdcard_layout.py apply --backup-dir DIR
  python a733_sdcard_layout.py write-ios IMAGE      raw HFS+ volume -> partition 2
  python a733_sdcard_layout.py restore-mbr BACKUP   put the old sector 0 back

Run from an administrator terminal (raw disk access). Only a disk that is
not number 0, not a system/boot disk, on USB/SD, exactly the expected size,
MBR, and whose partition 1 is exactly the boot partition above is accepted;
apply and write-ios ask for the disk number and serial number to be typed.
"""
from __future__ import annotations

import argparse
import array
import datetime
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a733_sdlog  # noqa: E402

SECTOR = 512
CHUNK = 4 << 20
CARD_BYTES = 61_891_149_824          # the owner's card (Windows Disk 1)
ALLOWED_BUS = {"USB", "SD", "MMC"}
BACKUP_SECTORS = (64 << 20) // SECTOR


@dataclass(frozen=True)
class Part:
    slot: int
    status: int
    type: int
    start: int
    count: int

    @property
    def end(self) -> int:
        return self.start + self.count


BOOT = Part(1, 0x80, 0x83, 65536, 65536)
IOS = Part(2, 0x00, 0xAF, 196608, 33554432)
LOG = Part(3, 0x00, 0x0C, IOS.end, (256 << 20) // SECTOR)
LOG_FILE_BYTES = 64 << 20
FAT_SPC = 4                           # 2 KiB clusters: 130553 clusters, FAT32


class LayoutError(Exception):
    pass


# --- MBR -------------------------------------------------------------------

def parse_mbr(sec: bytes) -> list[Part | None]:
    if len(sec) != SECTOR or sec[510:512] != b"\x55\xaa":
        raise LayoutError("sector 0 has no MBR signature")
    parts: list[Part | None] = []
    for i in range(4):
        e = sec[446 + 16 * i:462 + 16 * i]
        start, count = struct.unpack_from("<II", e, 8)
        empty = e[4] == 0 and start == 0 and count == 0
        parts.append(None if empty else Part(i + 1, e[0], e[4], start, count))
    return parts


def describe(p: Part | None) -> str:
    if p is None:
        return "empty"
    return (f"type 0x{p.type:02x}{' boot' if p.status == 0x80 else ''}, sectors {p.start}-{p.end - 1} "
            f"({p.count * SECTOR / (1 << 20):.0f} MiB)")


def check_mbr(parts: list[Part | None], total_sectors: int) -> str:
    """'ready' (slots 2-4 empty) or 'done' (already laid out); else LayoutError."""
    if any(p is not None and p.type == 0xEE for p in parts):
        raise LayoutError("the card has a GPT (protective MBR); this tool only handles the MBR card")
    if parts[0] != BOOT:
        raise LayoutError(f"partition 1 is {describe(parts[0])}, expected the boot partition "
                          f"{describe(BOOT)}: not the A733 card, or it was changed")
    if parts[3] is not None:
        raise LayoutError(f"partition 4 is in use ({describe(parts[3])})")
    if LOG.end > total_sectors:
        raise LayoutError("the card is too small for the layout")
    if parts[1] is None and parts[2] is None:
        return "ready"
    if parts[1] == IOS and parts[2] == LOG:
        return "done"
    raise LayoutError(f"partitions 2/3 already exist and differ from the plan: "
                      f"2 = {describe(parts[1])}, 3 = {describe(parts[2])}")


def mbr_entry(p: Part) -> bytes:
    # CHS fields FE FF FF: "use LBA" (the partitions lie beyond 8 GiB anyway).
    return struct.pack("<B3sB3sII", p.status, b"\xfe\xff\xff", p.type, b"\xfe\xff\xff", p.start, p.count)


def build_mbr(sec: bytes) -> bytes:
    new = bytearray(sec)
    new[446 + 16:446 + 32] = mbr_entry(IOS)
    new[446 + 32:446 + 48] = mbr_entry(LOG)
    assert new[:462] == sec[:462] and new[494:] == sec[494:]
    return bytes(new)


# --- FAT32 log partition ---------------------------------------------------

def fat_datetime(when: datetime.datetime) -> tuple[int, int]:
    date = ((when.year - 1980) << 9) | (when.month << 5) | when.day
    time = (when.hour << 11) | (when.minute << 5) | (when.second // 2)
    return date, time


def build_log_fat32(part: Part = LOG, file_bytes: int = LOG_FILE_BYTES,
                    when: datetime.datetime | None = None, volume_id: int | None = None) -> tuple[bytes, dict]:
    """
    FAT32 volume (Microsoft fatgen103 layout) for the whole partition, as the
    bytes of its first sectors up to the end of A733LOG.TXT; the rest of the
    partition is free clusters whose content does not matter. The file sits
    in clusters 3.. right after the root directory: one contiguous run, as
    bsd/dev/a733_sdmmc.c requires.
    """
    when = when or datetime.datetime.now().replace(microsecond=0)
    volume_id = volume_id if volume_id is not None else int(when.timestamp()) & 0xffffffff
    spc, reserved, nfats, total = FAT_SPC, 32, 2, part.count
    fatsz = -(-(total - reserved) // ((256 * spc + nfats) // 2))
    data_start = reserved + nfats * fatsz
    clusters = (total - data_start) // spc
    cbytes = spc * SECTOR
    if clusters < 65525 or fatsz * (SECTOR // 4) < clusters + 2 or file_bytes % cbytes:
        raise LayoutError("bad FAT32 geometry")
    first, nfile = 3, file_bytes // cbytes

    bs = bytearray(SECTOR)
    bs[0:11] = b"\xeb\x58\x90MSWIN4.1"
    struct.pack_into("<HBHBHHBHHHII", bs, 11, SECTOR, spc, reserved, nfats, 0, 0, 0xF8, 0, 63, 255,
                     part.start, total)
    struct.pack_into("<IHHIHH12xBBBI11s8s", bs, 36, fatsz, 0, 0, 2, 1, 6, 0x80, 0, 0x29, volume_id,
                     b"A733LOG    ", b"FAT32   ")
    bs[510:512] = b"\x55\xaa"
    fsi = bytearray(SECTOR)
    struct.pack_into("<I", fsi, 0, 0x41615252)
    struct.pack_into("<III", fsi, 484, 0x61417272, clusters - 1 - nfile, first + nfile)
    struct.pack_into("<I", fsi, 508, 0xAA550000)

    fat = bytearray(fatsz * SECTOR)
    struct.pack_into("<III", fat, 0, 0x0FFFFFF8, 0x0FFFFFFF, 0x0FFFFFFF)   # media, clean, root EOC
    chain = array.array("I", range(first + 1, first + nfile + 1))
    chain[-1] = 0x0FFFFFFF
    if sys.byteorder != "little":
        chain.byteswap()
    fat[first * 4:(first + nfile) * 4] = chain.tobytes()

    date, time = fat_datetime(when)
    root = bytearray(cbytes)
    struct.pack_into("<11sB10xHH", root, 0, b"A733LOG    ", 0x08, time, date)
    struct.pack_into("<11sBBBHHHHHHHI", root, 32, b"A733LOG TXT", 0x20, 0, 0, time, date, date,
                     first >> 16, time, date, first & 0xffff, file_bytes)

    region = bytearray(data_start * SECTOR)
    for s, blob in ((0, bs), (1, fsi), (6, bs), (7, fsi)):
        region[s * SECTOR:(s + 1) * SECTOR] = blob
    for i in range(nfats):
        off = (reserved + i * fatsz) * SECTOR
        region[off:off + len(fat)] = fat
    data = bytes(region) + bytes(root) + a733_sdlog.prepared_bytes(file_bytes)
    info = {"clusters": clusters, "fat_sectors": fatsz, "data_start": data_start,
            "file_sector": data_start + spc, "file_bytes": file_bytes}
    return data, info


# --- devices and guards ----------------------------------------------------

class Device:
    """Sector I/O on \\\\.\\PhysicalDriveN (or an image file in tests)."""

    def __init__(self, path: str, writable: bool = False) -> None:
        self.path = path
        self.f = open(path, "r+b" if writable else "rb", buffering=0)

    def close(self) -> None:
        self.f.close()

    def read(self, sector: int, count: int) -> bytes:
        self.f.seek(sector * SECTOR)
        out = bytearray()
        while len(out) < count * SECTOR:
            chunk = self.f.read(min(CHUNK, count * SECTOR - len(out)))
            if not chunk:
                raise LayoutError(f"short read at sector {sector}")
            out += chunk
        return bytes(out)

    def write(self, sector: int, data: bytes) -> None:
        if len(data) % SECTOR:
            raise LayoutError("unaligned write")
        self.f.seek(sector * SECTOR)
        view = memoryview(data)
        done = 0
        while done < len(view):
            n = self.f.write(view[done:done + CHUNK])
            if not n:
                raise LayoutError(f"write failed at sector {sector + done // SECTOR}")
            done += n
        os.fsync(self.f.fileno())


def check_disk(info: dict, number: int, expect_bytes: int) -> list[str]:
    problems = []
    if number == 0 or info.get("Number") == 0:
        problems.append("disk 0 is never touched (it is the system NVMe on this PC)")
    if info.get("Number") != number:
        problems.append(f"disk info is for disk {info.get('Number')}, not {number}")
    if info.get("IsSystem") or info.get("IsBoot"):
        problems.append("this is a system or boot disk")
    if info.get("BusType") not in ALLOWED_BUS:
        problems.append(f"bus {info.get('BusType')} is not a card reader (USB/SD/MMC)")
    if info.get("Size") != expect_bytes:
        problems.append(f"size {info.get('Size')} bytes, expected the card's {expect_bytes}")
    if info.get("PartitionStyle") != "MBR":
        problems.append(f"partition style {info.get('PartitionStyle')}, expected MBR")
    if info.get("LogicalSectorSize") != SECTOR:
        problems.append("sector size is not 512")
    if info.get("IsOffline") or info.get("IsReadOnly"):
        problems.append("disk is offline or read-only")
    return problems


def same_disk(a: dict, b: dict) -> bool:
    return all(a.get(k) == b.get(k) for k in ("Number", "SerialNumber", "Size", "FriendlyName"))


def windows_disk_info(number: int) -> dict:
    ps = (f"Get-Disk -Number {int(number)} | Select-Object Number,FriendlyName,SerialNumber,Size,BusType,"
          "IsSystem,IsBoot,IsOffline,IsReadOnly,PartitionStyle,LogicalSectorSize | ConvertTo-Json")
    out = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                         capture_output=True, text=True)
    if out.returncode or not out.stdout.strip():
        raise LayoutError(f"Get-Disk -Number {number} failed: {out.stderr.strip()}")
    return json.loads(out.stdout)


def windows_rescan(number: int) -> str:
    ps = (f"Update-Disk -Number {int(number)}; Start-Sleep -Seconds 2; Get-Partition -DiskNumber {int(number)} | "
          "Select-Object PartitionNumber,Offset,Size,MbrType,DriveLetter | Format-Table -AutoSize | Out-String")
    out = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                         capture_output=True, text=True)
    return (out.stdout + out.stderr).strip()


def is_admin() -> bool:
    if os.name != "nt":
        return os.geteuid() == 0
    import ctypes
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def confirm_typed(info: dict, action: str) -> bool:
    phrase = f"DISK {info['Number']} {info['SerialNumber']}"
    print(f"\n{action}\nDisk {info['Number']}: {info['FriendlyName']}, {info['Size']} bytes, "
          f"serial {info['SerialNumber']}, {info['BusType']}.")
    try:
        answer = input(f"Type exactly '{phrase}' to continue, anything else aborts: ")
    except EOFError:
        return False
    return answer.strip() == phrase


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_verified(dev: Device, sector: int, data: bytes, what: str) -> None:
    dev.write(sector, data)
    if sha256(dev.read(sector, len(data) // SECTOR)) != sha256(data):
        raise LayoutError(f"read-back of {what} does not match what was written")


# --- actions ---------------------------------------------------------------

def plan_text(parts: list[Part | None] | None, state: str) -> str:
    lines = []
    if parts is not None:
        lines.append("Current MBR:")
        lines += [f"  {i + 1}: {describe(p)}" for i, p in enumerate(parts)]
    if state == "done":
        lines.append("Already laid out: nothing to do.")
    else:
        lines.append("Planned (only MBR entries 2 and 3 of sector 0 change):")
        for p in (BOOT, IOS, LOG):
            lines.append(f"  {p.slot}: {describe(p)}{'   (unchanged)' if p is BOOT else ''}")
        lines.append(f"Writes: FAT32 file system (~1 MiB) + {LOG_FILE_BYTES >> 20} MiB A733LOG.TXT from "
                     f"sector {LOG.start}, then MBR entries 2-3. First a backup of the first "
                     f"{BACKUP_SECTORS * SECTOR >> 20} MiB (MBR, boot loader, partition 1).")
    return "\n".join(lines)


def apply_layout(dev: Device, info: dict, backup_dir: Path, confirm, recheck=None, log=print) -> str:
    """Backup, FAT32 log partition, MBR. Returns 'done' or 'applied'."""
    sec0 = dev.read(0, 1)
    parts = parse_mbr(sec0)
    state = check_mbr(parts, info["Size"] // SECTOR)
    log(plan_text(parts, state))
    if state == "done":
        return "done"
    if not confirm():
        raise LayoutError("aborted: confirmation not given")

    backup_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(backup_dir).free < BACKUP_SECTORS * SECTOR + (32 << 20):
        raise LayoutError(f"not enough free space in {backup_dir} for the 64 MiB backup")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = backup_dir / f"card{info['Number']}-first64MiB-before-sdlayout-{stamp}"
    head = dev.read(0, BACKUP_SECTORS)
    if head[:SECTOR] != sec0:
        raise LayoutError("sector 0 changed while reading")
    img = base.with_suffix(".bin")
    img.write_bytes(head)
    if sha256(img.read_bytes()) != sha256(head):
        raise LayoutError("backup file read-back mismatch")
    digest = sha256(head)
    # LF even on Windows, so `sha256sum -c` (Git Bash, Linux) can check it.
    base.with_suffix(".bin.sha256").write_bytes(f"{digest}  {img.name}\n".encode())
    base.with_suffix(".json").write_text(json.dumps({
        "disk": info, "sectors": BACKUP_SECTORS, "sha256": digest, "created": stamp,
        "mbr_before": [describe(p) for p in parts]}, indent=2))
    log(f"Backup: {img} ({len(head) >> 20} MiB, sha256 {digest[:16]}...)")

    if recheck:
        recheck()
    fat, fat_info = build_log_fat32()
    write_verified(dev, LOG.start, fat, "the FAT32 log partition")
    log(f"FAT32 written and verified: {fat_info['clusters']} clusters, A733LOG.TXT at partition sector "
        f"{fat_info['file_sector']}")

    if recheck:
        recheck()
    if dev.read(0, 1) != sec0:
        raise LayoutError("sector 0 changed during the operation; MBR NOT written")
    new = build_mbr(sec0)
    write_verified(dev, 0, new, "sector 0")
    if check_mbr(parse_mbr(dev.read(0, 1)), info["Size"] // SECTOR) != "done":
        raise LayoutError("MBR check after writing failed")
    log("MBR written and verified: partition 2 = iOS (HFS+), partition 3 = FAT32 log.")
    return "applied"


def check_ios_image(path: Path) -> int:
    size = path.stat().st_size
    if size == 0 or size % SECTOR:
        raise LayoutError(f"{path}: size {size} is not a multiple of 512")
    if size > IOS.count * SECTOR:
        raise LayoutError(f"{path}: {size} bytes does not fit partition 2 ({IOS.count * SECTOR} bytes)")
    with path.open("rb") as f:
        f.seek(1024)
        sig = f.read(2)
    if sig not in (b"H+", b"HX"):
        raise LayoutError(f"{path}: no HFS+/HFSX volume header at offset 1024 (raw volume image expected, "
                          "not a disk image with a partition table)")
    return size


def write_ios(dev: Device, info: dict, image: Path, confirm, recheck=None, log=print) -> str:
    size = check_ios_image(image)
    if check_mbr(parse_mbr(dev.read(0, 1)), info["Size"] // SECTOR) != "done":
        raise LayoutError("partition 2 does not exist yet: run apply first")
    log(f"Writing {image} ({size / (1 << 30):.2f} GiB) to partition 2, sector {IOS.start}.")
    if not confirm():
        raise LayoutError("aborted: confirmation not given")
    if recheck:
        recheck()
    src = hashlib.sha256()
    written = 0
    with image.open("rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            dev.write(IOS.start + written // SECTOR, chunk)
            src.update(chunk)
            written += len(chunk)
            if written % (512 << 20) < CHUNK:
                log(f"  written {written >> 20} / {size >> 20} MiB")
    back = hashlib.sha256()
    for off in range(0, size, CHUNK):
        n = min(CHUNK, size - off)
        back.update(dev.read(IOS.start + off // SECTOR, n // SECTOR))
    if back.hexdigest() != src.hexdigest():
        raise LayoutError("read-back of the iOS image does not match")
    log(f"iOS image written and verified (sha256 {src.hexdigest()}).")
    return src.hexdigest()


def restore_mbr(dev: Device, info: dict, backup: Path, confirm, force: bool = False, log=print) -> None:
    meta_path = backup.with_suffix(".json")
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        if not same_disk(meta["disk"], info):
            raise LayoutError("the backup was made from a different disk")
    elif not force:
        raise LayoutError(f"{meta_path} missing; use --force only if you are sure this backup is of this card")
    with backup.open("rb") as f:
        old = f.read(SECTOR)
    parse_mbr(old)
    cur = dev.read(0, 1)
    # Only the partition entries 2-4 may differ; anything else means another card or other changes.
    if (old[:462] != cur[:462] or old[510:] != cur[510:]) and not force:
        raise LayoutError("backup sector 0 differs outside partition entries 2-4: refusing")
    log("Restoring sector 0 from " + str(backup))
    if not confirm():
        raise LayoutError("aborted: confirmation not given")
    write_verified(dev, 0, old, "sector 0")
    log("Sector 0 restored. Data written to partitions 2/3 is left on the card (now unallocated).")


# --- command line ----------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--disk", type=int, default=1, help="Windows disk number of the card (default 1)")
    ap.add_argument("--expect-bytes", type=int, default=CARD_BYTES, help="exact card size in bytes")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("plan", help="dry run: checks and planned layout, no writes (default)")
    a = sub.add_parser("apply", help="backup, create the FAT32 log partition, write the MBR entries")
    a.add_argument("--backup-dir", type=Path, default=Path.home() / "a733-card-backups")
    w = sub.add_parser("write-ios", help="write a raw HFS+ volume image to partition 2")
    w.add_argument("image", type=Path)
    r = sub.add_parser("restore-mbr", help="restore sector 0 from an apply backup")
    r.add_argument("backup", type=Path)
    r.add_argument("--force", action="store_true")
    args = ap.parse_args()
    cmd = args.cmd or "plan"

    if args.disk == 0:
        print("REFUSED: disk 0 is never touched.")
        return 2
    if os.name != "nt":
        print("REFUSED: this tool drives Windows disks (\\\\.\\PhysicalDriveN).")
        return 2
    try:
        info = windows_disk_info(args.disk)
        problems = check_disk(info, args.disk, args.expect_bytes)
        print(f"Disk {info.get('Number')}: {info.get('FriendlyName')}, {info.get('Size')} bytes, "
              f"{info.get('BusType')}, serial {info.get('SerialNumber')}, {info.get('PartitionStyle')}")
        if problems:
            print("REFUSED:\n  - " + "\n  - ".join(problems))
            return 2
        if not is_admin():
            print("Disk checks passed. Reading sector 0 needs an administrator terminal: "
                  "Win+X -> Terminal (Admin), then run this again.")
            print(plan_text(None, "ready"))
            return 1 if cmd != "plan" else 0

        def recheck() -> None:
            if not same_disk(windows_disk_info(args.disk), info):
                raise LayoutError("the disk changed (card removed or swapped?): stopping")

        path = f"\\\\.\\PhysicalDrive{int(info['Number'])}"
        if cmd == "plan":
            dev = Device(path)
            try:
                parts = parse_mbr(dev.read(0, 1))
                print(plan_text(parts, check_mbr(parts, info["Size"] // SECTOR)))
                print("Dry run only: nothing was written. Next: apply --backup-dir DIR")
            finally:
                dev.close()
            return 0
        dev = Device(path, writable=True)
        try:
            if cmd == "apply":
                result = apply_layout(dev, info, args.backup_dir,
                                      lambda: confirm_typed(info, "This writes MBR entries 2-3 and the FAT32 log "
                                                            "partition (after a backup of the first 64 MiB)."),
                                      recheck)
                if result == "applied":
                    print(windows_rescan(args.disk))
                    print("Done. Windows should show the FAT32 partition 'A733LOG' with A733LOG.TXT. "
                          "Never click 'Format' if Windows offers it for another partition.")
            elif cmd == "write-ios":
                write_ios(dev, info, args.image,
                          lambda: confirm_typed(info, "This overwrites partition 2 (iOS root) completely."),
                          recheck)
            else:
                restore_mbr(dev, info, args.backup,
                            lambda: confirm_typed(info, "This rewrites sector 0 from the backup."), args.force)
                print(windows_rescan(args.disk))
        finally:
            dev.close()
    except (LayoutError, OSError, json.JSONDecodeError) as exc:
        print(f"REFUSED / FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
