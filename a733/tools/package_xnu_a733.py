#!/usr/bin/env python3
"""Pack ONLY an audited Allwinner A733 XNU kernel into the Stage0 payload.

The upstream Xiaomi mkpayload.py intentionally emits SWEETXNU. This wrapper
refuses kernels without our compiled A733 CPU/HDMI signatures, then changes the
8-byte payload magic to A733XNU1. Stage0 rejects legacy SWEETXNU payloads.
This is a static hardware identity check, not proof XNU boots on the board.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import struct
import sys

from audit_a733_macho import audit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import mkpayload  # noqa: E402

MAGIC = b"A733XNU1"
LEGACY = b"SWEETXNU"
PHYS_BASE = 0x100000000
MEM_SIZE = 0x40000000
MAX_BYTES = 128 * 1024 * 1024
RAMDISK_MAX_BYTES = 16 * 1024 * 1024
RAMDISK_TEST_BYTES = 8 * 1024 * 1024
# Development XNU filters kprintf unless -enable_kprintf_spam is supplied.
# serial=1 routes those logs to the A733 framebuffer-backed serial device.
# sweetfb_console=1 prevents a later graphics present from hiding diagnostics.
DEFAULT_CMDLINE = "debug=0xc cpus=1 keepsyms=1 -v modem=0 wifi=0 sweetbattery=0 sweetcpufreq=0 -enable_kprintf_spam serial=1 sweetfb_console=1"
# Root on the microSD card through bsd/dev/a733_sdmmc.c (read-only PIO).
# v22 showed that real Apple launchd needs unentitled_ios_sim_launch=1.
SDROOT_ARGS = "rd=sdroot0 unentitled_ios_sim_launch=1"
# Writable iOS root: the driver accepts root writes (sdrw=1) and XNU mounts
# / read-write (rootrw=1); launchd's mount-phase-1 needs it (board test #3).
SDRW_ARGS = "sdrw=1 rootrw=1"
# iOS userland on the writable root, as the upstream ios-sweet phone boots it:
# launchd_unsecure_cache=1 lets launchd_cache_loader skip the signature check
# and the AppleMobileFileIntegrity IOService ("abort: Unable to find AMFI",
# board test #4); ignition_level=1, wdt_test=no_user_checkin and wdt=-1
# as in the upstream boot-args.
USERLAND_ARGS = "launchd_unsecure_cache=1 ignition_level=1 wdt_test=no_user_checkin wdt=-1"
# The PID 1 kprintf traces of v14-v17 print several lines per copyinstr of
# launchd and slow the framebuffer console down; printf output (A733 SD,
# A733 TRACE, launchd via /dev/console) and the log file are unaffected.
NO_KPRINTF_SPAM = "-enable_kprintf_spam"
SDMMC_ADT_NODE = b"a733-sdmmc"


def _validate_sdroot_args(cmdline: str, ramdisk: Path | None, adt_bytes: bytes) -> None:
    """rd=sdroot0 needs the /a733-sdmmc ADT node, no RAM disk; rootrw=1 only with sdrw=1."""
    tokens = cmdline.split()
    rds = [t for t in tokens if t.startswith(("rd=", "rootdev="))]
    if "rd=sdroot0" not in rds:
        return
    if rds != ["rd=sdroot0"]:
        raise ValueError("microSD root requires exactly rd=sdroot0 and no other root device")
    if ramdisk is not None:
        raise ValueError("rd=sdroot0 boots from the card; do not add a RAM disk")
    if SDMMC_ADT_NODE not in adt_bytes:
        raise ValueError("rd=sdroot0 requires an ADT built with mkadt_a733.py --sdmmc")
    rootrw = any(t.startswith("rootrw=") and t != "rootrw=0" for t in tokens)
    sdrw = any(t.startswith("sdrw=") and t != "sdrw=0" for t in tokens)
    if rootrw != sdrw or (sdrw and "sdrw=1" not in tokens):
        raise ValueError("a writable root needs both sdrw=1 (driver) and rootrw=1 (mount), or neither")
    cpus = [t for t in tokens if t.startswith("cpus=")]
    if cpus == ["cpus=2"]:
        # Only the two Cortex-A76 cores; the second must be in the ADT (--a76-pair).
        if b"cpu1\x00" not in adt_bytes:
            raise ValueError("cpus=2 requires an ADT built with mkadt_a733.py --a76-pair")
    elif cpus != ["cpus=1"]:
        raise ValueError("A733 runs on the Cortex-A76 cores only: exactly cpus=1 or cpus=2 is required")


def _validate_ramdisk_args(cmdline: str, ramdisk: Path | None) -> None:
    """Refuse a fake md0 boot or conflicting storage arguments."""
    tokens = cmdline.split()
    rds = [t for t in tokens if t.startswith(("rd=", "rootdev="))]
    if ramdisk is None:
        if any(t in ("rd=md0", "rootdev=md0") for t in rds):
            raise ValueError("rd=md0 requires a RAM disk image")
        return
    if rds != ["rd=md0"]:
        raise ValueError("RAM disk boot requires exactly rd=md0 and no other root device")
    size = ramdisk.stat().st_size
    if not (4 * 1024 * 1024 <= size <= RAMDISK_MAX_BYTES):
        raise ValueError(f"RAM disk size must be 4..16 MiB (got {size} bytes)")
    if size % 0x4000:
        raise ValueError("RAM disk size must be 16 KiB aligned")
    with ramdisk.open("rb") as f:
        f.seek(1024)
        signature = f.read(2)
    if signature not in (b"H+", b"HX"):
        raise ValueError("RAM disk has no HFS+ / HFSX volume header at offset 1024")


def pack(kernel: Path, adt: Path, cmdline: str, ramdisk: Path | None = None) -> tuple[bytes, dict]:
    original = kernel.read_bytes()
    try:
        entry_offset, problems = audit(original)
    except (ValueError, struct.error) as exc:
        raise ValueError(f"A733 kernel audit failed: {exc}") from exc
    if problems:
        raise ValueError("A733 kernel audit failed: " + "; ".join(problems))
    # Xiaomi/Qualcomm MMIO is not valid on the Allwinner A733. Even the
    # battery personality can touch Qualcomm QUP/I2C and cpufreq registers.
    # Require explicit off switches in EVERY first-boot payload.
    tokens = set(cmdline.split())
    required_off = {"modem=0", "wifi=0", "sweetbattery=0", "sweetcpufreq=0"}
    if not required_off.issubset(tokens) or any(
        token.startswith(key + "=") and token != key + "=0"
        for token in tokens
        for key in ("modem", "wifi", "sweetbattery", "sweetcpufreq")
    ):
        raise ValueError("A733 first boot requires Qualcomm modem, Wi-Fi, battery I2C and cpufreq disabled")
    # mkpayload silently truncates cmdline[608]; a lost rd= would boot the wrong root.
    if len(cmdline.encode()) >= mkpayload.BOOT_LINE_LENGTH:
        raise ValueError(f"cmdline too long for the payload header ({len(cmdline.encode())} bytes)")
    _validate_ramdisk_args(cmdline, ramdisk)
    _validate_sdroot_args(cmdline, ramdisk, adt.read_bytes())
    data, meta = mkpayload.build(str(kernel), str(adt), cmdline,
                                 str(ramdisk) if ramdisk else None)
    if not data.startswith(LEGACY):
        raise ValueError("upstream payload format changed")
    phys, mem = struct.unpack_from("<2Q", data, 0x38)
    if (phys, mem) != (PHYS_BASE, MEM_SIZE):
        raise ValueError(f"unexpected ADT RAM map: {phys:#x}+{mem:#x}")
    if len(data) > MAX_BYTES:
        raise ValueError(f"payload too large: {len(data)}")
    data = MAGIC + data[8:]
    assert data[:8] == MAGIC
    meta["a733_audited_start_offset"] = hex(entry_offset)
    return data, meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("kernel", type=Path, help="macOS CI-built kernel.development.sweet")
    ap.add_argument("adt", type=Path, help="A733-specific Apple Device Tree")
    ap.add_argument("output", type=Path)
    ap.add_argument("--cmdline", default=DEFAULT_CMDLINE)
    ap.add_argument("--ramdisk", type=Path, help="4..16 MiB HFS+ test image; sets rd=md0 if no --cmdline")
    ap.add_argument("--sdroot", action="store_true",
                    help=f"root on the microSD card partition (adds '{SDROOT_ARGS}')")
    ap.add_argument("--cpus", type=int, choices=(1, 2), default=1,
                    help="with --sdroot: Cortex-A76 cores to use (2 needs an ADT from mkadt_a733.py --a76-pair)")
    ap.add_argument("--sdrw", action="store_true",
                    help=f"with --sdroot: writable iOS root for launchd (adds '{SDRW_ARGS} {USERLAND_ARGS}', drops {NO_KPRINTF_SPAM})")
    args = ap.parse_args()
    cmdline = args.cmdline
    if args.sdroot:
        if args.ramdisk is not None:
            ap.exit(1, "REFUSED: --sdroot and --ramdisk are exclusive\n")
        cmdline += " " + SDROOT_ARGS
        if args.sdrw:
            cmdline += " " + SDRW_ARGS + " " + USERLAND_ARGS
            cmdline = " ".join(t for t in cmdline.split() if t != NO_KPRINTF_SPAM)
        if args.cpus != 1:
            cmdline = " ".join(f"cpus={args.cpus}" if t.startswith("cpus=") else t for t in cmdline.split())
    elif args.sdrw or args.cpus != 1:
        ap.exit(1, "REFUSED: --sdrw and --cpus need --sdroot\n")
    if args.ramdisk is not None and not any(
        t.startswith(("rd=", "rootdev=")) for t in cmdline.split()
    ):
        cmdline += " rd=md0"
    try:
        result, meta = pack(args.kernel, args.adt, cmdline, args.ramdisk)
    except (ValueError, AssertionError, OSError) as exc:
        ap.exit(1, f"REFUSED: {exc}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result)
    digest = hashlib.sha256(result).hexdigest()
    checksum = args.output.with_name(args.output.name + ".sha256")
    checksum.write_text(f"{digest}  {args.output.name}\n")
    print("A733-only audited payload:", args.output, len(result), "bytes")
    print("SHA256:", digest)
    print("Kernel start offset:", meta["a733_audited_start_offset"])
    if args.ramdisk:
        root = "HFS+ RAM disk /dev/md0 (NO launchd/userland included)"
    elif "rd=sdroot0" in cmdline.split():
        mode = "READ-WRITE" if "sdrw=1" in cmdline.split() else "read-only"
        root = f"microSD partition via SMHC0 PIO driver, rd=sdroot0 ({mode})"
    else:
        root = "no root volume supplied"
    print("Root:", root)
    print("Still NOT hardware-boot-verified. Do not flash automatically.")


if __name__ == "__main__":
    main()
