#!/usr/bin/env python3
"""Preflight REAL Apple iPhone X iOS 16 files for the A733 RAM-root experiment.

Input is an already assembled/mounted iPhone X root (e.g. from ios-topaz
mkiosroot.sh with OS + SystemOS + AppOS Cryptexes). Does NOT download Apple
copyrighted files, patch binaries, or pretend to boot SpringBoard.

Usage:
    python3 a733/tools/inspect_ios16_root.py /mnt/iosroot --json report.json
    python3 a733/tools/inspect_ios16_root.py /mnt/iosroot --stage staging

--stage copies ONLY a diagnostic set (real launchd, dyld, dyld shared cache,
launchd.plist) to a new directory. This is NOT a complete iOS root; full
launchd needs many more frameworks, daemons and writable system directories.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import struct
import sys

MIB = 1024 * 1024
CURRENT_MD0_LIMIT = 16 * MIB
CURRENT_PAYLOAD_LIMIT = 128 * MIB
CURRENT_AUTOBOOT_IMAGE = 64 * MIB
# Real CI-built v20 with 8-MiB md0, not a theoretical kernel estimate.
V20_PAYLOAD_BYTES = 25471696
V20_TEST_ROOT_BYTES = 8 * MIB
REQUIRED = {
    "launchd": "sbin/launchd",
    "dyld": "usr/lib/dyld",
    "launchd_plist": "System/Library/xpc/launchd.plist",
}
CACHE_DIR = "System/Library/Caches/com.apple.dyld"
CACHE_RE = re.compile(r"dyld_shared_cache_arm64(?:[.]\d+)?$")
ARM64 = 0x0100000C
MH_MAGIC_64 = 0xFEEDFACF
LC_LOAD_DYLINKER = 0x0E
LC_CODE_SIGNATURE = 0x1D


def inspect_macho(path: Path) -> dict:
    """Inspect a Mach-O header without executing or modifying Apple's code."""
    with path.open("rb") as f:
        head = f.read(32)
        if len(head) < 32:
            raise ValueError("Mach-O header truncated")
        magic, cpu, subtype, filetype, ncmds, sizeofcmds, flags, reserved = struct.unpack("<8I", head)
        if (magic, cpu) != (MH_MAGIC_64, ARM64):
            raise ValueError(f"not thin arm64 Mach-O: magic={magic:#x}, cpu={cpu:#x}")
        if ncmds > 4096 or sizeofcmds > 16 * MIB:
            raise ValueError("implausible Mach-O load command count/size")
        cmds = f.read(sizeofcmds)
        if len(cmds) != sizeofcmds:
            raise ValueError("truncated Mach-O load commands")
    offset = 0
    dylinker, signed = None, False
    for i in range(ncmds):
        if offset + 8 > len(cmds):
            raise ValueError(f"truncated command {i}")
        cmd, size = struct.unpack_from("<2I", cmds, offset)
        if size < 8 or offset + size > len(cmds):
            raise ValueError(f"invalid command size at {i}")
        if cmd == LC_LOAD_DYLINKER:
            if size < 12:
                raise ValueError("bad LC_LOAD_DYLINKER")
            string_offset, = struct.unpack_from("<I", cmds, offset + 8)
            if string_offset < 12 or string_offset >= size:
                raise ValueError("invalid dylinker path offset")
            dylinker = cmds[offset + string_offset:offset + size].split(b"\0")[0].decode("utf-8", "replace")
        if cmd == LC_CODE_SIGNATURE:
            signed = True
        offset += size
    if offset != len(cmds):
        raise ValueError("Mach-O load commands do not consume sizeofcmds")
    return {"arm64": True, "filetype": filetype, "dylinker": dylinker,
            "has_code_signature_command": signed}


def within_root(root: Path, relative: str) -> Path:
    """Never stage a symlink that resolves outside the supplied root."""
    p = root / relative
    resolved = p.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(f"path escapes root: {relative}") from None
    if not resolved.is_file():
        raise ValueError(f"not a regular file: {relative}")
    return resolved


