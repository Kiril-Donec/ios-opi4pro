# A733 development handoff — 2026-10-19

Target: Orange Pi 4 Pro (Allwinner A733, 2×Cortex-A76 + 6×Cortex-A55, 4 GiB RAM).

## Confirmed on physical board

- Stage0 phone-shaped portrait HDMI diagnostic screen displayed.
- U-Boot/PSCI `CPU_ON` entered one Cortex-A76, MPIDR `0x600`, and reported MMFR0 `0x0000000000101122`.

## Automated validation on GitHub

- Commit `a8729bc72595ffd12bcfe4cbd48da133896ce096` includes 20 upstream updates and the first A733 source overlay.
- Linux Stage0 Actions run [39293622912](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39293622912): **SUCCESS** (cross-compile and host tests).
- macOS XNU Actions run [39293623008](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39293623008): **SUCCESS** (XNU compilation, artifacts, static `audit_a733_macho.py`).
- This validates a compiled A733 first-boot Mach-O, **NOT** its ability to execute on Orange Pi hardware.

## NOT confirmed

- No completed XNU bootstrap, kernel scheduler start, or iOS userland on A733.
- GIC timer, storage, IOKit framebuffer, touch and Wi-Fi remain unverified.
- A Qualcomm Xiaomi kernel packed into a payload is NOT adapted and must not be flashed.

## Current source and plans

- `a733/` preserves the verified Stage0 v3 code and the experimental v4 source.
- `a733/xnu-a733-firstboot.patch`: five guarded XNU source changes for MPIDR, A733 identity and early HDMI. It is a preliminary overlay, **not** a full platform port.
- The HDMI mapping at `0xBBF11000` crosses a 32-MiB mapping boundary; the initial XNU console is deliberately restricted to **1024×224** until the full driver exists.
- A733 macOS CI applies the overlay after upstream XNU patches; the final Mach-O must pass `a733/tools/audit_a733_macho.py`.
- Upstream patch series through `0126` has Xiaomi SM6225 modem/Wi-Fi code. `modem=1` and `wifi=1` must remain disabled for A733.
- XNU first execution/panic visible on HDMI is the next milestone; there is no flash-ready candidate yet.

See `a733/V4-XNU.md` for address bounds and safety assumptions. Do not risk the user's sole boot card.

## Successful A733 packaging CI

- `A733XNU1` is a board-tagged payload format, rejected by old Stage0 and rejecting legacy Xiaomi payloads in new Stage0.
- `a733/tools/package_xnu_a733.py` statically audits the Mach-O before it packs the board-tagged payload.
- XNU CI now adds `package-a733`: Linux Stage0 build, complete A733 payload and the actual Stage0 validator. The artifact is **not approved for flashing** until physical memory/boot protocol questions are resolved.

## One-shot test artifact ready (still no hardware XNU execution)

- Commit `e4054fecc069aea6ef07902b2b0e72724d286160` passed both macOS
  XNU build/static audit and Linux Stage0 + real payload validation:
  [run 39298193231](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39298193231).
- The next bundle build also includes a compiled
  `a733-xnu-one-shot.scr` alongside `stage0.uimg`, `a733-xnu.payload` and
  the ADT. Script filenames match these exact binaries.
- All existing U-Boot/SD autostart files must stay untouched. The owner has
  only **one** SD card: first confirm `mmc 0:1`, existing device tree and
  interactive U-Boot access. Never flash or overwrite `boot.scr`.
- The static vendor DTB previously reported only 512 MiB; whether U-Boot's
  `bootm` FDT fixup exposes usable A733 high DRAM needs a **board
  observation**, not guesswork. Stage0 will refuse unsafe RAM.
- Follow [TEST-XNU-RU.md](TEST-XNU-RU.md) for the supervised one-shot
  procedure. No claim that real XNU has booted.

- Final **bundle with compiled U-Boot `.scr` passed all CI jobs** on
  [run 39299998464](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39299998464),
  commit `3b6131f46785561351a16f77b88e47bc4acc4bef`. Artifact ID
  `12211572340`, `a733-firstboot-EXPERIMENTAL-no-flash` (14-day retention).
  Stage0 source tests, macOS XNU compile/audit, Linux packer/validator and
  `mkimage -l` all passed. Physical XNU execution still unverified.

## Real-board AutoBoot v2 diagnostic and hex fix (2026-10-19)

- The owner flashed a 64-MiB experimental auto-SD image based on the v59
  bootloader. U-Boot on the **physical Orange Pi 4 Pro** displayed:
  `V4 SHIM LOADED` (17000 bytes), `FDT LOADED` (626816 bytes),
  `XNU PAYLOAD LOADED` (17159328 bytes), then
  `Sorry, I could not convert "...d4a0>"` and
  `EXPERIMENTAL BOOT STOPPED`.
