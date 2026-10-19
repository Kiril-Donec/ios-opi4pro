# iOS / XNU on Orange Pi 4 Pro (Allwinner A733)

Experimental port of Apple's XNU 8796 (iOS 16 generation) to the **Orange Pi 4 Pro**, with an **Allwinner A733** (2 Cortex-A76 + 6 Cortex-A55).

**Status: XNU has NOT yet booted on the Orange Pi.** The Stage0 diagnostic screen has run on hardware, and a Cortex-A76 (MPIDR `0x600`) was reached via PSCI. An unmodified Xiaomi kernel is NOT suitable for A733 and must not be flashed.

## Repository layout

- [`a733/`](a733/) — our A733 Stage0, U-Boot scripts, tests, Apple Device Tree generator and guarded early-XNU patch.
- [`a733/V4-XNU.md`](a733/V4-XNU.md) — verified results, limitations, memory mapping and next steps.
- [`.github/workflows/xnu.yml`](.github/workflows/xnu.yml) — macOS build using the original XNU patch stack **plus the A733 first-boot overlay**, followed by a binary identity audit.
- [`.github/workflows/a733-stage0.yml`](.github/workflows/a733-stage0.yml) — Linux Stage0 compilation and host tests.
- [`xnu/patches/`](xnu/patches/) — upstream foundation kept intact for reproducibility.

The names **`topaz`**, **`sweet`**, and **`SWEET`** still occur in upstream Xiaomi drivers, XNU configuration and payload format. They are historical compatibility identifiers, **not the hardware target**. They will be replaced selectively as the actual A733 drivers are ported. In particular, do not enable `modem=1` or `wifi=1` on A733; these select Qualcomm-specific hardware paths.

## Build Stage0 sources

On Debian/Ubuntu with the AArch64 cross-toolchain:

```sh
cd a733
make test
make adt
make
make test-boot
```

The Stage0 `build/stage0.uimg` is for **development and diagnosis only**. It does not imply the real XNU kernel has booted. The A733 XNU artifact, even after it compiles and passes the static audit, still requires a separate non-destructive physical test.

## Origins

Based on [MakrSas/ios-topaz](https://github.com/MakrSas/ios-topaz), itself drawing on the [ios-sweet](https://github.com/dipa-studio/ios-sweet) XNU work. This fork is an independent experimental **Allwinner A733 board port**, not the original author's Xiaomi device.

**Important:** The owner has one working microSD card. Do not overwrite the card automatically or suggest that an untested boot image is safe.
