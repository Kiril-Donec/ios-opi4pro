#!/usr/bin/env python3
"""Locate the genuine OS, SystemOS and AppOS images in an iPhone X iOS16 IPSW.

Uses Apple's BuildManifest.plist for D22AP Erase, NOT filename guessing.
Default: report metadata only. Optional --extract DIR copies just these three
original DMGs (can use many GiB). Does not decrypt, patch, mount or flash.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import plistlib
import shutil
import sys
import zipfile

COMPONENTS = ("OS", "SystemOS", "AppOS")
TARGET_CLASS = "d22ap"


def select_components(zf: zipfile.ZipFile) -> dict[str, str]:
    try:
        manifest = plistlib.loads(zf.read("BuildManifest.plist"))
    except KeyError:
        raise ValueError("IPSW lacks BuildManifest.plist") from None
    if not isinstance(manifest, dict):
        raise ValueError("invalid BuildManifest.plist")
    identities = manifest.get("BuildIdentities", [])
    candidates = []
    for entry in identities:
        info = entry.get("Info", {})
        if not isinstance(info, dict) or str(info.get("DeviceClass", "")).lower() != TARGET_CLASS:
            continue
        available = entry.get("Manifest", {})
        if not all(k in available for k in COMPONENTS):
            continue
        paths = {}
        for key in COMPONENTS:
            record = available[key]
            if not isinstance(record, dict):
                break
            path = record.get("Info", {}).get("Path")
            if not isinstance(path, str) or not path:
                break
            # Do not accept traversal or ambiguous names, including ../ or /.
            p = PurePosixPath(path)
            if p.is_absolute() or ".." in p.parts or str(p) != path:
                raise ValueError(f"unsafe {key} archive path: {path!r}")
            if not path.endswith(".dmg"):
                raise ValueError(f"{key} is not a DMG: {path!r}")
            paths[key] = path
        if len(paths) != len(COMPONENTS):
            continue
        if not all(path in zf.namelist() for path in paths.values()):
            continue
        behavior = str(info.get("RestoreBehavior", "")).lower()
        variant = str(info.get("Variant", "")).lower()
        is_erase = "erase" in behavior or "erase" in variant
        candidates.append((is_erase, paths))
    if not candidates:
        raise ValueError("no complete D22AP (iPhone10,3) identity with OS/SystemOS/AppOS DMGs")
    candidates.sort(key=lambda x: x[0], reverse=True)
    if not candidates[0][0]:
        raise ValueError("no D22AP Erase restore identity found; refusing an arbitrary identity")
    chosen = candidates[0][1]
    if sum(1 for flag, paths in candidates if flag and paths != chosen):
        raise ValueError("ambiguous D22AP Erase identities with different image paths")
    return chosen


def examine(ipsw: Path) -> tuple[dict, dict[str, str]]:
    with zipfile.ZipFile(ipsw) as zf:
        paths = select_components(zf)
        report = {"ipsw": ipsw.name, "device": "iPhone10,3 / D22AP",
                  "identity": "Erase", "components": {}}
        for key, path in paths.items():
            meta = zf.getinfo(path)
            if meta.is_dir():
                raise ValueError(f"{key} path is a directory")
            report["components"][key] = {"archive_path": path,
                "file_bytes": meta.file_size, "compressed_bytes": meta.compress_size}
        report["total_uncompressed_bytes"] = sum(
            v["file_bytes"] for v in report["components"].values())
        return report, paths


def extract(ipsw: Path, destination: Path, paths: dict[str, str]) -> dict[str, str]:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing directory {destination}")
    destination.mkdir(parents=True)
    hashes = {}
    with zipfile.ZipFile(ipsw) as zf:
        for key, path in paths.items():
            dst = destination / f"{key}.dmg"
            sha = hashlib.sha256()
            with zf.open(path) as source, dst.open("xb") as output:
                while True:
                    block = source.read(1 << 20)
                    if not block:
                        break
                    sha.update(block)
                    output.write(block)
            hashes[key] = sha.hexdigest()
    return hashes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ipsw", type=Path, help="original iPhone X iOS16.7.16 Apple IPSW file")
    ap.add_argument("--extract", type=Path, help="extract OS.dmg SystemOS.dmg AppOS.dmg to NEW directory")
    ap.add_argument("--json", type=Path, help="save a size report without proprietary binary data")
    a = ap.parse_args()
    try:
        report, paths = examine(a.ipsw)
        if a.extract:
            report["extracted_sha256"] = extract(a.ipsw, a.extract, paths)
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    if a.json:
        a.json.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