- This is **not an XNU crash**. U-Boot's FDT integer parser rejected the bare
  hex output from `setexpr` within an `<...>` cell list. The script now
  explicitly prefixes `0x` for both ${filesize} in arithmetic and
  ${a733_end} in the FDT cell value. A new auto-SD candidate is built with
  this fix, but its physical XNU handoff is still untested.
- The SD/U-Boot/ext4 and artifact paths are confirmed operational. Next
  photo should reveal whether the patched FDT property passes and whether
  Stage0 reaches its A76/XNU diagnostic.

## Physical AutoBoot v3: first XNU code execution (2026-10-19)

- The board displayed the Stage0 portrait HDMI page and `XNU: JUMP`; on the same HDMI display, XNU's early unrotated exception console printed the full AArch64 register dump.
- The photographed values include `PC=0xfffffe00074a925c`, `ESR=0x96000006`, `FAR=0x220`, `x0=0`. Symbolication against the **exact macOS CI kernel artifact** from run `39299998464` locates `PC` in `_current_percpu_base + 0xC`: a load from `current_thread()->machine.pcpu_data_base`, with a null current-thread pointer. This could be either the primary failure or a second fault during early exception handling.
- **XNU instruction execution is now demonstrated, but XNU has not successfully bootstrapped.** This is not an iOS userland boot.
- AutoBoot v4 keeps the working loader and adjusts only XNU's console renderer to show 24 compact lines instead of 12 within the same safe 1024x224 HDMI scanout. Kernel compile and payload packaging passed on [XNU run 39317422418](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39317422418); Stage0 tests passed on [run 39317422221](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39317422221). Physical v4 still untested.

## Physical v14: successful userspace syscall round-trip (2026-10-20)

