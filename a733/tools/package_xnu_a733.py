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
DEFAULT_CMDLINE = "debug=0xc cpus=1 keepsyms=1 -v modem=0 wifi=0"


def pack(kernel: Path, adt: Path, cmdline: str) -> tuple[bytes, dict]:
    original = kernel.read_bytes()
    try:
        entry_offset, problems = audit(original)
    except (ValueError, struct.error) as exc:
        raise ValueError(f"A733 kernel audit failed: {exc}") from exc
    if problems:
        raise ValueError("A733 kernel audit failed: " + "; ".join(problems))
    if "modem=1" in cmdline or "wifi=1" in cmdline:
        raise ValueError("Qualcomm modem=1/wifi=1 boot args are forbidden on A733")
    data, meta = mkpayload.build(str(kernel), str(adt), cmdline)
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
    args = ap.parse_args()
    try:
        result, meta = pack(args.kernel, args.adt, args.cmdline)
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
    print("Still NOT hardware-boot-verified. Do not flash automatically.")


if __name__ == "__main__":
    main()
