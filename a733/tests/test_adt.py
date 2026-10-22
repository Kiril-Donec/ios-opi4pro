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
    for variant in ({}, {"ios_display": True}, {"sdmmc": True}, {"ios_display": True, "sdmmc": True},
                    {"sdmmc": True, "usb_touch": True},
                    {"sdmmc": True, "usb_touch": True, "a76_pair": True, "a55": True, "power": True}):
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
    # Six A55s after the A76 pair (cpus=N takes the A76s first), one XNU cluster.
    all8, _ = parse(hw.build(sdmmc=True, a76_pair=True, a55=True).serialize())
    cpus = next(n for n in all8.children if n.name == "cpus").children
    assert [int.from_bytes(c.prop("reg"), "little") for c in cpus] == [0x600, 0x700, 0, 0x100, 0x200, 0x300,
                                                                       0x400, 0x500]
    assert [int.from_bytes(c.prop("cpu-id"), "little") for c in cpus] == list(range(8))
    assert [c.name for c in cpus] == [f"cpu{i}" for i in range(8)]
    assert all(c.prop("state").rstrip(b"\0") == b"waiting" for c in cpus[1:])
    # every core must match SweetCPU's IONameMatch 'arm,cortex-a76' (board test #9)
    assert all(b"arm,cortex-a76" in c.prop("compatible").split(b"\0") for c in cpus)
    assert all(c.prop("compatible").startswith(b"arm,cortex-a55\0") for c in cpus[2:])
    assert len({c.prop("cluster-type") for c in cpus}) == 1 and len({c.prop("cluster-id") for c in cpus}) == 1
    try:
        hw.build(sdmmc=True, a55=True)
    except ValueError:
        pass
    else:
        raise AssertionError("--a55 without the A76 pair must be refused")
    # Power node: R_TWI0, R_CCU, CPU PLL; polled, no interrupts.
    pw_root, _ = parse(hw.build(sdmmc=True, power=True).serialize())
    pw = next(n for n in pw_root.children if n.name == "a733-power")
    assert struct.unpack("<2Q", pw.prop("twi-reg")) == (0x07083000, 0x400)
    assert struct.unpack("<2Q", pw.prop("rccu-reg")) == (0x07010000, 0x400)
    assert struct.unpack("<2Q", pw.prop("cpupll-reg")) == (0x08870000, 0x4000)
    assert pw.prop("interrupts") is None
    check_product()
    assert not any(n.name == "a733-usb" for n in sd_root.children)
    usb_root, _ = parse(hw.build(sdmmc=True, usb_touch=True).serialize())
    usb = next(n for n in usb_root.children if n.name == "a733-usb")
    assert struct.unpack("<2Q", usb.prop("reg")) == (0x04200000, 0x1000)
    assert struct.unpack("<2Q", usb.prop("ccu-reg")) == (0x02002000, 0x2000)
    dma = struct.unpack("<2Q", usb.prop("dma-reg"))
    # 32-bit OHCI DMA, page aligned, clear of BL31 (0x48000000-0x49000000),
    # the payload (0x52000000) and the framebuffer, and below XNU's RAM.
    assert dma == (0x60000000, 0x10000), dma
    assert dma[0] % 4096 == 0 and dma[0] + dma[1] <= 0x100000000
    assert dma[0] + dma[1] <= hw.FRAMEBUFFER and dma[0] >= 0x58000000
    assert usb.prop("interrupts") is None
    print("A733 ADT round-trip: PASS")


def raw_node(props, children=b"", nchildren=0) -> bytes:
    """ADT node bytes; props = (name, value, placeholder flag)."""
    out = struct.pack("<II", len(props), nchildren)
    for name, value, flag in props:
        out += name.encode().ljust(32, b"\0") + struct.pack("<I", len(value) | (flag << 31))
        out += value + bytes((-len(value)) & 3)
    return out + children


def check_product() -> None:
    import tempfile
    product = raw_node([("name", b"product\0", 0), ("AAPL,phandle", b"\x01\0\0\0", 0),
                        ("artwork-device-subtype", struct.pack("<I", 2436), 0),
                        ("artwork-scale-factor", struct.pack("<I", 3), 0),
                        ("cover-glass", b"syscfg/CGSp\0", 1)])
    tree = raw_node([("name", b"device-tree\0", 0), ("compatible", b"D22AP\0iPhone10,3\0", 0)],
                    raw_node([("name", b"chosen\0", 0)]) + product, 2)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp, "d22ap.adt")
        path.write_bytes(tree)
        props = hw.read_product(path)
        assert [n for n, _ in props] == ["artwork-device-subtype", "artwork-scale-factor"], props
        root, _ = parse(hw.build(sdmmc=True, product=props).serialize())
        node = next(n for n in root.children if n.name == "product")
        assert int.from_bytes(node.prop("artwork-device-subtype"), "little") == 2436
        assert not any(n.name == "product" for n in parse(hw.build().serialize())[0].children)
        path.write_bytes(tree.replace(b"D22AP\0", b"D201AP"))
        try:
            hw.read_product(path)
        except ValueError:
            pass
        else:
            raise AssertionError("a non-D22AP tree must be refused")


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
