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