- macOS XNU, static PID1, and 8-MiB populated HFSX root compiled and packed on [CI run 39431933051](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39431933051), commit `96767d3`.
- Real board HDMI photographs confirm BSD initialization, `hfs: mounted A733PID1 on device b(1, 0)`, and `execve returned errno=0 for /sbin/launchd` (our test binary, **not** Apple's launchd).
- Logs show `syscall enter 20`, `AFTER_SY_CALL syscall=20 errno=0`, `AFTER_AUDIT_EXIT syscall=20`, `syscall exit 20 errno=0 result=1`, then `syscall enter 5`. This **proves a getpid userspace → kernel → userspace round-trip** on the board.
- `open` syscall 5 prints `BEFORE_AUDIT_ENTER` and `BEFORE_SY_CALL` but not `AFTER_SY_CALL`. The stall is in the handler path; `__pthread_testcancel`, allocation, vnode lookup and devfs are not yet distinguished. One A76 core remains enabled. SMP is deferred.
- v15 source adds PID1-only tracepoints through `open`, `openat_internal`, `open1`, `vn_open_auth`, and `namei`, plus a read-only test open of the HFS+ `/sbin/launchd` before `/dev/console`. [CI run 39464210361](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39464210361) passed the complete kernel/userspace/payload pipeline. An offline-verified 64-MiB SD IMG was assembled by replacing only the payload in a copy of v14 (SHA-256 `975ad79943b246ddbcbeeee9f574fa33c4cf8a9e433a772eac104353666ecdd5`); **v15 still needs a real-board test**. Preserve the known-working v14 ZIP and the existing SD/U-Boot layout.

## microSD root driver source (2026-10-22, NOT board-tested)

- `a733/xnu-a733-sdmmc.patch` (CI `9999m`): `bsd/dev/a733_sdmmc.c`, read-only polled PIO for SMHC0
  `0x04020000` ("allwinner,sunxi-mmc-v5p3x" per the Orange Pi vendor DT), CCU `0x02002000` read only
  (SMHC0 clock `+0xd00`, BGR `+0xd0c`). Re-identifies the card, CMD17/CMD18, MBR/GPT partition 2 with an
  HFS+ header check, `rd=sdroot0`. Details, expected HDMI lines and the planned card layout:
  [SDMMC-ROOT-RU.md](SDMMC-ROOT-RU.md).
- `mkadt_a733.py --sdmmc` adds `/a733-sdmmc`; `package_xnu_a733.py --sdroot` adds
  `rd=sdroot0 unentitled_ios_sim_launch=1` and refuses RAM disk, `rootrw=1`, missing `cpus=1`, or a
  cmdline that mkpayload would truncate.
- Host checks only: helper/unit tests (gcc + clang), kernel-part `-fsyntax-only -Werror` against
  XNU-signature stubs, `git apply --check` on the exact CI tree. The macOS workflow refuses a kernel
  without the `A733 SD: sdroot0 ready, read-only PIO` marker. v22 (`rd=md0`) is unchanged for rollback.
- Real XNU build with the driver: CI run 39674728308 SUCCESS (commit dfb6b21; the first run 39673536036
  failed on broken `\n` escapes in the IOFindBSDRoot hook, fixed). Branch renamed `topaz` -> `opi4pro`.
- Console log to the card: all console output (ring from boot) is written to a contiguous `A733LOG.TXT`
  on a FAT32 partition every 5 s and twice during a panic; the only write path is bounded to that file.
  PC tool `a733/tools/a733_sdlog.py` (prepare/show/clear). `a733sdlog=1` enables it with `rd=md0` too.
  FAT lookup verified on real mkfs.fat/mtools images; card writes NOT verified on the board.
- Card layout tool `a733/tools/a733_sdcard_layout.py` (plan/apply/write-ios/restore-mbr, Windows, admin):
  keeps MBR (boot loader at sector 16 forbids GPT) and partition 1 (0x80/0x83, sector 65536, **32 MiB**,
  not 64 MiB as written earlier); adds slot 2 HFS+ 0xAF at 196608 (16 GiB) and slot 3 FAT32 0x0C at
  33751040 (256 MiB) with a contiguous 64 MiB A733LOG.TXT; changes only bytes 462-493 of sector 0.
  Tested on a sparse full-card image (sfdisk, fsck.fat, mtools, the driver's FAT lookup) and in dry
  run against the real Disk 1.
- **2026-10-22 10:06, real card laid out by the owner** (`apply`, Disk 1): backup
  `card1-first64MiB-before-sdlayout-20261022-100638.bin` (sha256 e29744f3...addcd, kept locally, not in git);
  Windows now lists partition 2 (offset 96 MiB, 16 GiB, MbrType 175 = 0xAF) and partition 3 (E:, FAT32,
  label A733LOG, Healthy) with `A733LOG.TXT` 67108864 bytes, first line "prepared ... not written yet".
  Partition 1 (D:, 32 MiB) unchanged. iOS image not yet written; board not yet booted with this card.
- **2026-10-22, iOS root written by the owner** (`write-ios`, Disk 1): `ios16-gui-first.img` (16 GiB) in
  partition 2, read-back sha256 4b44e310...906fd.
- Partition 1 of the real card (read from the 10:06 backup, sectors 65536-131071, sha256 a5c418d3...b001)
  is **not** an XNU card: it autostarts **UEFI v59.2** (`/boot.scr` -> `/uefi_stage0.uimg`, 8 MiB), with no
  `/ios-a733`. Booting it does not run the sdroot kernel.
- New tool `a733/tools/a733_bootpart.py` (+ `tests/test_bootpart.py`, 10 tests, WSL Debian):
  `build` edits a copy of partition 1 with debugfs (adds `/ios-a733/stage0.uimg` and `a733-xnu.payload`,
  keeps the UEFI script as `/boot-uefi-v59.scr|.cmd`, installs `tools/sd-boot-xnu-sdroot.cmd` = the
  hardware-proven v22 script with new labels), reads every file back, `e2fsck -fn`; `write` (Windows admin)
  rewrites only partition 1 and only if the card's current partition 1 hashes to `--expect-current`.
- Prepared image `part1-sdroot.img` (local, not in git): sha256 26a5b6c6...1726; payload = CI run
  39738424472 (commit a59ab73) artifact `a733-SDROOT-EXPERIMENTAL-readonly-PIO`, sha256 eccb3d03...bd03;
  stage0 = v22's hardware-proven `stage0.uimg` (sha256 40605aeb...3ef3; stage0 sources unchanged since
  7f0ad30). `uefi_stage0.uimg` and the DTB are byte-identical to the card. **Not yet written to the card.**
- **2026-10-22 11:05, partition 1 switched to XNU sdroot on the real card** (`a733_bootpart.py write`,
  Disk 1, owner confirmed): wrote `part1-sdroot.img` (sha256 26a5b6c6...1726), read-back verified, exit 0.
  The replaced UEFI v59.2 partition is saved as `card1-part1-before-bootpart-20261022-110505.bin`
  (sha256 a5c418d3...b001, local). The card now holds: partition 1 = v22 stage0 + sdroot payload
  (CI 39738424472), partition 2 = iOS 16 root, partition 3 = A733LOG.TXT. **Board not yet booted.**
- **2026-10-22 board test #1 of the sdroot card (photos):** U-Boot loaded `stage0.uimg`, the DTB and the
  17101568-byte payload ("A733 SDROOT: bootm handoff to Cortex-A76"), Stage0 drew its screen and
  "XNU: INSTALLING KERNEL / HIGH RAM 0x100000000", then XNU printed `unexpected
  ../xnu/iokit/Kernel/IODeviceTreeSupport.cpp:579` forever. Cause: `/a733-sdmmc` had `interrupts = 161`
  with no interrupt controller on the parent path (root), so `IODTMapOneInterrupt` never terminates.
  The SD driver never ran (log file untouched). Fix: the node has no `interrupts` (informational `gic-spi`),
  `tests/test_adt.py` now requires an interrupt controller for every `interrupts` property.
- Repacked locally from the same CI kernel (run 39738424472, kernel sha256 e048b718...255f): the old ADT
  reproduces the card payload byte for byte (eccb3d03...bd03); the fixed ADT gives payload 2bd3a5aa...4128
  (differs only inside the ADT: the renamed property and the per-build random-seed). New partition 1 image
  `card1-part1-sdroot-v2-noirq-20261022.img` sha256 93309c82...58f1 (same boot.cmd, stage0 and UEFI files).
- **2026-10-22 11:17, v2 partition 1 written to the real card** (`a733_bootpart.py write`, owner
  confirmed): 93309c82...58f1, read-back verified; previous (v1, 26a5b6c6...) saved locally. Board test #2 pending.
- **2026-10-22 board test #2 (photos): the microSD driver works on the real board.** SMHC0 version
  0x2050530, module clock 100 MHz (CCU SMHC0_CLK 0x81000003), identification div 125, transfer div 2;
  OCR 0xc0ff8000 SDHC/SDXC, CID manufacturer 0x02 "SE064" rev 9.0, 59024 MiB, 4-bit bus;
  `A733 LOG: console saved to A733LOG.TXT on partition 3`; partition 2 found, `HFSX volume v5,
  4194304 x 4096 bytes, cleanly unmounted, journaled`; `sdroot0 ready`; `BSD root: sdroot0`.
  Then vfs_mountroot failed in a loop: `hfs: Initializing the journal (joffset 0x82000 sz 0x800000)`,
  journal header write -> `A733 SD: I/O error 30` (EROFS, read-only driver) -> hfs_mountfs 22 ->
  `cannot mount root, errno = 19`. Cause: the image's lastMountedVersion is 'H+Lx' (last mounted by
  Linux), so HFS runs hfs_late_journal_init, which for MNT_ROOTFS skips the read-only journal_is_clean
  path and recreates the journal. Fix without a kernel rebuild: `a733_sdcard_layout.py hfs-journal off`
  clears kHFSVolumeJournaledBit (attributes 0x80002100 -> 0x80000100) in both volume headers.
