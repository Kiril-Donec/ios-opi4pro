#!/usr/bin/env python3
"""Read-only audit of an A733 vendor FDT before attempting a real XNU boot.

Run against the exact DTB passed to stage0, not an unrelated online DTS.
No device access and no disk writes.  Fail closed on unknown layouts.
"""
import argparse
import struct
import zipfile
from dataclasses import dataclass, field
from pathlib import Path


FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9
RAM_BASE, RAM_SIZE = 0x100000000, 0x40000000
PAYLOAD_BASE, PAYLOAD_SIZE = 0x52000000, 128 * 1024 * 1024
GICD, GICR, TIMER_INTID = 0x03400000, 0x03460000, 27


@dataclass
class Node:
    name: str
    props: dict[str, bytes] = field(default_factory=dict)
    children: list["Node"] = field(default_factory=list)
    parent: "Node | None" = None

    def descendants(self):
        yield self
        for child in self.children:
            yield from child.descendants()

    def compatible(self, value: bytes) -> bool:
        return value in self.props.get("compatible", b"").split(b"\0")

    def cells(self, name: str, default: int) -> int:
        data = self.props.get(name)
        if data is None:
            return default
        if len(data) != 4:
            raise ValueError(f"bad {name} in {self.name}")
        return struct.unpack(">I", data)[0]


def be_cells(data: bytes, width: int) -> list[int]:
    if width <= 0 or len(data) % (width * 4):
        raise ValueError("bad FDT cell array")
    result = []
    for off in range(0, len(data), width * 4):
        value = 0
        for i in range(width):
            value = (value << 32) | struct.unpack_from(">I", data, off + i * 4)[0]
        result.append(value)
    return result


def reg_ranges(node: Node) -> list[tuple[int, int]]:
    if not node.parent or "reg" not in node.props:
        return []
    parent = node.parent
    addr = parent.cells("#address-cells", 2)
    size = parent.cells("#size-cells", 1)
    if not 1 <= addr <= 2 or not 1 <= size <= 2:
        raise ValueError("unsupported FDT address/size cell count")
    words = be_cells(node.props["reg"], 1)
    if len(words) % (addr + size):
        raise ValueError(f"bad reg for {node.name}")
    ranges = []
    for off in range(0, len(words), addr + size):
        base = 0
        length = 0
        for word in words[off:off + addr]:
            base = (base << 32) | word
        for word in words[off + addr:off + addr + size]:
            length = (length << 32) | word
        ranges.append((base, length))
    return ranges


def read_fdt(blob: bytes) -> tuple[Node, list[tuple[int, int]]]:
    if len(blob) < 40:
        raise ValueError("short FDT header")
    magic, total, struct_off, strings_off, rsv_off, version, _, _, strings_sz, struct_sz = \
        struct.unpack_from(">10I", blob)
    if magic != FDT_MAGIC or version < 17 or total > len(blob) or total < 40:
        raise ValueError("invalid FDT header")
    if (struct_off + struct_sz > total or strings_off + strings_sz > total or
            not 40 <= rsv_off < total):
        raise ValueError("FDT offset outside blob")
    strings = blob[strings_off:strings_off + strings_sz]
    structure = blob[struct_off:struct_off + struct_sz]
    reserved = []
    pos = rsv_off
    for _ in range(512):
        if pos + 16 > total:
            raise ValueError("unterminated memory reservation map")
        base, size = struct.unpack_from(">QQ", blob, pos)
        pos += 16
        if not base and not size:
            break
        reserved.append((base, size))
    else:
        raise ValueError("too many FDT reserved-memory entries")

    root = None
    stack = []
    off = 0
    while off + 4 <= len(structure):
        token = struct.unpack_from(">I", structure, off)[0]
        off += 4
        if token == FDT_BEGIN_NODE:
            end = structure.find(b"\0", off)
            if end < 0:
                raise ValueError("unterminated node")
            node = Node(structure[off:end].decode("ascii"), parent=stack[-1] if stack else None)
            off = (end + 4) & ~3
            if stack:
                stack[-1].children.append(node)
            elif root is not None:
                raise ValueError("multiple root nodes")
            else:
                root = node
            stack.append(node)
        elif token == FDT_END_NODE:
            if not stack:
                raise ValueError("unbalanced end node")
            stack.pop()
        elif token == FDT_PROP:
            if off + 8 > len(structure) or not stack:
                raise ValueError("invalid FDT property")
            length, nameoff = struct.unpack_from(">II", structure, off)
            off += 8
            if nameoff >= len(strings) or off + length > len(structure):
                raise ValueError("property outside FDT")
            end = strings.find(b"\0", nameoff)
            if end < 0:
                raise ValueError("unterminated property name")
            name = strings[nameoff:end].decode("ascii")
            stack[-1].props[name] = structure[off:off + length]
            off = (off + length + 3) & ~3
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            if stack or root is None:
                raise ValueError("unbalanced FDT tree")
            return root, reserved
        else:
            raise ValueError(f"unknown FDT token {token}")
    raise ValueError("missing FDT_END")


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[1] and b[1] and a[0] < b[0] + b[1] and b[0] < a[0] + a[1]


