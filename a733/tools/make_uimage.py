#!/usr/bin/env python3
"""Minimal legacy U-Boot uImage packer, compatible with the v59 boot path."""
import argparse
import struct
import time
import zlib
from pathlib import Path

HEADER = ">7I4B32s"


def pack(payload: bytes, name: str, load: int) -> bytes:
    encoded = name.encode("ascii")
    if len(encoded) > 32:
        raise ValueError("uImage name too long")
    fields = (0x27051956, 0, int(time.time()), len(payload), load, load,
              zlib.crc32(payload) & 0xFFFFFFFF,
              5, 2, 2, 0, encoded.ljust(32, b"\0"))
    header = struct.pack(HEADER, *fields)
    crc = zlib.crc32(header) & 0xFFFFFFFF
    return header[:4] + struct.pack(">I", crc) + header[8:] + payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = args.input.read_bytes()
    args.output.write_bytes(pack(data, "ios-a733-stage0", 0x41000000))


if __name__ == "__main__":
    main()