- The card's own A733LOG.TXT from test #2 (41748 bytes, 37 mount attempts) was read on the PC:
  **SD writes (CMD24/25, log file only) work on the real board.**
- **2026-10-22 11:53, `hfs-journal off` on the real card** (owner confirmed): sectors 196610 and 33751038,
  attributes 0x80002100 -> 0x80000100, read-back verified, old headers saved locally. Board test #3 pending.
- **2026-10-22 board test #3 (log read from the card, 16769 bytes): the iOS 16 root mounts and Apple
  launchd runs.** `hfs: mounted iOSRoot on device b(1, 0)`, `exec launchd`, libignition
  ("hello from launchd.1"; preboot lookup failed 25, continued), the dyld shared cache segments map
  (`not in trust cache` notices only), `com.apple.xpc.launchd ... Darwin Bootstrapper Version 7.0.0`,
  `entering ondemand mode`, boot task fsck skipped, then mount-phase-1: `mount_hfs: Read-only file
  system`, `mount: / failed with 1`, bindfs lookup of /private/preboot/<hash>/usr/standalone/firmware
  failed (2), `pid 3 exited ... exit 1`. The root must be writable.
- Driver: root writes with boot-arg `sdrw=1` (`sd_write_root`, bounded to partition 2 and never over the
  log file; all CMD24/25 still go through `sd_write_sectors`, which also refuses sector 0).
  `package_xnu_a733.py --sdroot --sdrw` adds `sdrw=1 rootrw=1`; CI packs the sdroot payload that way.
- **2026-10-22 14:49, partition 1 v3 (writable root) on the real card** (owner confirmed): CI run
  39771632443 (commit afd11f8, kernel sha256 6fda4d2d...f790, payload 2dd5f990...2896 with
  `sdrw=1 rootrw=1`, ADT without `interrupts`), v22 stage0 40605aeb...; image 8491aa0b...eab1,
  read-back verified; previous v2 (93309c82...) saved locally. Board test #4 pending.
