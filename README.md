# iOS / XNU bring-up on Orange Pi 4 Pro (Allwinner A733)

An experimental port of Apple's **XNU 8796** (iOS 16-era kernel) to the **Orange Pi 4 Pro** with an **Allwinner A733** (2× Cortex-A76 + 6× Cortex-A55).

> **Current hardware status (21 October 2026, v19):** **Board-tested milestone reached.** XNU 8796 boots on one Cortex-A76, mounts the 8-MiB HFS+/HFSX RAM-root, runs our test PID 1 and successfully returns from `getpid()`, both `open()` calls and repeated `write()` calls. Real-board HDMI photos show `COPYINSTR_ACCESS_END errno=0 len=13`, completed `namei`/`VNOP_OPEN`, `syscall exit 5 errno=0` and repeated `A733 init: still alive`. This resolves the **previously observed v16 `_bcopyinstr()` stall** in the v17 build; it does not isolate which individual v17 code change was decisive. **21 October v18 update:** Hardware photos also show `A733 V18 PASS: read(4B Mach-O) + close + ENOENT` followed by repeated `A733 init: still alive`, demonstrating the test program successfully read and validated four file bytes, closed the file, and handled a deliberately missing path without stopping. **21 October v19 update:** Real-board photos show `A733 V19 PASS: mmap RW + mprotect RO + munmap` followed by repeated `A733 init: still alive`: our test PID 1 successfully allocated a 16-KiB anonymous page, wrote/read test patterns, changed the mapping to read-only, read from it, and unmapped it. There was no visible panic in the photographed test. **This is a custom test userspace, not Apple launchd, iOS or SpringBoard.**

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
| Open pathname copy stalls (v15) | **Confirmed on physical board:** `/sbin/launchd` returns from `execve` and from `getpid`; first `open` passes fd allocation and enters `namei()`. The final visible checkpoint after five minutes is `A733 PID1 V15: NAMEI_COPY_ENTER`, with no `NAMEI_COPY_DONE`. This is a location, not a proven root cause or fix. |
| Usercopy, pathname lookup, file and console open, sustained PID1 writes (v17) | **CONFIRMED on real hardware 21 Oct 2026.** `COPYINSTR_ACCESS_END errno=0 len=13`, `NAMEI_COPY_DONE errno=0`, `VN_AUTH_VNOP_OPEN_DONE errno=0`, `OPENAT_OPEN1_DONE errno=0`, two successful syscall 5 exits (file descriptors 0 and 1) and recurring syscall 4 exits with `errno=0 result=23`; userspace logs `A733 init: still alive`. |
| Test PID1 reads and closes file, validates expected ENOENT (v18) | **CONFIRMED on real hardware 21 Oct 2026.** HDMI photos show `A733 V18 PASS: read(4B Mach-O) + close + ENOENT`, a missing path yields `errno=2`, and the periodic `A733 init: still alive` output continues. XNU kernel is unchanged from v17; v18 alters only the test Mach-O in HFSX RAM root. |
| Anonymous VM lifecycle (v19) | **CONFIRMED on real hardware 21 Oct 2026.** Test PID 1 printed `A733 V19 PASS: mmap RW + mprotect RO + munmap` and kept writing `A733 init: still alive`. This covers one 16-KiB RW anonymous mapping, read/write verification, switching to RO, reading and unmapping; it does NOT exercise write permission fault handling, multiple processes, VM pressure or all kernel memory paths. |
| Real Apple launchd, SpringBoard, apps, iOS UI | **Not running.** This test RAM disk is a minimal HFS+ root, not a full iOS root filesystem. |

**v11 milestone:** a blank RAM disk mounted successfully; PID 1 could not start because `/sbin/launchd` was absent (`errno 2`, expected).

**v12 milestone:** the RAM disk contains a small ad-hoc-signed **test** Mach-O named `/sbin/launchd`. This is **not** Apple's launchd. No success/failure is yet established for the userspace transition: the last visible line is the exec attempt. XNU framebuffer `kprintf` and the userspace `/dev/console` are different output paths.

