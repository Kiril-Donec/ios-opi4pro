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
    _validate_ramdisk_args(cmdline, ramdisk)
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
    args = ap.parse_args()
    cmdline = args.cmdline
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
    print("Root:", "HFS+ RAM disk /dev/md0 (NO launchd/userland included)"
          if args.ramdisk else "no root volume supplied")
    print("Still NOT hardware-boot-verified. Do not flash automatically.")


if __name__ == "__main__":
    main()
