# ios-a733

> **Latest status (2026-10-20):** XNU boots on the physical Orange Pi 4 Pro,
> mounts an HFSX RAM disk and runs a test PID 1. v14 demonstrated a successful
> `getpid()` syscall return (PID 1); the next `open()` call stalls. The v15
> XNU/PID1/payload builds now pass CI and add diagnostics to isolate that stall;
> the v15 image still needs a hardware test. **The historical v4 notes
> below are retained for reference**, not the current boot status. The
> experimental userspace binary is not a full iOS installation.

Experimental native XNU/iOS 16 bring-up for Orange Pi 4 Pro (Allwinner A733).

**Historical v4 status (superseded):** the v3 stage0 screen diagnostic has booted on the physical board
and driven HDMI in the rotated 600x1024 view (photos from 2026-10-19).
The v4 source adds an **experimental cross-compiled, not hardware-verified
XNU handoff path**.
This *v4 snapshot* was **not yet an XNU or iOS boot**; the current v14 hardware tests now reach XNU PID 1. See [V4-XNU.md](V4-XNU.md) for its
new code, build requirements, experiments and limitations.

SD diagnostic builds and the v2 ARM64-header/cache corrections are described
in `SD-IMAGE.md`. This includes an explicitly requested automatic test variant;
it remains an experimental screen test, not an iOS system image.

## Hardware assumptions

The v59 EDK2 archive dated 2026-10-19 supplies the provisional values:

- U-Boot hand-off via legacy `bootm` and BL31, with a separate FDT.
- UART0 at `0x02500000` (not required for the stage-0 screen test).
- EDK2 framebuffer candidate `0xBBF11000`, BGRA, 1024x600, stride 1024.
- Monitor physically rotated clockwise by 90 degrees.
- Portrait coordinates 600x1024. A 1125:2436 iPhone X panel fits as
  473x1024, centered between black bars.

**Hardware warning:** the owner already confirmed v3 uses the inherited
U-Boot framebuffer to draw the screen on this board (photo). The v59
EDK2 video startup is still incomplete and a different firmware revision
could change the physical scanout address. The v4 A76/PSCI path has not
been run on real hardware and may hang; use the spare-SD test image only.
See `TEST-A76-RU.md` for the verified test package and safe boot steps.

## Build

Run `make test` on Linux to verify framebuffer geometry without hardware.
Run `make preview` to produce a synthetic portrait diagnostic screen PNG.
To create the bootable diagnostic on a Linux cross-build host, install an
AArch64 bare-metal-capable GNU toolchain (for Debian/Ubuntu:
`gcc-aarch64-linux-gnu`, `binutils-aarch64-linux-gnu`) and run `make`.
The result, `build/stage0.uimg`, contains no iOS or XNU kernel.

The `make adt` command produces a provisional 3284-byte early Apple Device
Tree for the A76 core (MPIDR 0x600), GICv3 and the 24 MHz ARM timer. The
initial XNU-managed memory range is 0x100000000..0x13fffffff. This only
describes intended hardware resources; it cannot boot a working kernel yet.

Load the image only from an **interactive** U-Boot prompt, following the
v59 method and after checking the candidate framebuffer address:

```text
setenv stdout serial,vidconsole
setenv stderr serial,vidconsole
ext4load mmc 0:1 0x42000000 /ios-a733/stage0.uimg
ext4load mmc 0:1 0x43000000 /dtb/allwinner/sun60i-a733-orangepi-4-pro.dtb
bootm 0x42000000 - 0x43000000
```

The legacy image relocates itself to `0x41000000`. Keep the stage0 image
separate from U-Boot and normal Debian boot files; do **not** replace
`boot.cmd`, SPL, boot partitions or any existing kernel.

Stage0 paints a phone-shaped diagnostic panel, reports the FDT address and
current exception level, then stops. It writes neither storage nor firmware.
Reboot with power cycle. The framebuffer code depends on a physically rotated
monitor; for counterclockwise rotation change the enum in `src/boot.c`.

The 8x16 text glyph data in `src/font.h` is copied from the
`ios-topaz/shim/font.h` generated console-font table. Source references:
[ios-topaz](https://github.com/MakrSas/ios-topaz) and
[ios-sweet](https://github.com/dipa-studio/ios-sweet).

## Future milestones

1. Confirm live HDMI framebuffer / orientation and memory reservation.
2. Reuse the ios-sweet XNU early-boot patches. Initial A733 memory, GIC,
   timer and CPU topology are described in the provisional Apple Device
   Tree; XNU platform patches and PSCI core handoff still need implementing.
3. Achieve XNU first log / panic on the rotated screen.
4. Bring up SD/MMC root device and the iOS 16 userland separately.

The initial stage0 v4 CPU_ON/loader implementation exists and cross-compiles,
but steps 2 through 4 still need hardware and XNU-specific verification.