- **2026-10-22 board test #4 (photo): the writable root works and launchd runs its boot tasks**
  (`prng_seedctl`: Doing boot task ...), then `launchd_cache_loader[22]`: `abort: Unable to find AMFI`
  -> launchd panic `exited -- exit reason namespace 7 subcode 0x1`. Same wall as upstream ios-sweet
  (root NOTES.md, boot 0038e/0039u): `launchd_unsecure_cache=1` skips the launchd.plist signature and
  AMFI checks and lets all boot tasks pass. The screen was flooded by the v14-v17 PID 1 kprintf traces.
- `package_xnu_a733.py --sdroot --sdrw` now also adds the upstream userland boot-args
  `launchd_unsecure_cache=1 ignition_level=1 wdt_test=no_user_checkin wdt=-1` and drops
  `-enable_kprintf_spam` (printf, A733 lines, launchd output and the card log are unaffected).
  Repacked locally from the CI 39771632443 kernel/ADT: the CI cmdline reproduces its payload
  byte for byte (2dd5f990...); the new payload 91c1fa88...92e6 differs only in the cmdline field.
  Partition 1 v4 `card1-part1-sdroot-v4-userland-20261022.img` sha256 b708f443...0ba5.
- Test #4 card log (39084 bytes, `ref` copy local): boot tasks mount-phase-1/2 (bindfs preboot/firmware
  and /private/var/hardware lookups fail, error 2, non-fatal), data-protection (seputil),
  finish-obliteration, detect-installed-roots, commit-boot-mode, restore-datapartition,
  init-with-data-volume, MSUEarlyBootTask, fips, keybag (keybagd), usermanagerd, dirs_cleaner,
  xpcroleaccountd, init_featureflags, auearlyboot, tzinit, finish-restore, finish-demo-restore,
  sysstatuscheck, prng_seedctl, then launchd_cache_loader ("Using default cache paths") -> AMFI abort.
- **2026-10-22 15:30, partition 1 v4 written to the real card** (owner confirmed): b708f443...0ba5,
  read-back verified; previous v3 (8491aa0b...) saved locally. Board test #5 pending.
- **2026-10-22 board test #5 (photos, still booting): iOS daemons run and the first real iOS frame shows.**
  With `launchd_unsecure_cache=1` launchd starts LaunchDaemons: lockdownd, configd, IOMFB_FDR_Loader,
  UserEventAgent, **backboardd**, locationd, runningboardd, powerd, tccd, identityservicesd, ... and the
  owner saw the **Apple logo on HDMI** (first iOS frame through AppleCLCD/IOSurface -> CPU path).
  Root writes work: `A733 SD: 640 MiB read from / 36 MiB written to the card, 0 retried errors`.
  Problems: console text painted over the iOS frame (fbcon draws directly into the scanned framebuffer and
  clears whole rows) and wrapped to the top instead of scrolling.
- `a733/xnu-a733-console-graphics.patch` (CI 9999n): the fbcon keeps a text copy and scrolls (newest line at
  the bottom); after the first real iOS frame (`a733_fbcon_graphics_frame` from a733_cpu_present) text is no
  longer drawn into the frame, only the 8-line log band is composited over its bottom from saved frame pixels
  (no damage, no accumulated darkening); a panic redraws the full text console; `a733fb_console=1` keeps the
  old full console over graphics. Host test `tests/test_console_graphics_patch.py` rebuilds the patched
  console code: scroll order, frame untouched above the band, band = darkened frame + text, panic text.
- **SD speed (driver):** the vendor v5p3x driver runs SDR modes with module clock = 2 x card clock and
  internal divider 0, so the card clock is module/2 (div 0) or module/(4 div). With the U-Boot module
  clock of 100 MHz the old transfer divider 2 gave only **12.5 MHz**. Now: identification div 63
  (397 kHz), Default Speed div 1 (25 MHz), then **High Speed** (CMD6 query/switch group 1 function 1,
  52M-table phases: cmd+data drive 180, sample phase 1) at div 0 = **50 MHz**, kept only if sector 0 reads
  back identical; any failure returns to 25 MHz. `sdhs=0` stays at Default Speed.
- **Second Cortex-A76:** `xnu-a733-smp-a76.patch` (9999o) lets SweetCPU accept MPIDR 0x700 (boot stays 0x600);
  `mkadt_a733.py --a76-pair` adds cpu1 (0x700, state "waiting", same cluster); XNU only uses it with
  `cpus=2` (`package_xnu_a733.py --cpus 2`, refused without the pair ADT). CI packs both
  `a733-xnu-sdroot.payload` (cpus=1) and `a733-xnu-sdroot-2cpu.payload` (cpus=2).
