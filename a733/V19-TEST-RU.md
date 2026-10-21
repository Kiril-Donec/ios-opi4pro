# A733 XNU v19 — hardware test of anonymous virtual memory

**Status: SUCCESSFULLY HARDWARE-TESTED on Orange Pi 4 Pro, 21 October 2026.** User-supplied HDMI photographs show the v19 PASS marker and continuing PID 1 heartbeat. This is a test program, not actual iOS.

The successful v17 XNU kernel, single A76 CPU, Stage0, U-Boot layout and 8-MiB HFSX RAM-disk size are all unchanged from the board-proven v18 AutoBoot IMG. The only changed bytes are our test PID 1 Mach-O stored in the RAM-root at `/sbin/launchd`. This is **not the actual Apple launchd**.

## What's new compared with v18

Test source: [a733-init-v19.S](src/a733-init-v19.S). The existing file I/O tests (`getpid`, opening `/sbin/launchd`, reading/verifying 4-byte Mach-O magic, `close`, expected `ENOENT`) run before the new virtual-memory tests.

v19 then executes on the same PID 1 thread:

1. `mmap(NULL, 0x4000, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANON, -1, 0)` (Darwin BSD syscall 197);
2. writes one 64-bit pattern to the first and last aligned 8-byte positions of the 16-KiB page and reads both back;
3. `mprotect(ptr, 0x4000, PROT_READ)` (syscall 74), checks that reading is still possible;
4. `munmap(ptr, 0x4000)` (syscall 73);
5. opens `/dev/console`, prints one PASS/FAIL message and returns to the established v18 heartbeat.

**No deliberate write to a read-only mapping** is attempted; a full permission-fault/recovery stress test is postponed.

## Exact offline IMG

- Filename: `ios-a733-xnu-autoboot-v19-mmap-mprotect-20261021.img`
- Size: 67,108,864 bytes (64 MiB)
- SHA-256: `0edbf0f5d82bb81028fbbefa3b0f256ce1549101d79cd5302f26d6d8e0b08c64`
- Physical-test base v18 SHA-256: `0923c1e9eab7bf9fea87520ceed57acf9f166b18cfa0eb9ec165431797b500a7`
- v19 signed static Mach-O SHA-256: `1315a6ffeb23b9cbcfb6433e1f12545191c24a8be537846063c3ce26c9487b7c`
- Changed file range inside full IMG: offset `59534880`, length `16635` bytes.
- Confirmed byte-for-byte unchanged outside that range: including first 32 MiB with bootloader, MBR, ext4 metadata and kernel payload outside that Mach-O.
- Confirmed CodeDirectory SHA-256 hashes for the four signed 4-KiB pages of the Mach-O, ARM64 binary identity and ext4 superblock/MBR signatures.
- Repository source Git blob SHA: `1fe31e2235d499f636586098b3345c943a5b1657` — matches the file compiled in the offline image.

**Offline limitations:** No full filesystem fsck or finished macOS GitHub Actions artifact equivalence is claimed. The additional physical test confirms observed functionality, but the photographed screen does not prove the exact written IMG checksum or all XNU virtual-memory mechanisms.

## Hardware result (21 October 2026)

**Photographed exact success line:**

```text
A733 V19 PASS: mmap RW + mprotect RO + munmap
A733 init: still alive
```

The test also includes these failure labels for possible future regressions:
- `A733 V19 FAIL: mmap`
- `A733 V19 FAIL: VM write/read`
- `A733 V19 FAIL: mprotect`
- `A733 V19 FAIL: RO read`
- `A733 V19 FAIL: munmap`

Earlier v18 failure lines are still available if the prerequisite file-I/O tests fail.

**Observed in supplied photos:** kernel reaches the test PID 1, prints `A733 V19 PASS: mmap RW + mprotect RO + munmap`, and repeatedly prints `A733 init: still alive` with successful syscall 4 writes (`errno=0 result=23`). No fatal exception or kernel panic is visible. One 16-KiB RW anonymous page and the RO transition were exercised, but *writing to the RO mapping was intentionally not tested*, so protection-fault recovery is still unverified. No further photos of this same heartbeat are needed.

The `V14`, `V15`, `V16`, `V17` labels in kernel traces are leftover diagnostic strings from the unchanged v17 XNU. They do not identify the currently loaded user-space test version.

## Safety

Use a spare microSD or verify a backup before writing any test IMG. The 64-MiB image contains experimental boot code; do not write it to a card with valuable data. The userland tests do not intentionally write to SD/eMMC; they operate on an in-memory HFSX root. The second A76 and all A55 cores remain disabled.

This does not prove Apple iOS/SpringBoard functionality; it confirms these XNU virtual-memory API operations in a single limited user-space task on real A733 hardware.
