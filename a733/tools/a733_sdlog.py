#!/usr/bin/env python3
"""Console log file of the A733 XNU microSD driver (bsd/dev/a733_sdmmc.c).

The kernel writes everything printed on the HDMI console into A733LOG.TXT on
a FAT32 partition of the boot card, every few seconds and once more during a
panic. It only overwrites the file's existing sectors, so the file must exist
and be contiguous: create it once on a freshly formatted FAT32 partition.

  python a733_sdlog.py prepare E:        create E:\\A733LOG.TXT (64 MiB)
  python a733_sdlog.py show E:           print the log in order
  python a733_sdlog.py show E: -o log.txt
  python a733_sdlog.py clear E:          blank it again (same clusters)

E: is the drive letter Windows gives the FAT32 log partition (a directory or
the file path itself also works). Opening A733LOG.TXT in Notepad works too:
the newest text ends at the line "A733 LOG END".
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

NAME = "A733LOG.TXT"
SECTOR = 512
MARK = b"\n<<<<< A733 LOG END: newest line is above >>>>>\n"
DEFAULT_MIB = 64
CHUNK = 1 << 20
BLANK_SECTOR = b" " * (SECTOR - 1) + b"\n"
PREPARED = (b"A733 log file prepared by a733_sdlog.py. "
            b"The Orange Pi has not written to it yet.")


def log_path(target: str) -> Path:
    p = Path(target)
    if re.fullmatch(r"[A-Za-z]:", target):
        p = Path(target + "\\")
    if p.is_dir() or target.endswith(("\\", "/")):
        return p / NAME
    return p


def volume_fs(path: Path) -> str | None:
    """File system name of the volume holding path (Windows only)."""
    if os.name != "nt":
        return None
    import ctypes

    root = os.path.splitdrive(str(path.resolve()))[0] + "\\"
    name = ctypes.create_unicode_buffer(64)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(root), None, 0, None, None, None, name, len(name))
    return name.value if ok else None


def blank(f, size: int) -> None:
    header = PREPARED.ljust(SECTOR - 1) + b"\n"
    f.write(header)
    left = size - SECTOR
    block = BLANK_SECTOR * (CHUNK // SECTOR)
    while left > 0:
        n = min(left, len(block))
        f.write(block[:n])
        left -= n
    f.flush()
    os.fsync(f.fileno())


def prepare(path: Path, mib: int, force: bool) -> None:
    if mib < 1 or mib > 1024:
        raise SystemExit("size must be 1..1024 MiB")
    fs = volume_fs(path)
    if fs is not None and fs.upper() != "FAT32":
        raise SystemExit(f"{path.parent} is {fs}, not FAT32: the kernel only reads FAT32")
    if path.exists():
        if not force:
            raise SystemExit(f"{path} already exists (use clear, or prepare --force to recreate it)")
        path.unlink()
    # One sequential write on a fresh FAT32 volume gives one contiguous run
    # of clusters, which the kernel requires (it never follows the FAT).
    with path.open("wb") as f:
        blank(f, mib << 20)
    print(f"Created {path}: {mib} MiB. Safely eject the card before moving it to the board.")


def clear(path: Path) -> None:
    size = path.stat().st_size
    with path.open("r+b") as f:     # overwrite in place: keeps the same clusters
        blank(f, size - size % SECTOR)
    print(f"Cleared {path} ({size >> 20} MiB)")


def extract(data: bytes) -> tuple[str, list[str]]:
    """Console text in chronological order, plus notes about its state."""
    header, body = data[:SECTOR], data[SECTOR:]
    body = body[:len(body) - len(body) % SECTOR]
    notes: list[str] = []
    if header.startswith(PREPARED):
        return "", ["The board has not written to this file yet."]
    m = re.search(rb"(\d+) bytes logged since boot", header)
    if not m or not body:
        return "", ["No A733 log header: not written by the kernel, or a damaged file."]
    total = int(m.group(1))
    size = len(body)
    if b"LOST" in header:
        notes.append("Some console output was lost: more than 4 MiB between two writes.")
    # Log byte n is at body offset n % size; the kernel puts MARK right after
    # the newest byte and cuts it at the end of the file (it never wraps).
    end = total % size if total > size else total
    expected = MARK[:max(0, min(len(MARK), size - end))]
    if body[end:end + len(expected)] != expected:
        notes.append("End marker missing: the last write may have been interrupted.")
    if total <= size:
        text = body[:total]
    else:
        # The rest of the marker's sector is space padding; the previous lap
        # of the file continues at the next sector boundary.
        resume = -(-(end + len(MARK)) // SECTOR) * SECTOR
        older = body[resume:] if end + len(MARK) <= size else b""
        text = older + body[:end]
        notes.append(f"The file wrapped: showing the last {len(text) >> 10} KiB of {total >> 10} KiB.")
    return text.decode("utf-8", "replace"), notes


def show(path: Path, out: Path | None) -> None:
    text, notes = extract(path.read_bytes())
    for n in notes:
        print("NOTE:", n, file=sys.stderr)
    if out:
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {len(text)} characters to {out}", file=sys.stderr)
    else:
        sys.stdout.buffer.write(text.encode("utf-8", "replace"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="create the log file on the FAT32 partition")
    p.add_argument("target")
    p.add_argument("--size-mib", type=int, default=DEFAULT_MIB)
    p.add_argument("--force", action="store_true", help="delete and recreate an existing file")
    s = sub.add_parser("show", help="print the console log in order")
    s.add_argument("target")
    s.add_argument("-o", "--output", type=Path)
    c = sub.add_parser("clear", help="blank the log file in place")
    c.add_argument("target")
    a = ap.parse_args()
    path = log_path(a.target)
    if a.cmd == "prepare":
        prepare(path, a.size_mib, a.force)
    elif a.cmd == "show":
        show(path, a.output)
    else:
        clear(path)


if __name__ == "__main__":
    main()