def analyze(root: Path) -> tuple[dict, list[tuple[str, Path]]]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("root is not a directory")
    result: dict = {"source": str(root), "kind": "REAL Apple iOS userland preflight",
                    "v20_md0_cap_bytes": CURRENT_MD0_LIMIT,
                    "v20_payload_cap_bytes": CURRENT_PAYLOAD_LIMIT,
                    "v20_autoboot_size_bytes": CURRENT_AUTOBOOT_IMAGE,
                    "files": {}, "errors": [], "warnings": []}
    paths: list[tuple[str, Path]] = []
    for key, relative in REQUIRED.items():
        try:
            p = within_root(root, relative)
            entry: dict = {"path": relative, "size_bytes": p.stat().st_size}
            if key in ("launchd", "dyld"):
                entry["macho"] = inspect_macho(p)
            if key == "launchd_plist":
                with p.open("rb") as f:
                    data = plistlib.load(f)
                if not isinstance(data, dict) or "LaunchDaemons" not in data:
                    raise ValueError("launchd.plist has no LaunchDaemons dictionary")
                entry["launchd_job_count"] = len(data["LaunchDaemons"])
            paths.append((relative, p))
            result["files"][key] = entry
        except (FileNotFoundError, ValueError, OSError, plistlib.InvalidFileException) as exc:
            result["errors"].append(f"{relative}: {exc}")

    version = root / "System/Library/CoreServices/SystemVersion.plist"
    if version.is_file():
        try:
            with version.open("rb") as f:
                info = plistlib.load(f)
            result["ios_version"] = str(info.get("ProductVersion", "unknown"))
            result["build_version"] = str(info.get("ProductBuildVersion", "unknown"))
            if not result["ios_version"].startswith("16."):
                result["errors"].append("not an iOS 16 system root")
        except (OSError, ValueError, plistlib.InvalidFileException) as exc:
            result["warnings"].append(f"cannot read SystemVersion.plist: {exc}")
    else:
        result["warnings"].append("SystemVersion.plist missing; version not independently verified")

    cache = root / CACHE_DIR
    selected = []
    if cache.is_dir():
        selected = sorted(p.name for p in cache.iterdir() if CACHE_RE.fullmatch(p.name))
    if not selected or "dyld_shared_cache_arm64" not in selected:
        result["errors"].append("missing arm64 dyld shared cache; mount/include SystemOS Cryptex")
    else:
        for name in selected:
            rel = f"{CACHE_DIR}/{name}"
            try:
                p = within_root(root, rel)
                paths.append((rel, p))
                result["files"][name] = {"path": rel, "size_bytes": p.stat().st_size}
            except (FileNotFoundError, ValueError, OSError) as exc:
                result["errors"].append(f"{rel}: {exc}")

    size = sum(p.stat().st_size for _, p in paths)
    result["diagnostic_file_bytes"] = size
    result["estimated_payload_bytes"] = V20_PAYLOAD_BYTES - V20_TEST_ROOT_BYTES + size
    result["fits_existing_16mib_md0"] = size <= CURRENT_MD0_LIMIT
    result["fits_existing_128mib_payload"] = result["estimated_payload_bytes"] <= CURRENT_PAYLOAD_LIMIT
    result["complete_root"] = False  # deliberate; this is just the probe set
    if size > CURRENT_MD0_LIMIT:
        result["warnings"].append("real Apple files exceed current 16-MiB md0 guard; a larger root design is required")
    if not result["fits_existing_128mib_payload"]:
        result["warnings"].append("real Apple files exceed current 128-MiB Stage0 payload limit")
    if any(x.endswith("arm64e") for x in result["files"]):
        result["warnings"].append("arm64e cache is not a substitute for arm64 on this kernel")
    if result["files"].get("launchd", {}).get("macho", {}).get("dylinker") not in (None, "/usr/lib/dyld"):
        result["warnings"].append("launchd references a nonstandard dynamic loader path")
    return result, paths


def stage_files(destination: Path, paths: list[tuple[str, Path]]) -> list[dict]:
    """Copy selected originals without rewriting signatures or guessing deps."""
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    destination.mkdir(parents=True)
    manifest = []
    for relative, source in paths:
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, output, follow_symlinks=True)
        with output.open("rb") as f:
            digest = hashlib.sha256()
            for chunk in iter(lambda: f.read(MIB), b""):
                digest.update(chunk)
        manifest.append({"path": relative, "size_bytes": output.stat().st_size,
                         "sha256": digest.hexdigest()})
    (destination / "A733_PROBE_NOT_A_COMPLETE_IOS_ROOT.txt").write_text(
        "Real, unmodified Apple binaries: diagnostic-only probe.\n"
        "NOT a bootable iOS root; missing other daemons, frameworks, writable dirs and services.\n"
        "Do not replace the hardware-tested A733 v20 RAM disk with this directory.\n"
    )
    (destination / "a733-probe-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", type=Path, help="mounted/assembled genuine iPhone X iOS 16 HFS+ root")
    ap.add_argument("--json", type=Path, help="write machine-readable size and dependency preflight")
    ap.add_argument("--stage", type=Path, help="copy diagnostic subset; NOT a bootable HFS+ image")
    args = ap.parse_args()
    try:
        result, paths = analyze(args.root)
        if args.stage is not None and not result["errors"]:
            result["staged_manifest"] = stage_files(args.stage, paths)
    except (ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    if args.json:
        args.json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
