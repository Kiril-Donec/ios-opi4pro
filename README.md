# iOS / XNU bring-up on Orange Pi 4 Pro (Allwinner A733)

An experimental port of Apple's **XNU 8796** (iOS 16-era kernel) to the **Orange Pi 4 Pro** with an **Allwinner A733** (2× Cortex-A76 + 6× Cortex-A55).

> **Current hardware status (20 October 2026, v14):** XNU boots, reaches BSD, mounts an HFS+ RAM root, and executes test PID 1. The `getpid()` syscall **returns PID 1 successfully**, then userspace enters `open()` which stalls in the handler path. **v15 now passes kernel, PID1, and payload CI checks**, adding targeted `open`/VFS diagnostics and a regular-file probe; v15 is **not yet hardware-verified**. **Full iOS and SpringBoard are not running.**

This project is an independent A733 port based on [MakrSas/ios-topaz](https://github.com/MakrSas/ios-topaz) and the underlying [ios-sweet](https://github.com/dipa-studio/ios-sweet) work. The original `ios-topaz` repository belongs to its author, not the owner of this fork.

## Verified on the real board

The evidence below comes from photographed HDMI/serial-framebuffer output on an Orange Pi 4 Pro, **not just a successful CI compile**:

| Stage | Hardware result |
| --- | --- |
| U-Boot → A733 Stage0 → XNU | **Works.** Stage0 transfers control to the XNU payload on an A76 core (MPIDR `0x600`). |
| Early CPU, exception and NEON initialization | **Passed in current tests**, following earlier SError and early exception fixes. |
| Framebuffer/HDMI diagnostic output | **Works.** A portrait 600×1024 text console is drawn in software over a physical 1024×600 HDMI framebuffer. This is not an iOS GPU/display driver. |
| Interrupts and single-core scheduling | **Works in tested configuration:** `SWEET CPU: 1/1 CPUs initialized, SGI1 verified`. |
| IOKit and BSD initialization | **Reached successfully:** `A733 TRACE 06: IOKit matching returned`, `A733 TRACE 12: BSD initialization returned`. |
| In-memory root filesystem (v11) | **Works:** `BSD root: md0, major 1, minor 0`; `hfs: mounted A733RAM on device b(1, 0)`. |
| HFS+ root with experimental Mach-O at `/sbin/launchd` (v12) | **Mount works:** `hfs: mounted A733PID1 on device b(1, 0)`. XNU prints `load_init_program: attempting to load /sbin/launchd`. |
| First userspace program / PID 1 (v13) | **CONFIRMED entering userspace** on real hardware: `execve returned errno=0 for /sbin/launchd` followed by `A733 PID1: syscall enter 5`. No `syscall exit 5` observed; the `open` handler or a subsequent step has not completed visibly. |
| PID 1 returns from a syscall (v14) | **Confirmed on physical board:** `syscall exit 20 errno=0 result=1`, followed by `syscall enter 5` and `BEFORE_SY_CALL syscall=5`. No `AFTER_SY_CALL syscall=5` appeared. The stall is inside the `open` handler path, not in the earlier audit or userspace transition. |
| Real Apple launchd, SpringBoard, apps, iOS UI | **Not running.** This test RAM disk is a minimal HFS+ root, not a full iOS root filesystem. |

**v11 milestone:** a blank RAM disk mounted successfully; PID 1 could not start because `/sbin/launchd` was absent (`errno 2`, expected).

**v12 milestone:** the RAM disk contains a small ad-hoc-signed **test** Mach-O named `/sbin/launchd`. This is **not** Apple's launchd. No success/failure is yet established for the userspace transition: the last visible line is the exec attempt. XNU framebuffer `kprintf` and the userspace `/dev/console` are different output paths.

**v13 hardware result (20 October 2026):** kernel-side framebuffer logs confirm `execve` returned 0 for `/sbin/launchd` and the experimental userspace program invoked syscall 5 (`open`). This confirms a real userspace-to-kernel transition on ARM64. No syscall exit log was seen, so execution beyond `open` remains unverified. The prepared v13 AutoBoot image deliberately **reuses the physically tested v12 HFS+ RAM disk and original v12 PID 1 executable**, to isolate the XNU change: the first expected syscall is `open` (number 5), which tests `/dev/console`. A separate `getpid`-before-`open` probe has also been committed in `a733-init.S` for a later image but is **not present** in this particular v13 test IMG. No second CPU is enabled. On the current GitHub Ubuntu runner, building a fresh populated HFS+ disk fails because the runner lacks the HFS+ mount driver; this does not invalidate the already audited macOS XNU build or the v12 RAM disk.

**v14 CI milestone (20 October 2026):** [GitHub Actions run #39431933051](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39431933051) **passed** both the macOS kernel/userspace build and the Ubuntu packaging job at commit `96767d3`. The newly built, static ARM64 test PID 1 calls `getpid()` (syscall 20) **before** `open("/dev/console")` (syscall 5). XNU includes `A733 PID1 V14: BEFORE_AUDIT_ENTER`, `BEFORE_SY_CALL`, `AFTER_SY_CALL` and `AFTER_AUDIT_EXIT` checkpoints for these calls. macOS built a populated 8-MiB HFSX RAM-root with `/sbin/launchd` (our test program, not Apple launchd). The [v14 PID1 artifact](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39431933051/artifacts/12268801889) contains the audited `a733-xnu-pid1.payload`, `stage0.uimg`, HFSX image and support files. **It is not a complete flashable SD-card IMG.** A previously verified A733 U-Boot/SD layout is needed to prepare a full image, with careful backup and layout validation. **Subsequent physical v14 photos confirm `getpid()` returned PID 1 and the next `open()` stalls inside the syscall handler**; the original CI result alone did not prove this. One A76 core remains enabled.

**v15 CI milestone (20 October 2026):** [GitHub Actions run #39464210361](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39464210361) **passed** macOS XNU compilation, Mach-O trace-string audit, signed static PID 1, populated HFSX RAM-disk creation, and Ubuntu `A733XNU1` payload integration. The [v15 PID1 artifact](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39464210361/artifacts/12284581494) contains `a733-xnu-pid1.payload` (SHA-256 `edc4d4098d53dc181b921c6c33a3804aa73a7e77b0a2b479c0b2586f302c6fe8`). A separate 64-MiB test SD IMG was prepared from the verified v14 layout by replacing only the payload in a *copy* of its ext4 partition; its SHA-256 is `975ad79943b246ddbcbeeee9f574fa33c4cf8a9e433a772eac104353666ecdd5`. The first 32 MiB of U-Boot/container bytes match the verified v14 base, ext4 `e2fsck -fn` passes, and payload filesystem readback matches the CI payload. **These are offline checks, not a successful v15 boot on hardware.**

## Current limitations

**v15 diagnostic build (CI passed; hardware test pending):** the test PID 1 first tries to open its own `/sbin/launchd` Mach-O with `O_RDONLY`, then `/dev/console` with `O_RDWR`. `a733/xnu-a733-pid1-v15-open.patch` traces `open()`, allocation, file-descriptor setup, vnode authorization, `namei()` and `VNOP_OPEN()` only for PID 1. This is a diagnostic change, **not a proven fix**. Use a spare microSD or an adequate backup before testing the offline-audited IMG.

- **Only one CPU is enabled** (`cpus=1`); SMP and the six A55 cores are deferred.
- **No permanent XNU SD/eMMC storage driver.** U-Boot reads the test image from microSD; XNU's current root is an **8 MiB RAM-backed HFS+ volume** (`rd=md0`).
- The first user process returns successfully from `getpid()`, but `open("/dev/console")` does not yet return; v15 compares regular-file HFS+ and devfs opens.
- No complete iOS rootfs, Apple userspace services, touch stack or functional graphics acceleration. Display output is an early framebuffer console.
- The imported Xiaomi/Qualcomm sources still contain device-specific paths. Boot flags `modem=0 wifi=0 sweetbattery=0 sweetcpufreq=0` keep the known incompatible ones disabled.
- Some `sweet`, `SWEET`, and `topaz` identifiers remain in build configurations and inherited source files for compatibility; **the target is Allwinner A733**.

## Project layout

- [`a733/src/`](a733/src/) — Stage0 and the test `a733-init.S` userspace program.
- [`a733/tools/package_xnu_a733.py`](a733/tools/package_xnu_a733.py) — audited A733-only XNU packaging, optional HFS+ RAM disk, and guarded boot arguments.
- [`a733/tools/make_pid1_ramdisk.sh`](a733/tools/make_pid1_ramdisk.sh) — builds the minimal test `/sbin/launchd` root with `/dev`.
- [`a733/xnu-a733-boot-trace.patch`](a733/xnu-a733-boot-trace.patch) — visible BSD/rootfs milestones.
- [`a733/xnu-a733-pid1-trace.patch`](a733/xnu-a733-pid1-trace.patch) — **experimental** PID 1 exec/syscall tracing (requires a new kernel build and hardware verification).
- [`a733/xnu-a733-pid1-v15-open.patch`](a733/xnu-a733-pid1-v15-open.patch) — PID1-only `open`/VFS tracepoints; not yet hardware-tested.
- [`.github/workflows/xnu.yml`](.github/workflows/xnu.yml) — builds patched XNU on macOS, audits the Mach-O, compiles Stage0, creates and validates HFS+ RAM-root payloads.
- [`.github/workflows/a733-stage0.yml`](.github/workflows/a733-stage0.yml) — Linux Stage0 tests.
- [`xnu/patches/`](xnu/patches/) — upstream-derived XNU patch series.
- [`a733/V4-XNU.md`](a733/V4-XNU.md) — **historical** early bring-up notes; for current status use this README.

### Build and verification

For Stage0 on Ubuntu/Debian with an AArch64 cross-compiler:

```sh
make -C a733 test adt all test-boot
```

For XNU, use [GitHub Actions: A733 XNU](../../actions/workflows/xnu.yml). The workflow compiles a patched XNU DEVELOPMENT kernel on macOS, statically checks the real Mach-O and packages an `A733XNU1` payload. RAM-root integration tests run on Linux. **CI PASS means the artifacts build and validate; it does not prove execution on the physical board.**

The guarded Stage0 rejects legacy Xiaomi `SWEETXNU` payloads and accepts only `A733XNU1`. Do not flash an untested payload as if it were a completed iOS installation.

## Important test precautions

The board owner's primary microSD card is repeatedly reused for experiments. **No automatic flashing or destructive operations are performed by CI or this repository.** Verify the device and any backups before writing an IMG; a successful kernel build is not a guarantee of bootability.

The current target is to make PID 1 **complete a file open** and continue running on one A76 core. The `getpid()` syscall already returned successfully on hardware. SMP, persistent storage and iOS UI are later milestones.
