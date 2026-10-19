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
    print("A733 ADT round-trip: PASS")


if __name__ == "__main__":
    main()
