# SD images: manual and automatic stage0 diagnostics

## Visible boot stages (v3)

`ios-a733-stage0-auto-v3-sd.img` restores the `screen_char` command present
in the working v59 boot script, before selecting serial,vidconsole. Its exact
effect on this bootloader has not been verified; its omission is a difference,
not a proven explanation of the previous black screen.

There are now visible `[1/4]` through `[4/4]` U-Boot messages, separated by
short pauses, and a `STAGE0 ENTERED` framebuffer marker before the full panel.
The marker may be brief if drawing completes successfully. A marker does not
prove later stages or iOS work. Even no marker cannot distinguish failure to
execute from a failed video path; UART may still be needed in that case.

## Header/cache correction (v2)

`ios-a733-stage0-auto-v2-sd.img` adds the inner 64-byte ARM64 Image header
(`ARM\x64` signature), including a branch over the header, fixed-load offset
and runtime size covering BSS/stack. The outer legacy ARM uImage wrapper
remains compatible with the vendor v59 flow. The code selects SP_ELx and is
built with general registers only, avoiding inherited FP/SIMD-enable state.
After painting, cache lines are cleaned to PoC and barriers completed so
non-coherent display scanout can see CPU-written pixels. No MMU tables,
display controllers, storage or firmware are reconfigured by stage0.

These address concrete source gaps; they do NOT establish the exact cause
of an earlier hardware failure. The direct entry/cache instructions and the
inherited framebuffer are still subject to a real board test. A black screen
may still require checking the boot stage rather than reflashing blindly.

This is NOT an iOS installer, XNU kernel or working operating system.
The image preserves the vendor SPL/U-Boot/BL31 container from our EDK2 v59
64 MiB image and its original 32 MiB ext4 partition layout. No EDK2 is started.

The `ios-a733-stage0-auto-sd.img` variant automatically loads stage0 and the
board FDT and calls vendor bootm/BL31. If either load fails it prints an error
and waits without executing stage0. This variant was explicitly requested
after discussing the experimental RAM/framebuffer access risks. Its screen
parameters match the v59 source, but direct boot/cache behaviour remains
untested on hardware. Power-cycle if the test hangs; it has no storage writes.

The older `ios-a733-stage0-manual-sd.img` is unchanged and remains available.
In manual mode the replacement boot.scr prints a warning and waits. Use Ctrl+C for
the U-Boot prompt. Stage0 is deliberately NOT run automatically: the inherited
framebuffer candidate 0xBBF11000 has not been verified on the actual board.
Check the live scanout address, BGRA format, 1024x600 geometry, stride 1024,
memory reservation and cache assumptions before executing any stage0 code.
If they differ, rebuild with corrected values; do not run the current payload.

Only AFTER those hardware checks, the project's original manual sequence is:

```
setenv stdout serial,vidconsole
setenv stderr serial,vidconsole
ext4load mmc 0:1 0x42000000 /ios-a733/stage0.uimg
ext4load mmc 0:1 0x43000000 /dtb/allwinner/sun60i-a733-orangepi-4-pro.dtb
bootm 0x42000000 - 0x43000000
```

These addresses/device numbers follow the previous v59 flow, not a new live
hardware verification. Check U-Boot's actual device mapping before loading.
The Apple ADT is included as reference only; stage0 does not consume it.
The payload paints a diagnostic then halts, not a graphical iOS session.

Writing this image to an SD card erases its previous partition table/data.
The build does not write any card. Keep a backup and choose the target carefully.
The filesystem is ext4: Windows Explorer will not show it as a normal USB disk.

Rebuild on Linux/WSL from the project root:

```
make test all adt
python3 tools/package_sd.py --base /path/to/orangepi4pro_edk2_v59_gmac_diag_flashable.img --output /path/to/NEW-stage0-manual.img
python3 tools/package_sd.py --autostart --base /path/to/orangepi4pro_edk2_v59_gmac_diag_flashable.img --output /path/to/NEW-stage0-auto.img
```

The packager refuses an existing output, validates both legacy image CRCs,
checks the AArch64 ELF, reads payloads back from ext4, runs e2fsck read-only,
and checks the original first 32 MiB is unchanged. No physical block device
is accessed. Hardware boot remains untested.

The linker currently warns about one RWX LOAD segment. This existing bare-metal
prototype has no MMU/page-permission setup; that warning is not fixed or hidden
by packaging. Do not treat host tests as proof that boot/display will work.