- **2026-10-22 board test #5 card log (2.45 MB, local copy):** backboardd never crashes; SpringBoard ran 57
  times and all 56 crashes are the same abort: `NSInternalInconsistencyException 'Failed to load bounding path
  bitmap data from the asset manager for asset name: BoundingPathBitmap-1125x2436-375x812-3.00x'`. SD: 0 errors.
  Upstream reached the SpringBoard home screen with a `/product` node copied from the real D22AP device tree
  (root NOTES.md, patch 0059); our ADT has the identity, display-scale 3 and home-button-type 2 but no /product.
- **2026-10-22 16:2x, partition 1 v5 (2x A76 cpus=2, SD High Speed, console fix) written to the real card**
  (owner confirmed): CI run 39783367967 (commit d169786), image d0140d68...9a2d, read-back verified;
  previous v4 (b708f443...) saved locally. A cpus=1 twin (d0498bcd...) is ready as fallback. Board test #6 pending.
- **/product from the real iPhone X device tree:** `Firmware/all_flash/DeviceTree.d22ap.im4p` (33719 bytes,
  CRC ok) fetched alone by range request (tools/remotezip.py) from Apple's
  `iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw` (updates.cdn-apple.com), IM4P payload LZFSE-decoded
  (Debian lzfse) to d22ap.adt (186084 bytes, sha256 9e670987...dbf1; Apple artifact, local only, NOT in git).
  `mkadt_a733.py --product-adt d22ap.adt` copies its /product (61 properties, e.g. artwork-device-subtype 2436,
  artwork-scale-factor 3, artwork-display-gamut P3; iBoot syscfg placeholders and phandle dropped, as upstream).
  Repacked from the CI 39783367967 kernel (CI ADT reproduces its 2cpu payload 34983a0d... byte for byte):
  partition 1 v6 `card1-part1-sdroot-v6-product-2cpu-20261022.img` 576dbdfb...3150 (cpus=2) and
  `-1cpu-` 12603bde...c408 (cpus=1).
- **2026-10-22 16:24, partition 1 v6 (v5 + iPhone X /product, cpus=2) written to the real card** (owner
  confirmed): 576dbdfb...3150, read-back verified; previous v5 (d0140d68...) saved locally. Board test #6 pending.
- **🎉 MILESTONE 2026-10-22 (board test #6, photo): iOS 16.7.16 Setup "hello" screen on the Orange Pi 4 Pro.**
  Partition 1 v6 (kernel CI 39783367967 + ADT with the real iPhone X /product, cpus=2, SD High Speed,
  console overlay). SpringBoard no longer aborts on BoundingPathBitmap; the HDMI panel shows the Setup
  "hello" animation, the status bar battery icon and the home indicator, rendered by backboardd through
  AppleCLCD/IOSurface -> CPU path; the console now only draws the 8-line log band at the bottom without
  damaging the frame. Second-A76 / High Speed confirmation pending the card log.
- Test #6 card log (208 KB): **second Cortex-A76 works** (`cpu=1 CPU_ON target=0x700 ... rc=0`,
  `cpu=1 mpidr=0x700 came alive; SGI1 OK`, `2/2 CPUs initialized`); **SD High Speed works**
  (`4-bit bus, High Speed 50000000 Hz`, 1409 MiB read / 30 MiB written, 0 retried errors).
  SpringBoard exec'd once and stayed up; `SWEET FB: 19000 swaps`; only driverkitd and PosterBoard
  crashed once; no panic.
- **USB touch screen (patch 9999p, `xnu-a733-usbtouch.patch`, ADT `--usb-touch`):** the HDMI display's
  touch is `wch.cn USB2IIC_CTP_CONTROL` 1a86:e5e3 (full speed, HID, interrupt IN 0x82, 64 bytes): report
  ID 1, 6 finger slots of tip/contact-id/X/Y(0..2048)/width, then scan time and contact count (descriptor
  and reports read on a PC, 2026-10-22). X runs along the 1024-pixel side. `bsd/dev/a733_usbtouch.c`
  powers USB1 (vendor sun60iw2 open_clock + passby, PHY tuning skipped), runs its OHCI polled with
  HCCA/ED/TD/buffers in the ADT `dma-reg` window 0x60000000 (OHCI DMA is 32-bit, XNU RAM is above
  4 GiB), enumerates root port 1 directly or behind one hub, re-enumerates after a replug, parses the
  HID descriptor and feeds `sweet_hid_touch()` after Stage0's portrait rotation (raw origin = portrait
  top-right) and the 1125x2436 -> 473x1024 letterbox. Boot-args `a733touch_swap/flipx/flipy=1` fix the
  raw axes, `a733usb=0` turns it off. Log lines start with `A733 TOUCH:`. Not tested on the board yet.
