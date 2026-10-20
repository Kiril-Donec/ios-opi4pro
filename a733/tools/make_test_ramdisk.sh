#!/usr/bin/env bash
# A733 diagnostic ONLY: blank HFSX volume to prove XNU can mount md0.
# This does not contain iOS, launchd or a working userspace.
set -euo pipefail

out=${1:?usage: make_test_ramdisk.sh PATH/TO/a733-root-test.img}
if [[ -e "$out" ]]; then
  echo "Refusing to overwrite existing image: $out" >&2
  exit 1
fi
command -v mkfs.hfsplus >/dev/null || {
  echo "Install hfsprogs (Ubuntu: sudo apt install hfsprogs)" >&2
  exit 1
}
mkdir -p "$(dirname "$out")"
truncate -s 8M "$out"
mkfs.hfsplus -s -v A733RAM "$out"
# Check a raw HFS+ (HFSX, case-sensitive) volume header rather than trusting
# the mkfs exit code; this image is embedded unmodified inside the XNU payload.
python3 - "$out" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
with p.open("rb") as f:
    f.seek(1024)
    signature = f.read(2)
if p.stat().st_size != 8 * 1024 * 1024 or signature not in (b"H+", b"HX"):
    raise SystemExit("Invalid 8 MiB HFS+ test volume")
print(f"A733 diagnostic HFS+ RAM root: {p} (8 MiB), signature={signature!r}")
print("This has no /sbin/launchd: mounting the root, NOT booting iOS, is the test.")
PY
if command -v fsck.hfsplus >/dev/null; then
  fsck.hfsplus -fn "$out"
fi
