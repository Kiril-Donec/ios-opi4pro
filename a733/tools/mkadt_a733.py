#!/usr/bin/env python3
"""Create an early-boot Apple Device Tree for the Allwinner A733.

This is a *bring-up hypothesis*, not a working iOS ADT. It intentionally
includes only the boot CPU (Cortex-A76 MPIDR 0x600) and no SD/MMC driver.
The shim must hand off to that core with PSCI before this tree is usable.
"""
import argparse
import hashlib
import os
import struct
from dataclasses import dataclass, field
from pathlib import Path

SOC_BASE = 0x02000000
GIC_DISTRIBUTOR = 0x03400000
GIC_REDISTRIBUTORS = 0x03460000
VIRTUAL_TIMER_INTID = 27
CNTFRQ = 24_000_000
BOOT_CPU_MPIDR = 0x600

# Conservative early-boot slice in the top 1 GiB of the 4-GiB bank.
# This excludes U-Boot / BL31 / the candidate 0xBBF11000 framebuffer, but
# the range still needs validation against the live firmware memory map.
XNU_RAM_BASE = 0x100000000
XNU_RAM_SIZE = 0x40000000
FRAMEBUFFER = 0xBBF11000
FRAMEBUFFER_SIZE = 1024 * 600 * 4


def u32(*values: int) -> bytes:
    return struct.pack("<" + "I" * len(values), *values)


def u64(*values: int) -> bytes:
    return struct.pack("<" + "Q" * len(values), *values)


def cstr(value: str) -> bytes:
    return value.encode("ascii") + b"\0"


@dataclass
class Node:
    name: str
    props: list[tuple[str, bytes]] = field(default_factory=list)
    children: list["Node"] = field(default_factory=list)

    def serialize(self) -> bytes:
        props = [("name", cstr(self.name)), *self.props]
        out = bytearray(u32(len(props), len(self.children)))
        for name, value in props:
            if len(name.encode()) > 32:
                raise ValueError("ADT property name is longer than 32 bytes")
            out.extend(name.encode().ljust(32, b"\0"))
            out.extend(u32(len(value)))
            out.extend(value)
            out.extend(bytes((-len(value)) & 3))
        for child in self.children:
            out.extend(child.serialize())
        return bytes(out)


def build() -> Node:
    chosen = Node("chosen", [
        ("dram-base", u64(XNU_RAM_BASE)),
        ("dram-size", u64(XNU_RAM_SIZE)),
        ("random-seed", os.urandom(64)),
        ("debug-enabled", u32(1)),
        ("display-scale", u32(3)),
        ("firmware-version", cstr("ios-a733-stage0")),
        ("system-firmware-version", cstr("ios-a733-stage0")),
        ("boot-manifest-hash", hashlib.sha384(b"A733 experimental boot").digest()),
        ("crypto-hash-method", cstr("sha2-384")),
        ("unique-chip-id", u64(0x4137330000000001)),
        ("chip-id", u32(0x8015)),
    ], [
        Node("memory-map"),
        Node("asmb", [("lp-sip0", u64(0x6F)), ("lp-sip1", u32(1))]),
    ])

    cpu = Node("cpu0", [
        ("device_type", cstr("cpu")),
        ("compatible", cstr("arm,cortex-a76") + cstr("ARM,v8")),
        ("reg", u32(BOOT_CPU_MPIDR)),
        ("cpu-id", u32(0)),
        ("cluster-id", u32(0)),
        ("cluster-type", u32(0)),
        ("die-cluster-id", u32(0)),
        ("cluster-core-id", u32(0)),
        ("state", cstr("running")),
        ("timebase-frequency", u32(CNTFRQ)),
        ("fixed-frequency", u32(CNTFRQ)),
        ("peripheral-frequency", u32(CNTFRQ)),
        ("clock-frequency", u32(2_000_000_000)),
    ])
    cpus = Node("cpus", [
        ("#address-cells", u32(1)),
        ("#size-cells", u32(0)),
    ], [cpu])

    gic = Node("gic", [
        ("compatible", cstr("arm,gic-v3")),
        ("interrupt-controller", b""),
        ("virtual-timer-intid", u32(VIRTUAL_TIMER_INTID)),
        ("reg", u64(GIC_DISTRIBUTOR - SOC_BASE, 0x10000,
                    GIC_REDISTRIBUTORS - SOC_BASE, 0x100000)),
    ])
    arm_io = Node("arm-io", [
        ("device_type", cstr("sweet-io")),
        ("compatible", cstr("sweet-io") + cstr("arm-io")),
        ("#address-cells", u32(2)),
        ("#size-cells", u32(2)),
        ("ranges", u64(0, SOC_BASE, 0x100000000 - SOC_BASE)),
    ], [gic])

    # Keep the A733 DT intentionally smaller than topaz's: the upstream
    # AppleCLCD matches "sweet,display" and expects Qualcomm MDP/DSI
    # registers. Advertising that device on Allwinner would load a driver
    # against unrelated SoC MMIO. The direct early-fb console below remains
    # usable for first kernel entry/panic diagnostics, without a display kext.

    return Node("device-tree", [
        ("compatible", cstr("D22AP") + cstr("iPhone10,3") +
         cstr("allwinner,a733") + cstr("AppleARM")),
        ("model", cstr("iPhone10,3")),
        ("target-type", cstr("D22")),
        ("target-sub-type", cstr("D22AP")),
        ("manufacturer", cstr("Apple Inc.")),
        ("#address-cells", u32(2)),
        ("#size-cells", u32(2)),
    ], [
        chosen,
        Node("defaults", [("no-effaceable-storage", u32(1))]),
        cpus,
        arm_io,
        Node("sweet-fbcon", [
            ("reg", u64(FRAMEBUFFER, FRAMEBUFFER_SIZE)),
            ("width", u32(1024)),
            ("height", u32(600)),
            ("stride", u32(4096)),
        ]),
        Node("buttons", [
            ("home-button-type", u32(2)),
            ("opposed-power-vol-buttons", u32(1)),
        ]),
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = build().serialize()
    args.output.write_bytes(data)
    print(f"A733 early ADT: {len(data)} bytes -> {args.output}")
    print("MPIDR 0x600 / GICD 0x03400000 / GICR 0x03460000 / vtimer 27")
    print("EXPERIMENTAL: A76 PSCI verified; A733 XNU source rebuild still required")


if __name__ == "__main__":
    main()
