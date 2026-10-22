#!/usr/bin/env python3
"""Replace the boot partition (MBR partition 1, 32 MiB ext4) of the A733 card.

Two separate steps, so nothing is improvised on the real card:

  build  (Linux/WSL, needs debugfs/e2fsck; never opens a disk)
         python3 a733_bootpart.py build BASE.img NEW.img --stage0 S --payload P [--boot-cmd C]
         BASE is partition 1 as it is on the card (for example cut from the
         64 MiB apply backup). NEW is a copy with /ios-a733/stage0.uimg,
         /ios-a733/a733-xnu.payload and the SDROOT boot.scr/boot.cmd; the old
         boot.scr/boot.cmd stay as /boot-uefi-v59.scr and /boot-uefi-v59.cmd.
         Every written file is read back with debugfs and compared, then
         e2fsck -fn must report a clean file system. BASE is never modified.

  write  (Windows, administrator terminal)
         python a733_bootpart.py write NEW.img --expect-current SHA256
         Partition 1 is rewritten only if what is on the card right now hashes
         to SHA256, i.e. it is exactly the image NEW was built from. The current
         partition is saved to --backup-dir first. The MBR, the boot loader at
         sector 16 and partitions 2/3 are never written.
         Rollback: write BASE.img --expect-current <sha256 of NEW.img>.

The same disk guards as a733_sdcard_layout.py apply: not disk 0, not a system
disk, USB/SD bus, exact card size, MBR with the expected partition 1, and the
disk number and serial number must be typed.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a733_sdcard_layout as lay  # noqa: E402
from uimage_format import script_image, validate  # noqa: E402

PART_BYTES = lay.BOOT.count * lay.SECTOR
EXT_MAGIC_OFFSET = 1024 + 56
PAYLOAD_MARKERS = (b"rd=sdroot0", b"A733 SD: sdroot0 ready, read-only PIO")
# Cortex-A76 cores only: cpus=1, or cpus=2 with the second A76 (mkadt --a76-pair).
CPU_MARKERS = (b" cpus=1 ", b" cpus=2 ")
SCRIPT_NAME = "ios-a733 XNU SDROOT"
KEEP_SCR, KEEP_CMD = "/boot-uefi-v59.scr", "/boot-uefi-v59.cmd"


class BootPartError(Exception):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_ext4(image: bytes) -> None:
    if len(image) != PART_BYTES:
        raise BootPartError(f"image is {len(image)} bytes, partition 1 is {PART_BYTES}")
    if struct.unpack_from("<H", image, EXT_MAGIC_OFFSET)[0] != 0xEF53:
        raise BootPartError("image has no ext2/3/4 superblock")


# --- build (Linux/WSL) -------------------------------------------------------

def debugfs(image: Path, command: str, write: bool = False) -> str:
    args = ["debugfs"] + (["-w"] if write else []) + ["-R", command, str(image)]
    out = subprocess.run(args, capture_output=True, text=True)
    err = out.stderr.lower()
    # debugfs exits 0 on most command errors; its messages are the only signal.
    if out.returncode or any(m in err for m in ("not found", "no space", "permission denied", "not open",
                                                 "already exists", "could not allocate", "error")):
        raise BootPartError(f"debugfs {command!r}: {out.stderr.strip()}")
    return out.stdout


def exists(image: Path, path: str) -> bool:
    out = subprocess.run(["debugfs", "-R", f"stat {path}", str(image)], capture_output=True, text=True)
    return "not found" not in out.stderr.lower() and "Inode:" in out.stdout


def dump(image: Path, path: str, work: Path) -> bytes:
    target = work / f"dump-{abs(hash(path))}"
    target.unlink(missing_ok=True)
    debugfs(image, f"dump {path} {target}")
    return target.read_bytes()


def check_inputs(stage0: bytes, payload: bytes) -> None:
    validate(stage0, 2)
    missing = [m.decode() for m in PAYLOAD_MARKERS if m not in payload]
    if not any(m in payload for m in CPU_MARKERS):
        missing.append("cpus=1 or cpus=2")
    if missing:
        raise BootPartError(f"payload is not an rd=sdroot0 kernel (missing {missing})")


def build(base: Path, output: Path, stage0: Path, payload: Path, cmd: Path, log=print) -> dict:
    if output.exists():
        raise BootPartError(f"{output} exists: refusing to overwrite")
    base_bytes = base.read_bytes()
    check_ext4(base_bytes)
    stage0_bytes, payload_bytes = stage0.read_bytes(), payload.read_bytes()
    check_inputs(stage0_bytes, payload_bytes)
    cmd_bytes = cmd.read_bytes().replace(b"\r\n", b"\n")
    scr_bytes = script_image(cmd_bytes, SCRIPT_NAME)
    validate(scr_bytes, 6)
    for path, wanted in (("/boot.scr", True), ("/ios-a733", False), (KEEP_SCR, False), (KEEP_CMD, False)):
        if exists(base, path) != wanted:
            raise BootPartError(f"{path} {'missing from' if wanted else 'already in'} the base image")
    files = {"/ios-a733/stage0.uimg": stage0_bytes, "/ios-a733/a733-xnu.payload": payload_bytes,
             "/boot.cmd": cmd_bytes, "/boot.scr": scr_bytes}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        part = work / "part1.img"
        shutil.copyfile(base, part)
        old_scr = dump(part, "/boot.scr", work)
        kept = {KEEP_SCR: old_scr}
        if exists(part, "/boot.cmd"):
            kept[KEEP_CMD] = dump(part, "/boot.cmd", work)
        for i, (path, data) in enumerate(kept.items()):
            (work / f"keep{i}").write_bytes(data)
            debugfs(part, f"write {work / f'keep{i}'} {path}", write=True)
        debugfs(part, "rm /boot.scr", write=True)
        if KEEP_CMD in kept:
            debugfs(part, "rm /boot.cmd", write=True)
        debugfs(part, "mkdir /ios-a733", write=True)
        for i, (path, data) in enumerate(files.items()):
            (work / f"new{i}").write_bytes(data)
            debugfs(part, f"write {work / f'new{i}'} {path}", write=True)
        for path, data in {**kept, **files}.items():
            if sha256(dump(part, path, work)) != sha256(data):
                raise BootPartError(f"read-back of {path} differs")
        fsck = subprocess.run(["e2fsck", "-fn", str(part)], capture_output=True, text=True)
        if fsck.returncode:
            raise BootPartError(f"e2fsck -fn reports problems:\n{fsck.stdout}{fsck.stderr}")
        new = part.read_bytes()
        check_ext4(new)
        shutil.copyfile(part, output)
    manifest = {
        "base": str(base), "base_sha256": sha256(base_bytes),
        "output": str(output), "output_sha256": sha256(new),
        "files": {p: {"bytes": len(d), "sha256": sha256(d)} for p, d in {**kept, **files}.items()},
        "fsck": fsck.stdout.strip().splitlines()[-1],
    }
    output.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n")
    log(f"Built {output}: sha256 {manifest['output_sha256']} from base {manifest['base_sha256']}.")
    log(manifest["fsck"])
    return manifest


# --- write (Windows) ---------------------------------------------------------

def write_boot(dev: lay.Device, info: dict, image: bytes, expect_current: str, backup_dir: Path,
               confirm, recheck=None, log=print) -> str:
    check_ext4(image)
    parts = lay.parse_mbr(dev.read(0, 1))
    lay.check_mbr(parts, info["Size"] // lay.SECTOR)       # partition 1 must be exactly the boot partition
    current = dev.read(lay.BOOT.start, lay.BOOT.count)
    if sha256(current) == sha256(image):
        log("Partition 1 already holds this image: nothing to do.")
        return "unchanged"
    if sha256(current) != expect_current.lower():
        raise lay.LayoutError(f"partition 1 on the card is {sha256(current)}, expected {expect_current}: "
                              "it is not the image this one was built from; refusing")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"card{info['Number']}-part1-before-bootpart-{stamp}.bin"
    backup.write_bytes(current)
    backup.with_name(backup.name + ".sha256").write_text(f"{sha256(current)}  {backup.name}\n", newline="\n")
    log(f"Saved the current partition 1 to {backup}.")
    log(f"Writing {len(image) >> 20} MiB to partition 1 (sector {lay.BOOT.start}), sha256 {sha256(image)}.")
    if not confirm():
        raise lay.LayoutError("aborted: confirmation not given")
    if recheck:
        recheck()
    lay.write_verified(dev, lay.BOOT.start, image, "partition 1")
    log("Partition 1 written and verified.")
    return "written"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="make a new partition 1 image from a copy of the current one (Linux/WSL)")
    b.add_argument("base", type=Path)
    b.add_argument("output", type=Path)
    b.add_argument("--stage0", type=Path, required=True)
    b.add_argument("--payload", type=Path, required=True)
    b.add_argument("--boot-cmd", type=Path, default=Path(__file__).resolve().parent / "sd-boot-xnu-sdroot.cmd")
    w = sub.add_parser("write", help="write a partition 1 image to the card (Windows, admin)")
    w.add_argument("image", type=Path)
    w.add_argument("--expect-current", required=True, help="sha256 of partition 1 as it is on the card now")
    w.add_argument("--disk", type=int, default=1)
    w.add_argument("--expect-bytes", type=int, default=lay.CARD_BYTES)
    w.add_argument("--backup-dir", type=Path, default=Path.home() / "a733-card-backups")
    args = ap.parse_args()

    try:
        if args.cmd == "build":
            build(args.base, args.output, args.stage0, args.payload, args.boot_cmd)
            return 0
        if args.disk == 0:
            print("REFUSED: disk 0 is never touched.")
            return 2
        if os.name != "nt":
            print("REFUSED: write drives Windows disks (\\\\.\\PhysicalDriveN).")
            return 2
        image = args.image.read_bytes()
        check_ext4(image)
        info = lay.windows_disk_info(args.disk)
        problems = lay.check_disk(info, args.disk, args.expect_bytes)
        print(f"Disk {info.get('Number')}: {info.get('FriendlyName')}, {info.get('Size')} bytes, "
              f"{info.get('BusType')}, serial {info.get('SerialNumber')}, {info.get('PartitionStyle')}")
        if problems:
            print("REFUSED:\n  - " + "\n  - ".join(problems))
            return 2
        if not lay.is_admin():
            print("Disk checks passed. Writing needs an administrator terminal: Win+X -> Terminal (Admin).")
            return 1

        def recheck() -> None:
            if not lay.same_disk(lay.windows_disk_info(args.disk), info):
                raise lay.LayoutError("the disk changed (card removed or swapped?): stopping")

        dev = lay.Device(f"\\\\.\\PhysicalDrive{int(info['Number'])}", writable=True)
        try:
            write_boot(dev, info, image, args.expect_current, args.backup_dir,
                       lambda: lay.confirm_typed(info, "This overwrites partition 1 (boot partition) completely."),
                       recheck)
        finally:
            dev.close()
        print(lay.windows_rescan(args.disk))
    except (BootPartError, lay.LayoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"REFUSED / FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