**v13 hardware result (20 October 2026):** kernel-side framebuffer logs confirm `execve` returned 0 for `/sbin/launchd` and the experimental userspace program invoked syscall 5 (`open`). This confirms a real userspace-to-kernel transition on ARM64. No syscall exit log was seen, so execution beyond `open` remains unverified. The prepared v13 AutoBoot image deliberately **reuses the physically tested v12 HFS+ RAM disk and original v12 PID 1 executable**, to isolate the XNU change: the first expected syscall is `open` (number 5), which tests `/dev/console`. A separate `getpid`-before-`open` probe has also been committed in `a733-init.S` for a later image but is **not present** in this particular v13 test IMG. No second CPU is enabled. On the current GitHub Ubuntu runner, building a fresh populated HFS+ disk fails because the runner lacks the HFS+ mount driver; this does not invalidate the already audited macOS XNU build or the v12 RAM disk.

**v14 CI milestone (20 October 2026):** [GitHub Actions run #39431933051](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39431933051) **passed** both the macOS kernel/userspace build and the Ubuntu packaging job at commit `96767d3`. The newly built, static ARM64 test PID 1 calls `getpid()` (syscall 20) **before** `open("/dev/console")` (syscall 5). XNU includes `A733 PID1 V14: BEFORE_AUDIT_ENTER`, `BEFORE_SY_CALL`, `AFTER_SY_CALL` and `AFTER_AUDIT_EXIT` checkpoints for these calls. macOS built a populated 8-MiB HFSX RAM-root with `/sbin/launchd` (our test program, not Apple launchd). The [v14 PID1 artifact](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39431933051/artifacts/12268801889) contains the audited `a733-xnu-pid1.payload`, `stage0.uimg`, HFSX image and support files. **It is not a complete flashable SD-card IMG.** A previously verified A733 U-Boot/SD layout is needed to prepare a full image, with careful backup and layout validation. **Subsequent physical v14 photos confirm `getpid()` returned PID 1 and the next `open()` stalls inside the syscall handler**; the original CI result alone did not prove this. One A76 core remains enabled.

**v15 CI milestone (20 October 2026):** [GitHub Actions run #39464210361](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39464210361) **passed** macOS XNU compilation, Mach-O trace-string audit, signed static PID 1, populated HFSX RAM-disk creation, and Ubuntu `A733XNU1` payload integration. The [v15 PID1 artifact](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39464210361/artifacts/12284581494) contains `a733-xnu-pid1.payload` (SHA-256 `edc4d4098d53dc181b921c6c33a3804aa73a7e77b0a2b479c0b2586f302c6fe8`). A separate 64-MiB test SD IMG was prepared from the verified v14 layout by replacing only the payload in a *copy* of its ext4 partition; its SHA-256 is `975ad79943b246ddbcbeeee9f574fa33c4cf8a9e433a772eac104353666ecdd5`. The first 32 MiB of U-Boot/container bytes match the verified v14 base, ext4 `e2fsck -fn` passes, and payload filesystem readback matches the CI payload. **These are offline checks, not a successful v15 boot on hardware.**

**v16 CI and image (20 October 2026):** [GitHub Actions #39480590799](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39480590799) passed macOS kernel build, compiled marker audit, HFSX root construction and Ubuntu payload integration. Its [PID1 CI artifact](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39480590799/artifacts/12290989136) contains an audited payload SHA-256 `4e7c53feb8b8dd8b50d88c79b4c61ee23029ac57164a5a7036b374123159a591`. A 64-MiB AutoBoot IMG was assembled by replacing only the equal-size XNU payload in a copy of the verified v15 ext4 image; full ext4 readback matched GitHub's payload, and the first 32 MiB were unchanged. The v16 IMG SHA-256 is `1c1d1196f4422362fdbe6906905260fb98c9ba8e50450cc088e4c0398fec4384`. **No hardware boot result for v16 yet; do not mistake CI PASS for a fix of `open()`.**

**v16 probe design:** `a733/xnu-a733-pid1-v16-copyinstr.patch` instruments XNU 8796 ARM64 `copyinstr()` around user-address validation, access-enablement, and `_bcopyinstr()`. Its purpose is to distinguish an invalid user address from a missing translation or exception/recovery issue during a user-space read. The v16 patch requires new kernel compilation and a physical board test; until that happens, `open()` **is not fixed**. The existing v15 boot, Stage0 and single-core configuration are kept unchanged.

**v16 hardware result:** User photos confirm `A733 PID1 V16: COPYINSTR_ENTER user=0x1000004e0 size=256`, `COPYINSTR_VALIDATE_DONE errno=0`, `COPYINSTR_USER_ACCESS_ENTER`, and `COPYINSTR_ASM_ENTER`, with no corresponding `COPYINSTR_ASM_DONE`. Earlier copies inside `execve` return successfully. The reported user address passes range validation, but this does not prove the kernel's privileged access permissions or page mappings are correct. The failure manifests inside the low-level `_bcopyinstr` on the first real PID 1 `open`.

**v17 PAN fix candidate:** The inherited `xnu/pexpert/pexpert/arm64/SWEET.h` disabled `__ARM_PAN_AVAILABLE__` for the original A53/A73 CPUs. A733 currently boots only on a Cortex-A76 (ARMv8.2, with Privileged Access Never support). [`a733/xnu-a733-pid1-v17-usercopy.patch`](a733/xnu-a733-pid1-v17-usercopy.patch) enables the XNU PAN mechanism for this configuration: PAN=1 during normal kernel execution, disabled by `user_access_enable()` for kernel reads of user memory, and restored by `user_access_disable()`. The patch also moves `kprintf` tracing outside the PAN-disabled section to avoid instrumentation while user accesses are temporarily permitted. One core remains enabled. **Verified on the real board (21 October 2026):** the v17 build gets past the formerly stalled usercopy, completes both `open()` calls and continues with repeated userspace `write()`. Native PAN handling plus moving `kprintf` outside the PAN-disabled window is the successful v17 *change set*; the photos alone cannot isolate one cause. It does not bypass kernel security checks.

**v17 build result (20 October 2026):** [GitHub Actions run #39488689426](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39488689426) passed XNU compilation for `-mcpu=cortex-a76`, the new PAN-related Mach-O checks, static PID 1 build, macOS HFSX RAM-root creation, and Ubuntu payload packaging. An offline 64-MiB AutoBoot test IMG was prepared from the v16 boot layout; its first 32 MiB match v16 byte-for-byte, and the new shorter payload (`25,471,456` bytes) was read back from ext4 and compared with CI. SHA-256 of the IMG is `9b0021366947a6054810caa40cfa4d8524dd7d8414f6b138533f124f51b01986`. The original v16 base is unchanged. The full `e2fsck` executable was unavailable for this offline repack; the readback check does not substitute for a complete filesystem check. **21 Oct update:** subsequent real-board HDMI photos confirm that v17 runs past the usercopy/open stall. The SHA-256 above identifies the earlier offline v17 IMG variant, not necessarily the exact image used in the photographed test.

## v18 file I/O milestone (21 October 2026; board verified)

The successful v17 single-core XNU kernel and Stage0 are intentionally **unchanged**. The only image change is the 16,635-byte **test PID 1 Mach-O** `/sbin/launchd` inside the HFSX RAM root, built from [`a733/src/a733-init-v18.S`](a733/src/a733-init-v18.S). The v18 userspace now tests `open`, `read` of its own Mach-O header into user stack memory, validates magic `0xfeedfacf`, tests `close`, and expects `ENOENT` on a nonexistent path before reopening the console and resuming the heartbeat. This extends v17 without touching additional CPUs, XNU code or device drivers.

**Locally prepared full 64-MiB AutoBoot IMG** (based on the physically working v17 IMG) SHA-256: `0923c1e9eab7bf9fea87520ceed57acf9f166b18cfa0eb9ec165431797b500a7`. The original v17 IMG SHA-256 is `1fbf1b44a4efc0cb9bb4274f4d4c97f419eadf4a9b44af44afd8254afaedeab9`; only byte range `59534880..59551514` (16,635 bytes) changed. Mach-O ad-hoc signature code-page hashes and exact outside-region byte equality were verified offline. Our local Mach-O packager reproduced the old v17 test binary **byte-for-byte**, validating packaging compatibility. **Real-board v18 boot verified on 21 October 2026** by six photographed HDMI frames. Full ext4 fsck and completed CI run are not asserted, and the photos cannot independently verify the SHA-256 of the exact flashed IMG. See [v18 hardware test notes](a733/V18-TEST-RU.md).

**Observed on hardware:** `A733 V18 PASS: read(4B Mach-O) + close + ENOENT` followed by repeated `A733 init: still alive` and successful `write` exits; the deliberate negative-path open returns `errno=2` as expected. The on-screen `V16` and `V17` marker prefixes are retained diagnostic labels from the v17 XNU kernel, not evidence that v18 loaded the wrong image.

## v19 — anonymous virtual-memory self-test (21 October 2026; real-board PASS)

**Hardware status: PASSED on Orange Pi 4 Pro, confirmed by user-supplied HDMI photographs on 21 October 2026.** After [v18 passed file I/O on the real A733 board](a733/V18-TEST-RU.md), v19 retains the same XNU v17 kernel, single-core Stage0, partition layout and HFSX RAM-root; only the signed PID 1 test Mach-O changes. The new [a733-init-v19.S](a733/src/a733-init-v19.S) first reruns the successful file-I/O checks and then exercises `mmap` for one 16-KiB anonymous RW page, read/write checks at both ends, `mprotect` to read-only, a read check and `munmap`. It prints an explicit `A733 V19 PASS: mmap RW + mprotect RO + munmap` or a specific `A733 V19 FAIL: ...` message before continuing the heartbeat.

**Locally packaged AutoBoot IMG:** `ios-a733-xnu-autoboot-v19-mmap-mprotect-20261021.img`, 64 MiB, SHA-256 `0edbf0f5d82bb81028fbbefa3b0f256ce1549101d79cd5302f26d6d8e0b08c64`. Compared with the verified v18 IMG SHA-256 `0923c1e9eab7bf9fea87520ceed57acf9f166b18cfa0eb9ec165431797b500a7`, precisely 16,635 file bytes at offset `59,534,880` were replaced. The rest of the image was byte-for-byte identical, and the new Mach-O CodeDirectory SHA-256 slots passed offline verification. **Hardware runtime has now been confirmed independently of the offline build checks:** photographs show the explicit v19 PASS line and continued PID 1 heartbeat. The photos do not independently establish the flashed IMG's SHA-256, a full ext4 fsck or comprehensive system stability.

[Hardware test procedure and hashes](a733/V19-TEST-RU.md) · [v19 user program source](a733/src/a733-init-v19.S)

## Experimental A733 real iOS graphics (21 October 2026; source candidate)

The next experimental branch of work targets **actual Apple iOS userland frames**, not a mock home screen. A new [A733-specific XNU graphic overlay](a733/xnu-a733-ios-framebuffer.patch) changes the existing `AppleCLCD`/`IOMobileFramebuffer` driver to copy **real IOSurface surfaces** to the proven U-Boot/HDMI `0xBBF11000` framebuffer, CPU-scale an iPhone X canvas (1125×2436) to portrait 600×1024 and rotate it into physical 1024×600 pixels. The patch also keeps Qualcomm MDP accesses disabled on A733 and adds an eight-line kernel-log overlay over any real frame (`a733fb_logs=1`, default, or `=0` to hide).

The [A733 Apple Device Tree generator](a733/tools/mkadt_a733.py) has a fail-closed, opt-in `--ios-display` mode that advertises `/arm-io/disp0` with the `sweet,display` matching interface required by `AppleCLCD`. The original v19 device tree remains the default. CI now builds the driver overlay and packages a **separate experimental display-enabled payload**. The included 8-MiB root still has only our custom test PID 1 and **no real Apple launchd, dyld shared cache, backboardd or SpringBoard**. Thus neither a successful compile nor a successful hardware boot with this test root would show genuine iOS frames.

**Status: proposed implementation awaiting CI validation and real-board display tests.** The physically tested v19 image remains the rollback baseline, unchanged. This is not yet a flash-ready or successfully booted iOS GUI image. See [the complete real-iOS graphics bring-up notes](a733/IOS-GRAPHICS-RU.md).

## Current limitations

**Historical v15 hardware result (stalled in user pathname copying; FIXED IN v17 for the test PID 1):** the test PID 1 first tries to open its own `/sbin/launchd` Mach-O with `O_RDONLY`, then `/dev/console` with `O_RDWR`. `a733/xnu-a733-pid1-v15-open.patch` traces `open()`, allocation, file-descriptor setup, vnode authorization, `namei()` and `VNOP_OPEN()` only for PID 1. This is a diagnostic change, **not a proven fix**. Use a spare microSD or an adequate backup before testing the offline-audited IMG.

- **Only one CPU is enabled** (`cpus=1`); SMP and the six A55 cores are deferred.
- **No permanent XNU SD/eMMC storage driver.** U-Boot reads the test image from microSD; XNU's current root is an **8 MiB RAM-backed HFS+ volume** (`rd=md0`).
- **v17 passed the earlier `open()` stall.** The custom PID 1 now returns from both file and `/dev/console` opens and loops with repeated successful `write()` calls. More functional validation and the *real* iOS userspace are future work.
- No complete iOS rootfs, Apple userspace services, touch stack or functional graphics acceleration. Display output is an early framebuffer console.
- The imported Xiaomi/Qualcomm sources still contain device-specific paths. Boot flags `modem=0 wifi=0 sweetbattery=0 sweetcpufreq=0` keep the known incompatible ones disabled.
- Some `sweet`, `SWEET`, and `topaz` identifiers remain in build configurations and inherited source files for compatibility; **the target is Allwinner A733**.

## Project layout

- [`a733/src/`](a733/src/) — Stage0 and the test `a733-init.S` userspace program.
- [`a733/tools/package_xnu_a733.py`](a733/tools/package_xnu_a733.py) — audited A733-only XNU packaging, optional HFS+ RAM disk, and guarded boot arguments.
- [`a733/tools/make_pid1_ramdisk.sh`](a733/tools/make_pid1_ramdisk.sh) — builds the minimal test `/sbin/launchd` root with `/dev`.
- [`a733/xnu-a733-boot-trace.patch`](a733/xnu-a733-boot-trace.patch) — visible BSD/rootfs milestones.
- [`a733/xnu-a733-pid1-trace.patch`](a733/xnu-a733-pid1-trace.patch) — **experimental** PID 1 exec/syscall tracing (requires a new kernel build and hardware verification).
- [`a733/xnu-a733-pid1-v15-open.patch`](a733/xnu-a733-pid1-v15-open.patch) — PID1-only `open`/VFS tracepoints; board-tested, stopped at `copyinstr`.
- [`a733/src/a733-init-v18.S`](a733/src/a733-init-v18.S) — v18 userspace probe for `read`/`close`/`ENOENT`, board-tested 21 Oct 2026.
- [`a733/V18-TEST-RU.md`](a733/V18-TEST-RU.md) — v18 image hashes, test expectations and hardware-test precautions.
- [`a733/src/a733-init-v19.S`](a733/src/a733-init-v19.S) — v19 anonymous VM mapping, protect and unmap self-test, passed on physical board 21 Oct 2026.
- [`a733/V19-TEST-RU.md`](a733/V19-TEST-RU.md) — v19 image SHA-256 and expected VM success/failure output.
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

**Milestones achieved on 21 Oct 2026:** test PID 1 opens, reads and closes files, handles `ENOENT`, and stays alive on one A76 core. v19 additionally confirms anonymous 16-KiB `mmap`, user data access, `mprotect` RO, readback and `munmap` on real hardware. Process/thread lifecycle, Mach IPC, real Apple userspace, SMP and storage/display drivers remain future work.