def audit(blob: bytes) -> list[str]:
    root, reserved = read_fdt(blob)
    nodes = list(root.descendants())
    memory = [r for n in nodes if n.props.get("device_type") == b"memory\0"
              for r in reg_ranges(n)]
    if not memory:
        raise ValueError("missing memory node")
    if not any(base <= RAM_BASE and base + size >= RAM_BASE + RAM_SIZE
               for base, size in memory):
        raise ValueError("XNU 1 GiB high-RAM slice is absent from FDT")
    if not any(base <= PAYLOAD_BASE and base + size >= PAYLOAD_BASE + PAYLOAD_SIZE
               for base, size in memory):
        raise ValueError("XNU payload RAM is absent from FDT")
    for node in nodes:
        if node.name == "reserved-memory":
            for child in node.children:
                reserved.extend(reg_ranges(child))
    for item in reserved:
        if overlaps(item, (RAM_BASE, RAM_SIZE)) or overlaps(item, (PAYLOAD_BASE, PAYLOAD_SIZE)):
            raise ValueError(f"XNU allocation overlaps reserved memory {item}")

    gics = [node for node in nodes if node.compatible(b"arm,gic-v3")]
    if len(gics) != 1 or len(reg_ranges(gics[0])) < 2:
        raise ValueError("missing or ambiguous GICv3")
    distributor, redistributor = reg_ranges(gics[0])[:2]
    if distributor[0] != GICD or redistributor[0] != GICR or redistributor[1] < 0xE2000:
        raise ValueError("GIC MMIO is different from stage0/ADT")

    cpus = [node for node in nodes if node.name == "cpus"]
    if len(cpus) != 1 or not any(n.compatible(b"arm,cortex-a76") and
                                n.props.get("reg") == b"\x00\x00\x00\x00\x00\x00\x06\x00"
                                for n in cpus[0].children):
        raise ValueError("A76 MPIDR 0x600 not found")

    timers = [node for node in nodes if node.compatible(b"arm,armv8-timer")]
    if len(timers) != 1:
        raise ValueError("missing or ambiguous architected timer")
    timer = timers[0]
    freq = timer.cells("clock-frequency", 0)
    ints = be_cells(timer.props.get("interrupts", b""), 1)
    if freq != 24_000_000 or len(ints) < 9 or ints[6] != 1 or 16 + ints[7] != TIMER_INTID:
        raise ValueError("architected timer frequency/PPI differs from ADT")
    return [
        f"RAM: {', '.join(f'{base:#x}+{size:#x}' for base, size in memory)}",
        f"reserved ranges: {', '.join(f'{base:#x}+{size:#x}' for base, size in reserved)}",
        f"GICD {distributor[0]:#x}; GICR {redistributor[0]:#x}+{redistributor[1]:#x}",
        f"A76 MPIDR 0x600; virtual timer INTID {TIMER_INTID}; counter {freq} Hz",
        "A733 planned XNU RAM/payload/GIC/CPU/timer: PASS (FDT-only)",
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", type=Path, help="raw board DTB or ZIP with DeviceTree/ board DTB")
    ap.add_argument("--live", action="store_true",
                    help="when given the v59 ZIP, inspect the expanded Linux FDT")
    args = ap.parse_args()
    if args.file.suffix.lower() == ".zip":
        with zipfile.ZipFile(args.file) as z:
            name = ("DeviceTree/live-expanded-fdt.dtb" if args.live else
                    "DeviceTree/sun60i-a733-orangepi-4-pro.dtb")
            data = z.read(name)
    else:
        data = args.file.read_bytes()
    for line in audit(data):
        print(line)


if __name__ == "__main__":
    main()
