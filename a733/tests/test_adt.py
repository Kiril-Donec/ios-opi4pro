#!/usr/bin/env python3
"""Check our ADT writer; use ios-topaz parser when available."""
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import mkadt_a733 as hw  # noqa: E402

reference = Path(__file__).resolve().parents[2] / "ios-topaz" / "tools"
if reference.is_dir() and os.environ.get("A733_TEST_STANDALONE") != "1":
    sys.path.insert(0, str(reference))
    import adt  # noqa: E402
    parse = adt.parse
else:
    # Standalone fallback for a ZIP downloaded without an ios-topaz checkout.
    class Parsed:
        def __init__(self, props, children):
            self.props = props
            self.children = children

        @property
        def name(self):
            return self.props["name"].rstrip(b"\0").decode()

        def prop(self, key):
            return self.props.get(key)

    def parse(buf, off=0):
        nprops, nchildren = struct.unpack_from("<II", buf, off)
        off += 8
        props = {}
        for _ in range(nprops):
            name = buf[off:off + 32].split(b"\0")[0].decode()
            size = struct.unpack_from("<I", buf, off + 32)[0]
            props[name] = buf[off + 36:off + 36 + size]
            off += 36 + ((size + 3) & ~3)
        children = []
        for _ in range(nchildren):
            child, off = parse(buf, off)
            children.append(child)
        return Parsed(props, children), off


def main() -> None:
    blob = hw.build().serialize()
    root, end = parse(blob)
    assert end == len(blob)
    assert root.name == "device-tree"
    cpu = next(n for n in root.children if n.name == "cpus").children[0]
    assert int.from_bytes(cpu.prop("reg"), "little") == 0x600
    assert int.from_bytes(cpu.prop("timebase-frequency"), "little") == 24_000_000
    armio = next(n for n in root.children if n.name == "arm-io")
    gic = armio.children[0]
    assert int.from_bytes(gic.prop("virtual-timer-intid"), "little") == 27
    assert [n.name for n in armio.children] == ["gic"]
    assert b"xiaomi,sweet" not in root.prop("compatible")
    assert b"sweet,display" not in blob
    chosen = next(n for n in root.children if n.name == "chosen")
    assert int.from_bytes(chosen.prop("dram-base"), "little") == 0x100000000
    assert not any(n.name == "a733-sdmmc" for n in root.children)

    sd_root, end = parse(hw.build(sdmmc=True).serialize())
    sd = next(n for n in sd_root.children if n.name == "a733-sdmmc")
    reg = struct.unpack("<2Q", sd.prop("reg"))
    ccu = struct.unpack("<2Q", sd.prop("ccu-reg"))
    assert reg == (0x04020000, 0x1000), reg
    assert ccu == (0x02002000, 0x2000), ccu
    assert sd.prop("interrupts") is None and sd.prop("AAPL,interrupts") is None
    assert int.from_bytes(sd.prop("gic-spi"), "little") == 161
    assert sd.prop("compatible").rstrip(b"\0") == b"allwinner,sunxi-mmc-v5p3x"

    # IOKit maps every "interrupts" property at boot by walking interrupt
    # parents (IODTMapOneInterrupt). Without an "interrupt-controller" on
    # the way it loops forever printing "unexpected IODeviceTreeSupport.cpp:579"
    # (board test 2026-10-22, /a733-sdmmc had interrupts = 161).
    for variant in ({}, {"ios_display": True}, {"sdmmc": True}, {"ios_display": True, "sdmmc": True}):
        tree, _ = parse(hw.build(**variant).serialize())
        check_interrupt_parents(tree, [], variant)
    # Second A76 only on request; XNU needs a non-running state for secondaries.
    assert len(next(n for n in root.children if n.name == "cpus").children) == 1
    pair, _ = parse(hw.build(sdmmc=True, a76_pair=True).serialize())
    cpus = next(n for n in pair.children if n.name == "cpus").children
    assert [int.from_bytes(c.prop("reg"), "little") for c in cpus] == [0x600, 0x700]
    assert [int.from_bytes(c.prop("cpu-id"), "little") for c in cpus] == [0, 1]
    assert cpus[0].prop("state").rstrip(b"\0") == b"running"
    assert cpus[1].prop("state").rstrip(b"\0") == b"waiting"
    assert cpus[1].prop("cluster-type") == cpus[0].prop("cluster-type")
    print("A733 ADT round-trip: PASS")


def check_interrupt_parents(node, ancestors, variant) -> None:
    for key in ("interrupts", "AAPL,interrupts"):
        if node.prop(key) is not None:
            assert node.prop("interrupt-parent") is not None or any(
                a.prop("interrupt-controller") is not None and a.prop("#interrupt-cells") is not None
                for a in ancestors), f"{variant}: node {node.name} has {key} but no interrupt controller"
    for child in node.children:
        check_interrupt_parents(child, ancestors + [node], variant)


if __name__ == "__main__":
    main()
