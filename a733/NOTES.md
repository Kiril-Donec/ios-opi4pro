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

- No execution of any XNU instruction on A733.
- No verified real XNU boot-args handoff, GIC timer, storage, IOKit framebuffer, touch, Wi-Fi or iOS userland.
- A Qualcomm Xiaomi kernel packed into a payload is NOT adapted and must not be flashed.

## Current source and plans

- `a733/` preserves the verified Stage0 v3 code and the experimental v4 source.
- `a733/xnu-a733-firstboot.patch`: five guarded XNU source changes for MPIDR, A733 identity and early HDMI. It is a preliminary overlay, **not** a full platform port.
- The HDMI mapping at `0xBBF11000` crosses a 32-MiB mapping boundary; the initial XNU console is deliberately restricted to **1024×224** until the full driver exists.
- A733 macOS CI applies the overlay after upstream XNU patches; the final Mach-O must pass `a733/tools/audit_a733_macho.py`.
- Upstream patch series through `0126` has Xiaomi SM6225 modem/Wi-Fi code. `modem=1` and `wifi=1` must remain disabled for A733.
- XNU first execution/panic visible on HDMI is the next milestone; there is no flash-ready candidate yet.

See `a733/V4-XNU.md` for address bounds and safety assumptions. Do not risk the user's sole boot card.
