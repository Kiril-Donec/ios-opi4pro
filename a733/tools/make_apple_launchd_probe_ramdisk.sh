#!/usr/bin/env bash
# Create ONLY a 16-MiB first-exec diagnostic RAM-root using ORIGINAL Apple files.
# This is not a complete iOS root and cannot boot SpringBoard.
# Usage (as root): bash a733/tools/make_apple_launchd_probe_ramdisk.sh MOUNTED_IOS_ROOT OUT.hfs
set -euo pipefail

usage() {
  echo "Usage: sudo bash $0 /mnt/iosroot /root/ios-root-work/a733-apple-launchd-probe.hfs" >&2
  echo "This tests Apple launchd/dyld Mach-O loading ONLY; no shared cache, no working iOS." >&2
}
if [[ ${1:-} == '--help' || ${1:-} == '-h' ]]; then
  usage
  exit 0
fi
if (( $# != 2 )); then usage; exit 2; fi
if (( EUID != 0 )); then echo "ERROR: need root for HFSX loop mount" >&2; exit 2; fi
command -v mkfs.hfsplus >/dev/null || { echo "ERROR: install hfsprogs" >&2; exit 2; }
command -v mount >/dev/null || { echo "ERROR: mount missing" >&2; exit 2; }
command -v umount >/dev/null || { echo "ERROR: umount missing" >&2; exit 2; }

root=$(realpath -e -- "$1")
out=$(realpath -m -- "$2")
[[ -d "$root" ]] || { echo "ERROR: iOS root is not a directory" >&2; exit 2; }
[[ "$out" != "$root"/* ]] || { echo "ERROR: output must not be inside source iOS root" >&2; exit 2; }
[[ ! -e "$out" && ! -L "$out" ]] || { echo "ERROR: refusing overwrite $out" >&2; exit 2; }

# These are all original, individually checkable signed iOS binaries.
files=(
  sbin/launchd
  usr/lib/dyld
  usr/libexec/xpcproxy
  System/Library/xpc/launchd.plist
  System/Library/CoreServices/SystemVersion.plist
)
for f in "${files[@]}"; do
  [[ -f "$root/$f" && ! -L "$root/$f" ]] ||
    { echo "ERROR: expected original regular file is missing or a symlink: $f" >&2; exit 2; }
done

# Check actual Apple Mach-O header (arm64) before creating the image.
python3 - "$root" <<'PY'
import sys, struct
from pathlib import Path
r = Path(sys.argv[1])
for f in ("sbin/launchd", "usr/lib/dyld", "usr/libexec/xpcproxy"):
    with (r/f).open("rb") as src:
        header = src.read(32)
    if len(header) != 32 or struct.unpack_from("<II", header) != (0xfeedfacf, 0x0100000c):
        raise SystemExit(f"ERROR: not a thin arm64 Mach-O: {f}")
print("PASS: three original ARM64 Mach-O headers")
PY

mkdir -p -- "$(dirname "$out")"
mnt=$(mktemp -d)
mounted=0
created=0
cleanup() {
  rc=$?
  trap - EXIT
  if (( mounted )); then
    sync
    if ! umount "$mnt"; then
      echo "WARNING: HFSX mount still active at $mnt; preserving image" >&2
      exit 1
    fi
  fi
  rmdir "$mnt" || true
  if (( rc != 0 && created )); then rm -f -- "$out"; fi
  exit "$rc"
}
trap cleanup EXIT

# Create new file exclusively; refuse to touch any preexisting volume.
( set -C; : > "$out" ) || { echo "ERROR: cannot create output" >&2; exit 2; }
created=1
truncate -s 16M "$out"
mkfs.hfsplus -s -v A733APPLE "$out"
mount -t hfsplus -o loop,force,rw "$out" "$mnt"
mounted=1
install -d -m 0755 "$mnt/dev" "$mnt/private" "$mnt/private/var" \
  "$mnt/var" "$mnt/tmp" "$mnt/Library" "$mnt/System" "$mnt/usr" \
  "$mnt/usr/lib" "$mnt/usr/libexec" "$mnt/sbin"
for f in "${files[@]}"; do
  install -d -m 0755 "$mnt/$(dirname "$f")"
  cp --preserve=mode,ownership,timestamps -- "$root/$f" "$mnt/$f"
  cmp -- "$root/$f" "$mnt/$f"
done
test -x "$mnt/sbin/launchd"
test -x "$mnt/usr/lib/dyld"
test -d "$mnt/dev"
sync
umount "$mnt"
mounted=0
python3 - "$out" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
with p.open("rb") as f:
    f.seek(1024)
    header = f.read(2)
if p.stat().st_size != (16 << 20) or header not in (b"HX", b"H+"):
    raise SystemExit("FAIL: invalid 16MiB HFSX root")
print("PASS: 16MiB HFSX with genuine Apple binaries", p)
PY
if command -v fsck.hfsplus >/dev/null; then
  fsck.hfsplus -fn "$out"
fi
sha256sum -- "$out"
echo "IMPORTANT: Apple launchd will probably fail in dyld without its 2.55GiB shared cache."
echo "This is a first Mach-O/dyld exec diagnostic, NOT iOS or SpringBoard."
