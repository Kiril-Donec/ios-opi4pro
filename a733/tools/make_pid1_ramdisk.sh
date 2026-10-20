#!/usr/bin/env bash
# Experimental Darwin userspace bring-up: HFSX md0 with a static ARM64 PID1.
# No Apple iOS userland is included. Requires sudo / loop mount on Linux.
set -euo pipefail

if (( $# != 3 )); then
  echo "usage: bash $0 STATIC_ARM64_MACHO ROOT.img LABEL" >&2
  exit 2
fi
init=$(realpath "$1")
out=$2
label=$3

case "$label" in
  ''|*[!A-Za-z0-9]*) echo "label should contain only alphanumeric characters" >&2; exit 2;;
esac
[[ ! -e "$out" ]] || { echo "refusing to overwrite: $out" >&2; exit 1; }
[[ -s "$init" ]] || { echo "missing init binary: $init" >&2; exit 1; }
command -v mkfs.hfsplus >/dev/null || { echo "hfsprogs missing" >&2; exit 1; }

work=$(mktemp -d)
mounted=0
cleanup() {
  if [[ $mounted == 1 ]]; then
    sudo umount "$work" || { echo "ERROR: RAM image still mounted at $work" >&2; return 1; }
  fi
  rmdir "$work"
}
trap cleanup EXIT

mkdir -p "$(dirname "$out")"
truncate -s 8M "$out"
mkfs.hfsplus -s -v "$label" "$out"
sudo mount -t hfsplus -o loop,force,rw "$out" "$work"
mounted=1

# devfs_kernel_mount("/dev") returned ENOENT on v11. The directory is
# mandatory even for this tiny root. Never fake /dev/console as a disk file:
# XNU will mount devfs on /dev and publish it itself.
sudo install -d -m 0755 "$work"/{sbin,dev,private,var,tmp,usr}
sudo install -m 0755 "$init" "$work/sbin/launchd"

# Read back the executable before unmounting: Linux HFS+ needs to preserve
# executable mode and content. Mach-O is a static, ad-hoc signed test binary.
sudo test -x "$work/sbin/launchd"
sudo test -d "$work/dev"
sudo cmp "$init" "$work/sbin/launchd"
sync
sudo umount "$work"
mounted=0

python3 - "$out" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
with p.open("rb") as f:
    f.seek(1024)
    sig = f.read(2)
assert p.stat().st_size == 8 * 1024 * 1024
assert sig in (b"H+", b"HX"), f"invalid HFSX signature: {sig!r}"
print(f"PASS A733 PID1 HFS root: {p} ({p.stat().st_size} B, {sig!r})")
print("PID1 is a temporary static test executable, NOT Apple's launchd.")
PY
if command -v fsck.hfsplus >/dev/null; then
  fsck.hfsplus -fn "$out"
fi
