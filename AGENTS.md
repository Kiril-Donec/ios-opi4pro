# Working on iOS / XNU for Orange Pi 4 Pro (Allwinner A733)

- The target is Orange Pi 4 Pro (A733), **not** Xiaomi topaz / sweet. See `a733/NOTES.md` and `a733/V4-XNU.md` before changing boot code.
- Preserve the upstream XNU patch stack under `xnu/patches/`. Place our board-specific changes in `a733/`; the dedicated macOS workflow applies the board overlay last.
- Do not infer that a successful build or an XNU payload parser test proves the kernel has booted. The only verified hardware events are the Stage0 diagnostic screen and the A76 PSCI probe.
- One working microSD card only. Never flash, repartition, or change boot autostart without a device-specific backup and explicit user approval.
- Never feed an unadapted Qualcomm kernel to the A733 loader; audit the final Mach-O first.
- Keep source, tests and docs tracked. Never commit Apple binary artifacts, board dumps, serial numbers, built payloads, SD images, personal files, or private credentials.
- Keep `a733/NOTES.md` updated after milestones with precise commit SHAs, CI runs, and physical results.
- Root `NOTES.md` is inherited from the upstream Xiaomi project and is reference-only for the A733 port.
