#!/usr/bin/env python3
"""Reject Xiaomi/Qualcomm XNU binaries before producing an A733 SD image.

Checks distinctive compiled startup instructions and essential embedded
CPU/IOKit strings. It is an audit of the first-boot port, not proof that
the binary runs correctly on Allwinner hardware.
"""

import argparse
import struct
from pathlib import Path

LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x02


def word_movk_x0(value: int, shift: int) -> int:
    """Encode `movk x0, #value, lsl #shift` (AArch64)."""
    assert shift in (0, 16, 32, 48)
    return 0xF2800000 | (shift // 16 << 21) | (value << 5)


def find_start_offset(buf: bytes) -> int:
    if len(buf) < 32 or struct.unpack_from("<I", buf)[0] != 0xFEEDFACF:
        raise ValueError("not an arm64 Mach-O (little endian)")
    _, cpu, _, _, ncmds, cmdbytes, _, _ = struct.unpack_from("<8I", buf)
    if cpu != 0x0100000C or ncmds == 0 or ncmds > 256 or 32 + cmdbytes > len(buf):
        raise ValueError("invalid arm64 Mach-O header")
    segments = []
    symbols = None
    pos = 32
    endcmd = 32 + cmdbytes
    for _ in range(ncmds):
        if pos + 8 > endcmd:
            raise ValueError("truncated Mach-O commands")
        kind, size = struct.unpack_from("<II", buf, pos)
        if size < 8 or pos + size > endcmd:
            raise ValueError("invalid Mach-O command size")
        if kind == LC_SEGMENT_64 and size >= 72:
            va, vmbytes, off, filebytes = struct.unpack_from("<4Q", buf, pos + 24)
            if off + filebytes > len(buf):
                raise ValueError("segment outside Mach-O")
            segments.append((va, vmbytes, off, filebytes))
        if kind == LC_SYMTAB and size >= 24:
            symbols = struct.unpack_from("<4I", buf, pos + 8)
        pos += size

    if not symbols:
        raise ValueError("Mach-O has no symbol table: cannot verify start_first_cpu")
    symoff, nsyms, stroff, strsize = symbols
    if nsyms > 1000000 or symoff + 16 * nsyms > len(buf) or stroff + strsize > len(buf):
        raise ValueError("invalid Mach-O symbol table")
    for index in range(nsyms):
        nameoff, _, _, _, value = struct.unpack_from("<IBBHQ", buf, symoff + 16 * index)
        if nameoff >= strsize:
            continue
        start = stroff + nameoff
        if buf[start:start + 17] == b"_start_first_cpu\0":
            for va, _, offset, filebytes in segments:
                if va <= value and value + 64 <= va + filebytes:
                    return offset + value - va
            raise ValueError("start_first_cpu not in a file-backed segment")
    raise ValueError("cannot locate _start_first_cpu symbol")


def audit(buf: bytes) -> tuple[int, list[str]]:
    start = find_start_offset(buf)
    # The compiler's MOV64 macro emits four MOVKs at start_first_cpu+0x10.
    # In unmodified topaz these encode 0x9C9C1800 (Qualcomm framebuffer).
    first = struct.unpack_from("<8I", buf, start + 16)
    expected_address = 0xBBF11000 + 192 * 4096
    expected = tuple(word_movk_x0((expected_address >> shift) & 0xFFFF, shift)
                     for shift in (48, 32, 16, 0))
    errors = []
    # Early arm_init calls cpu_data_init(), which emits NEON on this XNU.
    # CPACR_EL1.FPEN enable MUST be followed by ISB on Cortex-A76 before it
    # can safely execute the compiler's MOVI/STP SIMD instructions.
    # These are little-endian AArch64 opcodes:
    #     msr CPACR_EL1, x0 ; isb
    neon_sync = struct.pack("<II", 0xD5181040, 0xD5033FDF)
    if neon_sync not in buf[start:start + 4096]:
        errors.append("early NEON enable missing ISB after MSR CPACR_EL1")
    if first[:4] != expected:
        errors.append("XNU boot marker still has a non-A733 framebuffer address")
    if first[6] != (0xD2800000 | (4096 << 5) | 4):
        errors.append("XNU boot marker stride is not 4096 bytes")
    for marker in (b"expected boot MPIDR 0x600", b"Cortex-A76", 
                   b"allwinner,a733", b"arm,cortex-a76",
                   b"A733 ARM64 ASYNC SError:",
                   b"A733 TRACE 03: interrupts enabled",
                   b"A733 TRACE 10: searching for root device",
                   b"A733 ROOT: IOFindBSDRoot entered"):
        if marker not in buf:
            errors.append("missing compiled A733 kernel identity: " + marker.decode())
    return start, errors


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("kernel", type=Path)
    args = ap.parse_args()
    try:
        offset, errors = audit(args.kernel.read_bytes())
    except (ValueError, struct.error) as exc:
        ap.exit(1, f"REJECT: {exc}\n")
    print(f"XNU _start_first_cpu file offset: 0x{offset:x}")
    if errors:
        for err in errors:
            print("REJECT:", err)
        ap.exit(1, "A733 kernel audit: FAIL (do not flash)\n")
    print("A733 first-boot XNU identity and early marker: PASS (static only)")


if __name__ == "__main__":
    main()
