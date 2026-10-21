#!/usr/bin/env bash
# GUI-first genuine iOS16 root: create a separate 16-GiB HFS+ COPY and
# apply upstream launchd/Setup/activation adjustments to the COPY only.
# This does NOT boot SpringBoard by itself: XNU needs access to storage.
set -euo pipefail
usage() {
  echo "Usage: sudo bash $0 SOURCE-16G-HFS.img NEW-GUI-16G-HFS.img" >&2
}
if (( $# == 1 )) && [[ "$1" == --help || "$1" == -h ]]; then usage; exit 0; fi
if (( $# != 2 )); then usage; exit 2; fi
if (( EUID != 0 )); then echo "REFUSED: root/sudo required" >&2; exit 2; fi
for tool in cp python3 mount umount mountpoint fsck.hfsplus stat; do
  command -v "$tool" >/dev/null || { echo "REFUSED: missing $tool" >&2; exit 2; }
done
src=$(realpath -e -- "$1")
dst=$(realpath -m -- "$2")
[[ -f "$src" && ! -L "$src" && ! -b "$src" && ! -c "$src" ]] ||
  { echo "REFUSED: input must be a regular HFS+ file" >&2; exit 2; }
[[ "$src" != "$dst" && ! -e "$dst" && ! -L "$dst" ]] ||
  { echo "REFUSED: identical or existing destination" >&2; exit 2; }
[[ -d "$(dirname "$dst")" ]] || { echo "REFUSED: destination parent missing" >&2; exit 2; }
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
tweaks="$repo_root/tools/sweet-root-tweaks.py"
[[ -f "$tweaks" ]] || { echo "REFUSED: upstream tweaks unavailable" >&2; exit 2; }
size=$(stat -c %s -- "$src")
[[ "$size" == 17179869184 ]] || { echo "REFUSED: expected 16 GiB original root" >&2; exit 2; }
python3 - "$src" <<'PY'
from pathlib import Path
import sys
with Path(sys.argv[1]).open("rb") as f:
    f.seek(1024)
    if f.read(2) not in (b"H+", b"HX"):
        raise SystemExit("REFUSED: no raw HFS+ volume header")
PY
echo "Read-only check on original root:"
fsck.hfsplus -fn "$src"
echo "Copying full HFS+ image; source will NOT be mounted writable:"
cp --reflink=auto --sparse=always -- "$src" "$dst"
[[ $(stat -c %s -- "$dst") == "$size" ]] || { echo "INCOMPLETE CLONE" >&2; exit 1; }
mnt=$(mktemp -d)
mounted=0
cleanup() {
  rc=$?
  trap - EXIT
  if (( mounted )); then
    if ! umount "$mnt"; then
      echo "FAILED to unmount CLONE at $mnt; preserving mount" >&2
      exit 1
    fi
  fi
  rmdir "$mnt" || true
  if (( rc != 0 )); then echo "CLONE needs inspection: $dst" >&2; fi
  exit "$rc"
}
trap cleanup EXIT
mount -t hfsplus -o loop,force,rw "$dst" "$mnt"
mounted=1
[[ -f "$mnt/sbin/launchd" && -f "$mnt/usr/lib/dyld" &&
   -f "$mnt/System/Library/xpc/launchd.plist" ]] ||
  { echo "REFUSED: missing original Apple userland" >&2; exit 2; }
python3 "$tweaks" "$mnt"
sync
umount "$mnt"
mounted=0
fsck.hfsplus -fn "$dst"
echo "GUI-FIRST HFS+ COPY READY: $dst"
echo "Not an AutoBoot IMG. Storage driver and GUI service launch are NOT yet verified."
