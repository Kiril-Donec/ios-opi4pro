#!/usr/bin/env bash
# Make a RAW, 8-MiB, HFSX RAM-root image with a signed static PID1 on macOS.
# The Ubuntu CI runner cannot mount hfsplus; hdiutil is available on macOS.
# Not a real iOS filesystem. No device is flashed or modified here.
set -euo pipefail
if (( $# != 3 )); then
  echo "usage: bash $0 STATIC_ARM64_MACHO ROOT.hfs VOLUME_LABEL" >&2
  exit 2
fi
init=$1; out=$2; label=$3
case "$label" in
  ''|*[!A-Za-z0-9]*) echo "label must be alphanumeric" >&2; exit 2;;
esac
test -s "$init" || { echo "missing PID1 binary: $init" >&2; exit 1; }
test ! -e "$out" || { echo "refusing to overwrite: $out" >&2; exit 1; }
mkdir -p "$(dirname "$out")"
work=$(mktemp -d)
mounted=0
cleanup() {
  if (( mounted )); then
    hdiutil detach -quiet "$work/mnt" || hdiutil detach -quiet -force "$work/mnt" || true
  fi
  rm -rf "$work"
}
trap cleanup EXIT
mkdir -p "$work/mnt"
# UDRW contains RAW disk data first, then the UDIF trailer. -layout NONE
# deliberately omits a partition map so HFSX starts at byte zero.
hdiutil create -quiet -ov -size 8m -fs HFSX -layout NONE \
  -volname "$label" -format UDRW -o "$work/root.dmg"
hdiutil attach -quiet -nobrowse -mountpoint "$work/mnt" "$work/root.dmg"
mounted=1
mkdir -p "$work/mnt/sbin" "$work/mnt/dev" "$work/mnt/private" "$work/mnt/var" "$work/mnt/tmp" "$work/mnt/usr"
cp "$init" "$work/mnt/sbin/launchd"
chmod 0755 "$work/mnt/sbin/launchd"
cmp "$init" "$work/mnt/sbin/launchd"
test -d "$work/mnt/dev"
test -x "$work/mnt/sbin/launchd"
sync
hdiutil detach -quiet "$work/mnt"
mounted=0
# UDRW .dmg is raw disk data followed by the UDIF trailer. Do not put
# that trailer inside the A733XNU1 segment: it expects a raw HFS+ volume.
python3 - "$work/root.dmg" "$out" <<'PY'
import sys
from pathlib import Path
raw = Path(sys.argv[1]).read_bytes()
size = 8 * 1024 * 1024
if len(raw) < size:
    raise SystemExit(f"UDRW image too small: {len(raw)}")
sig = raw[1024:1026]
if sig not in (b"H+", b"HX"):
    raise SystemExit(f"HFS+ volume header not at raw offset 1024: {sig!r}")
p = Path(sys.argv[2])
p.write_bytes(raw[:size])
assert p.stat().st_size == size
print("PASS: macOS HFSX RAM-root (8 MiB), /sbin/launchd copied and /dev created:", p)
PY
