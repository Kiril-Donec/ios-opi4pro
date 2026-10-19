#!/usr/bin/env python3
"""Clone verified v3 SD image into NEW automatic PSCI A76-probe SD image.

Never opens a real block device. Retains the first 32 MiB verbatim (v59
bootloader) and changes only files inside the image's private ext4 copy.
"""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import json
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from arm64_header import validate_arm64  # noqa: E402
from package_sd import debugfs  # noqa: E402
from uimage_format import validate, script_image  # noqa: E402

BASE = ROOT / "build/ios-a733-stage0-auto-v3-sd.img"
OUT = ROOT.parent / "ios-a733-v4-a76-probe-sd-20261019.img"
FIRMWARE_ZIP = ROOT.parent / "upload/OrangePi4Pro-EDK2-v59-and-DeviceTree-20261019.zip"
BOARD_DT = "DeviceTree/sun60i-a733-orangepi-4-pro.dtb"
BASE_SHA256 = "6b461666e2bf37b976f641cff09d08229ab6a0dd032f3c25cc76167fe901acb3"


def build(out: Path = OUT) -> dict:
    if out.exists():
        raise ValueError("Output exists, refusing to replace an existing image")
    original = BASE.read_bytes()
    if sha256(original).hexdigest() != BASE_SHA256:
        raise ValueError("This is not the known working v3 base image")
    if len(original) != 64 * 1024 * 1024 or original[510:512] != b"\x55\xaa":
        raise ValueError("Unexpected v59 SD layout")
    entry = original[446:462]
    start, sectors = struct.unpack_from("<II", entry, 8)
    if entry[4] != 0x83 or (start, sectors) != (65536, 65536):
        raise ValueError("Unknown ext4 partition position")
    offset = start * 512

    kernel = (ROOT / "build/stage0.uimg").read_bytes()
    validate(kernel, 2)
    validate_arm64(kernel[64:])
    command = (ROOT / "tools/sd-boot-a76-probe.cmd").read_bytes()
    script = script_image(command, "A733 v4 AUTO A76 CPU_ON")
    validate(script, 6)
    with ZipFile(FIRMWARE_ZIP) as zipfile:
        dtb = zipfile.read(BOARD_DT)
    if struct.unpack_from(">I", dtb)[0] != 0xD00DFEED:
        raise ValueError("Invalid v59 FDT")

    paths = {
        "/boot.cmd": command,
        "/boot.scr": script,
        "/ios-a733/stage0-v4.uimg": kernel,
        "/dtb/allwinner/sun60i-a733-orangepi-4-pro.dtb": dtb,
    }
    with TemporaryDirectory(prefix="a733-a76-sd-") as directory:
        temp = Path(directory)
        partition = temp / "partition.ext4"
        partition.write_bytes(original[offset:])
        for n, (name, data) in enumerate(paths.items()):
            source = temp / f"new-{n}"
            source.write_bytes(data)
            try:
                debugfs(partition, f"rm {name}")
            except RuntimeError as error:
                if "file not found" not in str(error).lower():
                    raise
            debugfs(partition, f"write {source} {name}")
            roundtrip = temp / f"check-{n}"
            debugfs(partition, f"dump {name} {roundtrip}")
            if roundtrip.read_bytes() != data:
                raise ValueError(f"Readback differs for {name}")

        check = subprocess.run(["e2fsck", "-fn", str(partition)],
                               text=True, capture_output=True)
        if check.returncode:
            raise RuntimeError(f"ext4 corruption: {check.stdout}\n{check.stderr}")
        image = original[:offset] + partition.read_bytes()
        if image[:offset] != original[:offset] or len(image) != len(original):
            raise ValueError("Bootloader bytes or image size changed")
        out.write_bytes(image)

    info = {
        "image": out.name,
        "bytes": len(image),
        "sha256": sha256(image).hexdigest(),
        "v3_original_unchanged": sha256(BASE.read_bytes()).hexdigest() == BASE_SHA256,
        "bootloader_first_32MiB_preserved": True,
        "ext4_e2fsck": "PASS",
        "verified_files": list(paths),
        "hardware_tested": False,
        "xnu_included": False,
        "automatic_a76_psci_probe": True,
    }
    out.with_suffix(".json").write_text(json.dumps(info, indent=2) + "\n")
    out.with_suffix(".sha256").write_text(f"{info['sha256']}  {out.name}\n")
    return info


if __name__ == "__main__":
    if len(sys.argv) > 2:
        raise SystemExit("Usage: package_a76_sd.py [new-image-path]")
    target = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else OUT
    print(json.dumps(build(target), indent=2))
