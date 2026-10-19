#!/usr/bin/env python3
"""Build a handoff-only SD test ZIP from the *cross-built* v4 uImage.

Inputs are local project files plus the user's v59 DeviceTree upload.
The ZIP has no automatic boot script and cannot write or repartition an SD.
"""
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from arm64_header import validate_arm64  # noqa: E402
from uimage_format import script_image, validate  # noqa: E402

FIRMWARE_ZIP = ROOT.parent / "upload/OrangePi4Pro-EDK2-v59-and-DeviceTree-20261019.zip"
DT_IN_ARCHIVE = "DeviceTree/sun60i-a733-orangepi-4-pro.dtb"
OUT = ROOT.parent / "ios-a733-v4-a76-probe-20261019.zip"


def build(out: Path = OUT) -> Path:
    stage0 = (ROOT / "build/stage0.uimg").read_bytes()
    validate(stage0, 2)
    image_size = validate_arm64(stage0[64:])
    if image_size < len(stage0) - 64 or image_size > 0x100000:
        raise ValueError("Unexpected v4 ARM64 runtime image size")
    if b"XNU: STARTING A76" not in stage0 and b"PROBE: STARTING A76" not in stage0:
        raise ValueError("Image lacks the v4 CPU handoff diagnostic")

    source = (ROOT / "tools/sd-boot-a76-probe.cmd").read_bytes()
    forbidden = (b"xnu.payload", b"mmc write", b"saveenv", b"ext4write", b"fatwrite")
    if any(op in source.lower() for op in forbidden):
        raise ValueError("Unsafe command detected in hardware probe")
    script = script_image(source, "A733 v4 A76 CPU_ON probe")
    validate(script, 6)

    with ZipFile(FIRMWARE_ZIP) as f:
        dtb = f.read(DT_IN_ARCHIVE)
    if len(dtb) < 40:
        raise ValueError("Device tree too small")
    magic, total = struct.unpack_from(">II", dtb)
    if magic != 0xD00DFEED or total > len(dtb) or total > 2 * 1024 * 1024:
        raise ValueError("Invalid v59 board DTB")

    files = {
        "ios-a733/stage0-v4.uimg": stage0,
        "ios-a733/a76-probe.scr": script,
        "dtb/allwinner/sun60i-a733-orangepi-4-pro.dtb": dtb,
        "TEST-A76-RU.md": (ROOT / "TEST-A76-RU.md").read_bytes(),
    }
    checksums = "".join(f"{sha256(data).hexdigest()}  {name}\n"
                        for name, data in files.items()).encode("ascii")
    files["SHA256SUMS"] = checksums
    with ZipFile(out, "w", compression=ZIP_DEFLATED) as f:
        for name, contents in files.items():
            f.writestr(name, contents)
    return out


if __name__ == "__main__":
    path = build()
    print(f"Ready for manual A76 CPU_ON test: {path}")
    print("Only A76 diagnostic; NO XNU Mach-O. No persistent SD modifications in U-Boot.")