- **2026-10-22 19:32, partition 1 v7 (v6 + USB touch screen, cpus=2) written to the real card** (owner
  confirmed): kernel CI 39794332437 (commit 415dd69; CI ADT reproduces its 2cpu payload 63516538...
  byte for byte), ADT v6 + /a733-usb, image 7d3035ef...9b33, read-back verified; previous v6
  (576dbdfb...) saved locally. cpus=1 twin 62d9851f...3088 ready as fallback. Board test #7 pending.
- **🎉 2026-10-22 board test #7 (owner report): the display's USB touch screen works in iOS** with partition 1
  v7 (patch 9999p, default orientation, no axis boot-args). Card log not read yet (which USB 2.0 port,
  direct or behind a hub).
- Test #7 card log (current boot = first 6884 lines; the rest of the 64 MiB file is older text; local
  copy only): touch path `USB1 OHCI -> hub 1a40:0101 (4 ports, the black USB 2.0 pair) -> port 3 ->
  1a86:e5e3`, 150 touches delivered, default orientation correct. Problems: (1) the root was mounted
  **dirty and non-journaled** (test #6 was powered off by pulling power) and the kernel reported 703x
  `hfs_mark_inconsistent` (BlockMarkFreeInternal frees unallocated blocks) + `MapFileBlockC` - the
  volume needs fsck.hfsplus, and power-off without a journal or a clean shutdown keeps damaging it;
  (2) SpringBoard crash loop during Setup: 7x SIGSEGV pc 0x0, same lr 0x1deba058c (slide 0x4a068000),
  first one right after a tap - to re-check after fsck. SD: 0 errors; 2/2 CPUs; SWEET FB 3000 swaps.
- **Test #8 log (second boot after test #7, local copy):** 4157x `hfs_mark_inconsistent`, SpringBoard
  crash loop right at launch (26x SIGSEGV pc 0, same lr). Root cause of the damage: the HFS journal had
  been switched off (`hfs-journal off`, needed while the driver was read-only) and the board is powered
  off by pulling the plug. **2026-10-22: partition 2 restored from the clean `ios16-gui-first.img`
  (sha256 4b44e310..., read-back verified; owner confirmed) with the journal flag left ON** - with
  sdrw=1 XNU can now write the journal itself. Setup progress was lost with it.
- **Patch 9999q (`xnu-a733-cores-fb-power.patch`):** SweetCPU accepts the six Cortex-A55s (MPIDR
  0x000-0x500, ADT `--a55` after the A76 pair, so cpus=N takes A76s first; packager allows cpus=1..8);
  `a733_cpu_present()` scales in physical row order with sequential 64-bit stores (host test: identical
  pixels to the old loop) and presents at 30 Hz by default (`sweetfb_hz`); `bsd/dev/a733_power.c`
  (ADT `--power`): the board's power button through the PMICs on R_TWI0 (AXP8191 0x36 IRQ_STATUS2 0x49
  bits 5/6, AXP515 0x34 0x4b bits 5/4, polled 50 ms; short press = side button, hold 1.5 s adds volume
  up = "slide to power off"), PE_halt_restart -> PSCI SYSTEM_OFF/RESET after the log flush, CPU PLL
  report + timed loop. `serial=1` stays: XNU never uses the A733 UART; that boot-arg is the screen
  console, which also feeds the card log.
- **2026-10-22 22:22, partition 1 v8 (8 cores, 30 Hz scaler, power button, PSCI off) written to the card**
  (owner confirmed): kernel CI 39835724694 (commit 1e5c0de), ADT v7 + `--a55 --power`, cpus=8, image
  15b33e51...69dc, read-back verified; previous v7 (7d3035ef...) saved locally. Fallbacks: v8 cpus=4
  514c8a49...849d, cpus=2 a6567335...8ad8. iOS partition = clean image, journal on. Board test #9 pending.
