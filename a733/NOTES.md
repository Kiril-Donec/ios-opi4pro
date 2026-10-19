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
