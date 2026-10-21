# Orange Pi 4 Pro — XNU v18 (read/close/ENOENT test)

**21 October 2026. This build has NOT yet been tested on the board.** It is a deliberately narrow follow-up to the successful v17 test, which remained alive for at least 15 minutes.

## What changed

- **XNU kernel:** unchanged from the board-proven v17 image.
- **Stage0, U-Boot/MBR, ext4 layout, 8-MiB HFSX RAM root size:** unchanged.
- **Only the 16,635-byte signed test PID 1 Mach-O `/sbin/launchd`** inside the HFSX RAM root was replaced with the new `a733/src/a733-init-v18.S` program. This is our test executable, **not Apple's launchd**.
- Still **one Cortex-A76**; SMP and the A55 cores are deferred.

The new PID 1 calls `getpid()`, then:
1. Opens its own `/sbin/launchd` read-only;
2. Reads exactly four bytes into a 16-byte-aligned user-stack buffer (testing `read()` / kernel-to-userspace `copyout()`);
3. Checks the expected 64-bit Mach-O little-endian magic `0xfeedfacf`;
4. Closes the descriptor;
5. Tries to open `/a733-v18-definitely-missing` and expects `ENOENT=2`;
6. Opens `/dev/console`, prints the result, and continues its v17 heartbeat loop.

## Source and offline image validation

- Source: [`a733/src/a733-init-v18.S`](src/a733-init-v18.S).
- The repository Git blob ID for the assembled source matches the exact source compiled offline: `0ab9fe8753ee6561209d453d92c332116d7134ac`.
- Static signed v18 Mach-O SHA-256: `ca8d58fd9f773e84c1dc95c8b4c16a77e7faaba7a83d3112b4ef8af337c2634f`.
- Base physical-test v17 AutoBoot IMG SHA-256: `1fbf1b44a4efc0cb9bb4274f4d4c97f419eadf4a9b44af44afd8254afaedeab9`.
- Local 64-MiB v18 AutoBoot IMG SHA-256: `0923c1e9eab7bf9fea87520ceed57acf9f166b18cfa0eb9ec165431797b500a7`.
- Exact replacement region: file offset `59,534,880`, length `16,635` bytes. Every byte outside this region was verified identical to the board-proven v17 IMG; the first 32 MiB are byte-for-byte identical.
- Mach-O CodeDirectory SHA-256 code-page hashes (four 4-KiB code pages) checked successfully. MBR partition signature/type/start/length unchanged.

**Limits of these checks:** the new image has not been booted on Orange Pi, the full filesystem `e2fsck` was not available in the local build environment, and the locally compiled binary has not yet been compared with macOS CI output. Do not label the v18 tests as hardware PASSED based on offline validation.

## Expected HDMI result

Success would look like:

```text
A733 V18 PASS: read(4B Mach-O) + close + ENOENT
A733 init: still alive
```

The kernel's PID1 syscall trace should also show:
- `syscall enter 3` and `syscall exit 3 errno=0 result=4`;
- `syscall enter 6` and `syscall exit 6 errno=0`;
- the missing-file `open` returning an error 2 (expected, not a fatal failure);
- `open("/dev/console")` and repeated `write` syscalls continuing.

A `A733 V18 FAIL: ...` line tells us which new test failed; photograph it. If it stops before opening the console, photograph the **last kernel syscall trace**, not only a blank or early boot screen. The `PASS` banner can scroll away as the heartbeat repeats, so a photo shortly after boot is more useful than waiting 15 minutes.

**Do not write over your only working microSD without a backup.** Use a test card if possible.

## What this does not provide

This is still XNU with an ad-hoc test PID 1 in a tiny RAM-backed filesystem. It is not a real iOS distribution, does not start the Apple launchd, and has no iOS UI, GPU driver, SD/eMMC driver inside XNU, or multi-core scheduling.