- **Board test #9 (v8, cpus=8, photo):** `SWEET CPU: requested=8 selected=8`, then `cpu=2..7 NOT
  registered (IOKit matching timeout)` -> panic `CPU registration timeout` (before root mount, so the
  iOS volume was not touched). Cause: SweetCPU's personality is IONameMatch 'arm,cortex-a76' and the
  A55 nodes only said arm,cortex-a55. Fix in the ADT only (no kernel rebuild): A55 compatible =
  "arm,cortex-a55" "arm,cortex-a76" "ARM,v8". **22:43, partition 1 v8b (cpus=8) written** (owner
  confirmed): 45923d34...8151, read-back verified; cpus=4 twin 246ea5b8...a56f. Board test #10 pending.
- **Board test #10 (v8b, photo):** A55 matching fixed; then `SWEET CPU: cpu=2 NOT alive: PSCI CPU_ON
  rc=-4` (ALREADY_ON) for MPIDR 0x000: Stage0 had parked the boot A55 in WFE after starting the A76.
  Fix: Stage0 calls PSCI CPU_OFF there (WFE only if it fails; CI 39845482621 stage0 a83430df..., body
  dc9052e5..., one extra smc with 0x8400xxxx in the disassembly; the old CI stage0 body equals the card's
  v22 one, 68d2e755...), and mkadt lists 0x000 last so cpus=7 works with any Stage0.
  **23:05, partition 1 v8c (new Stage0, cpus=8) written** (owner confirmed): 7c16bb15...0117,
  read-back verified. Fallback v8c-olds0 cpus=7 (old Stage0): 5658cea6...fd81. Board test #11 pending.
- **Board tests #11 (v8c cpus=8) and #12 (v8c cpus=3), photos:** both froze right after `SWEET CPU:
  requested=N` with no panic - not even the boot-CPU / cpu=1 lines (in test #10 the same kernel had
  started the second A76). The only difference is the new Stage0: after its PSCI CPU_OFF of the boot
  A55, the next CPU_ON hangs inside the firmware with the only running core. **Stage0 CPU_OFF reverted**;
  0x000 stays last in the ADT and is not used. **23:3x, partition 1 v8c-olds0 (old Stage0, cpus=7:
  2x A76 + A55 0x100-0x500) written** (owner confirmed): 5658cea6...fd81. Board test #13 pending.
  The 8th core would need Stage0 to park 0x000 on a mailbox XNU can release (spin table), not CPU_OFF.
- **Board test #13 (v8c-olds0, cpus=7) card log (local copy):** all 7 cores up (`7/7 CPUs initialized`;
  A55 0x100-0x500 rc=0). **CPU clocks: A76 and A55 PLLs both 936 MHz, DSU 720 MHz** (`A733 CPU:`; timed
  loop ~506 iterations/us on the A76) - U-Boot's boot clock, while the vendor OPP table
  (sun60iw2p1-cpu-vf.dtsi) allows A76 1200 MHz / A55 1008 MHz at 800 mV for every chip bin and A76
  1608 MHz at <= 950 mV (DCDC3 = A76, DCDC5 = A55 + DSU; AXP8191 0x14 / 0x16, 0.5 V + 10 mV/code).
  Journal recreated on mount (`hfs: Initializing the journal`), volume clean, no SpringBoard crashes,
  datamigrator ran (no LastSystemVersion -> "iOS updated" screen). Power button works on AXP8191 (AXP515
  does not answer): side button and the volume-up chord reach SpringBoard, the slider appears, but no
  shutdown ever reached the kernel (no reboot/halt lines) - the slide did not complete; the owner used
  the PMIC 6 s hard-off.
- **Patch 9999r (`xnu-a733-cpufreq-setup.patch`):** vendor Linux cpufreq ported into `a733_power.c`:
  speed bin from the efuse (SID+0x24C, dvfs_bak over dvfs_ori, `vf_mapping_table`), the 24 MHz rows of
  `sun60iw2p1-cpu-vf.dtsi` embedded (A76 up to 1992 MHz, A55 up to 1800, DSU up to 1296 depending on the
  bin), AXP8191 DCDC3 (A76) / DCDC5 (A55 + DSU) raised before and lowered after the in-place PLL retune
  (`ccu_nkmp_set_rate`: N, update bit 26, lock bit 28), every step flushed to the card log first
  (`a733_sd_log_sync`); THS (0x02522000, vendor formula + efuse calibration) steps both clusters down above
  90 C, floor at 105 C, back up below 80 C. Boot-arg `a733cpufreq=0|1|2|3` (off / <=800 mV / <=950 mV /
  bin max, default 3). Triple press of the power button = `reboot_kernel(RB_HALT)` (clean unmount, then
  PSCI off). `a733_firstboot.c` (bsd_init hook after the root mount, before launchd): one-time Setup-skip
  preferences as upstream `sweet-root-tweaks.py` (purplebuddy, migration LastSystemVersion, SpringBoard
  watchdogs, cloud config, data ark if the upstream container exists) + Reduce Motion / Transparency,
  marker `/private/var/root/.a733-firstboot-v1`, boot-arg `a733setupskip=0|1|2`. ADT `--activation`:
  /chosen security tuple (0,0,1,1) for Hactivation. Screen 20 Hz.
