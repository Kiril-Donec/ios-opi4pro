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
