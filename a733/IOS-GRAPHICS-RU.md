# Orange Pi 4 Pro / Allwinner A733 — real iOS graphics, first bring-up

**Status 2026-10-21: REAL A733 HARDWARE GRAPHICS INITIALIZATION CONFIRMED.** GitHub Actions [#39577962831](https://github.com/Kiril-Donec/ios-opi4pro/actions/runs/39577962831) compiled and packaged the kernel; the user subsequently photographed the AutoBoot v20 running on Orange Pi 4 Pro, including the exact AppleCLCD 'READY' message and v19 test PID1 successful heartbeat. **No actual SpringBoard or CoreAnimation IOSurface frame has yet been shown.**
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

The experimental CI payload currently includes **the same 8-MiB test HFSX RAM-root / synthetic PID 1**. It does not contain the real iPhone X root filesystem or Apple launchd/backboardd; thus **no SpringBoard frame is expected even if the patched kernel boots**. It is only a safe first test that the new display service registers correctly and PID 1 continues. An experimental full 64-MiB AutoBoot IMG has **now been built offline**, preserving the board-tested v19 U-Boot/Stage0 and exactly reusing its 8-MiB RAM-root.

## Exact testable AutoBoot v20 (offline validated, NOT hardware proven)

The image `ios-a733-xnu-autoboot-v20-ios-display-probe-20261021.img` was built using the exact 64-MiB physically tested v19 image as a base. The payload inside the ext4 `/ios-a733/a733-xnu.payload` was replaced with the CI-produced AppleCLCD kernel and `--ios-display` ADT, but the internal 8-MiB RAMDisk bytes were **copied directly from v19**, not from the macOS runner. One Cortex-A76 only; original Stage0 and first 32 MiB remain byte-for-byte identical.

- **IMG size:** 67,108,864 bytes; **SHA-256:** `97dfacf81fbedbbd1cbbaf713051e4126cb204f4e9a39bd110fcc824f76a008e`.
- Original physically tested v19 IMG SHA-256: `0edbf0f5d82bb81028fbbefa3b0f256ce1549101d79cd5302f26d6d8e0b08c64`.
- CI-signed XNU display payload SHA-256 (before copying tested v19 RAM root): `0432a3c7a6a8596d31ff8a198a87dad41c96b4de0b8bb7404ac001caf5717fc8`.
- **Embedded IMG payload SHA-256:** `3a540c351045aaee4751a835c2d96019f6ca5759104286ec92edb439198efa24`.
- RAM-root SHA-256 preserved exactly from v19: `157afca7b8fabac58acd4fb7e408e66843387fe0bb47da6427b6a7c80cb6ef3f`.
- Offline verification: actual graphics marker found in compiled kernel, display ADT entry present, full ext4 file readback exact, ext4 inode checksum and all group descriptor checksums valid, other ext4 boot files unchanged, first 32 MiB equal v19. No full `e2fsck` assertion.
- **Real hardware status: AppleCLCD initialization and basic XNU/PID1 regression tested, PASSED (photos 2026-10-21).** The photos do not test the real IOSurface present/copy/compositor path because the image contains no Apple userland producing frames.

### First hardware test

Flash only to a spare microSD card (or make a full backup first). Look for the exact kernel message:

```text
A733 FB: AppleCLCD IOSurface HDMI CPU path READY 1125x2436 -> 1024x600
```

Then find the unchanged v19 self-test message and heartbeats:

```text
A733 V19 PASS: mmap RW + mprotect RO + munmap
A733 init: still alive
```

The iOS display service may initialize earlier or later relative to the PID 1 messages. If there is a hang/panic, photograph its last lines and any ESR/FAR/ELR or IOKit errors. One or two clear photos are sufficient.

**No lock screen or real iOS graphical frame can appear yet** because this test image does not include Apple's actual `launchd`, `backboardd`, `SpringBoard` or the dyld shared cache. The first hardware test is only to establish that the real graphics bridge can register safely while the v19 userspace still runs.

---

## Real board v20 — 7 photographed HDMI states (21 October 2026)

**Confirmed on Orange Pi 4 Pro, not inferred from CI:**

- U-Boot loads Stage0, DTB and A733 XNU PID1 payload, then `bootm` hands off to Cortex-A76.
- Stage0 displays the existing portrait 600×1024 HDMI diagnostic and proceeds to install XNU.
- XNU reaches IOKit/BSD startup, reports `SWEET CPU: 1/1 CPUs initialized, SGI1 verified` and `SWEET SURF: IOCoreSurfaceRoot registered`.
- At the bottom of the kernel-init photographs the display service announces the **exact** line:

```text
A733 FB: AppleCLCD IOSurface HDMI CPU path READY 1125x2436 -> 1024x600
```

  In the [A733 graphics patch](xnu-a733-ios-framebuffer.patch), `AppleCLCD::start()` prints this only **after** `registerService()` for the A733 framebuffer. This supports the stronger finding that the `AppleCLCD` service started and registered on the real board, not just that its string exists inside the kernel.

- Later photographs clearly show `A733 V19 PASS: mmap RW + mprotect RO + munmap` and repeated `A733 init: still alive`, proving the original test PID 1 was reached and ran after graphics initialization. No fatal abort is shown.
- The earlier U-Boot/Linux handoff includes `[mmc]: MMC Device 2 not found`; since XNU and PID1 subsequently ran, that message is **not a boot blocker in this test**. The screen's cyclic framebuffer text console means a last printed line such as `NAMEI_COPY_ENTER` does not alone establish a hang.

**Not yet demonstrated:** any `AppleCLCD::present()` call with nonempty real `IOSurface` layers, correct compositing or scaling, logs over a real iOS frame, genuine Apple launchd/dyld, backboardd, SpringBoard, or iOS Lock Screen. Do not extrapolate the word READY into a working GUI.

Result: **v20 graphics service and v19 test-userspace regression PASSED on real hardware; actual iOS pixel presentation NOT TESTED.** This is an important independent milestone with v19 as preserved rollback.

---

## Next actual milestones

1. ~~Compile XNU with `xnu-a733-ios-framebuffer.patch`, package both ADT configurations, and confirm the `AppleCLCD` READY message on the Orange Pi 4 Pro.~~ **DONE**, CI run #39577962831 and seven physical-HDMI photos dated 21 October 2026.
2. **First actual iOS frame**: feed real Apple CoreAnimation/IOSurface userspace content into the registered A733 AppleCLCD and verify its CPU portrait copy, bounds, cache coherence, and diagnostic overlay. The source guard bypasses Qualcomm MMIO on A733; further real-device testing remains important. Preserve v19 as rollback.
3. Prepare a **real, lawfully obtained iPhone X iOS 16 root/shared cache** as upstream topaz does, in suitable storage (8-MiB md0 is not enough).
4. Debug real `dyld`, Apple `launchd` and required daemons, then `backboardd`/CoreAnimation and SpringBoard. Address actual missing syscalls, Mach IPC, security requirements and IOKit services as errors arise.
5. Show and validate the first *genuine Apple-created frame* with kernel overlay and portrait transform. Improve performance, layer rectangles, memory coherency, and later actual touch/USB input.

No second Cortex-A76 or A55 core is enabled. Storage, modem, Wi-Fi, GPU, audio and touch drivers are not prerequisites to build the *graphics kernel ABI candidate*, though a real iOS root filesystem, process support and display service are prerequisites to seeing genuine SpringBoard.

See [MakrSas/ios-topaz](https://github.com/MakrSas/ios-topaz) for the upstream software rendering implementation. Hardware-specific Qualcomm display and touch code must NOT be copied to A733 unguarded.
