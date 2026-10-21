# Orange Pi 4 Pro / Allwinner A733 — real iOS graphics, first bring-up

**Status 2026-10-21: SOURCE CANDIDATE, CI build and hardware tests not yet confirmed.**
Do not mistake this work for an already booting iOS SpringBoard.

## What this attempts

This is the **real Apple iOS graphics protocol**, not a SpringBoard clone.
The XNU tree already includes Sweet's built-in compatibility drivers:
- `IOCoreSurfaceRoot` / `SweetSurface` — backing and sharing actual `IOSurface` objects from CoreAnimation, ported from dipa-studio/ios-sweet and improved by MakrSas/ios-topaz;
- `AppleCLCD` / `IOMobileFramebuffer` — the kernel-visible display service used by `backboardd` and CoreAnimation.

`a733/xnu-a733-ios-framebuffer.patch` adds an **A733-specific CPU copy** to `AppleCLCD::present()`. It samples real iOS-provided BGRA IOSurface pixels on the **one enabled Cortex-A76**, scales a nominal iPhone X canvas `1125×2436` into a centered 473×1024 view, and rotates pixels clockwise to the hardware's already-proven **1024×600** HDMI framebuffer at `0xBBF11000`. It does **not** render any iOS icons, clocks, or UI of its own. The real iOS userland must provide all pixels.

The critical hardware isolation check is that `AppleCLCD::start()` does **not** map or touch the topaz Qualcomm MDP registers at `0x05e05000`/`0x05e02000` for the A733 framebuffer. The real XNU framebuffer mapping and the existing U-Boot HDMI timing are reused, rather than attempting any Allwinner display-register programming.

An eight-line kernel diagnostic overlay is drawn **after** each actual IOSurface frame, enabled by default and disabled with `a733fb_logs=0`. It shows the actual ring of recent console characters and darkens the background region; it is not an iOS UI. Known first-prototype limitation: the original framebuffer console can write between iOS frames, and complete layer rectangles/scaling/blending, alpha formats and coherency still require hardware validation.

## Safe activation

The `a733/tools/mkadt_a733.py` generator **does not publish a display nub by default** (unchanged v19 behavior). The optional `--ios-display` adds `/arm-io/disp0`, `device_type=display-subsystem`, `compatible=sweet,display`, `canvas-width=1125`, `canvas-height=2436`. That asks Apple's real graphics stack to find our `AppleCLCD` service. Never enable it on a kernel not containing the A733 overlay: an unguarded topaz build would access Qualcomm MMIO addresses inappropriate for the Orange Pi.

The XNU workflow builds the A733 graphics patch *after* the proven v17 PAN patches. Its packaging job generates **two independent configurations**:
- normal v19-compatible `a733-early.adt` (no display nub);
- experimental `a733-ios-display.adt` and `a733-xnu-ios-display.payload` (display nub present).

The experimental CI payload currently includes **the same 8-MiB test HFSX RAM-root / synthetic PID 1**. It does not contain the real iPhone X root filesystem or Apple launchd/backboardd; thus **no SpringBoard frame is expected even if the patched kernel boots**. It is only a safe first test that the new display service registers correctly and PID 1 continues. A 64-MiB flashable AutoBoot IMG has **not** yet been produced for this graphics candidate.

## Next actual milestones

1. Confirm macOS XNU compilation with `xnu-a733-ios-framebuffer.patch` and successful A733 dual-ADT packaging. Inspect driver start logs on real hardware before proceeding.
2. Confirm `AppleCLCD` registers on the A733 display node without accessing Qualcomm MDP/MMIO. Preserve working v19 as a rollback.
3. Prepare a **real, lawfully obtained iPhone X iOS 16 root/shared cache** as upstream topaz does, in suitable storage (8-MiB md0 is not enough).
4. Debug real `dyld`, Apple `launchd` and required daemons, then `backboardd`/CoreAnimation and SpringBoard. Address actual missing syscalls, Mach IPC, security requirements and IOKit services as errors arise.
5. Show and validate the first *genuine Apple-created frame* with kernel overlay and portrait transform. Improve performance, layer rectangles, memory coherency, and later actual touch/USB input.

No second Cortex-A76 or A55 core is enabled. Storage, modem, Wi-Fi, GPU, audio and touch drivers are not prerequisites to build the *graphics kernel ABI candidate*, though a real iOS root filesystem, process support and display service are prerequisites to seeing genuine SpringBoard.

See [MakrSas/ios-topaz](https://github.com/MakrSas/ios-topaz) for the upstream software rendering implementation. Hardware-specific Qualcomm display and touch code must NOT be copied to A733 unguarded.
