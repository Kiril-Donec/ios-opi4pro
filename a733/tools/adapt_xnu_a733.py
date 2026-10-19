#!/usr/bin/env python3
"""First-boot CPU and early HDMI adaptation of *already patched* ios-topaz XNU.

This intentionally does NOT claim the remainder of its Qualcomm drivers work
on Allwinner A733. The default --check is read-only; --apply changes only
strictly anchored files and retains .pre-a733 backups.

The A733 scanout starts at 0xBBF11000, close to a 32-MiB boundary. SWEET's
early identity/final framebuffer mapping covers ONE 32-MiB block, so only the
first 224 of 600 native scanlines may be touched by the early console.
Later full framebuffer mapping is a separate driver bring-up task.
"""

import argparse
import difflib
from pathlib import Path


FIXES = {
    "iokit/Kernel/arm/SweetCPU.cpp": [
        (
            "if ((cpu->phys_id >> 8) > 1 || (cpu->phys_id & 0xff) > 3 ||",
            "if (cpu->phys_id != 0x600 ||",
        ),
        (
            'OSSymbol::withCStringNoCopy("Kryo 260")',
            'OSSymbol::withCStringNoCopy("Cortex-A76")',
        ),
        (
            "topology->boot_cpu->phys_id != 0x100",
            "topology->boot_cpu->phys_id != 0x600",
        ),
        (
            "expected boot MPIDR 0x100",
            "expected boot MPIDR 0x600",
        ),
    ],
    "iokit/KernelConfigTables.cpp": [
        (
            "'IONameMatch'     = 'xiaomi,sweet';",
            "'IONameMatch'     = 'allwinner,a733';",
        ),
        (
            "'IONameMatch'     = 'qcom,kryo470';",
            "'IONameMatch'     = 'arm,cortex-a76';",
        ),
    ],
    "osfmk/arm64/start.s": [
        (
            "MOV64\tx0, (0x9c000000 + 2368 * 4320)",
            "MOV64\tx0, (0xBBF11000 + 192 * 4096)",
        ),
        (
            "mov\t\tx4, #4320",
            "mov\t\tx4, #4096",
        ),
        (
            "MOV64\tx10, 0x9c000000",
            "MOV64\tx10, 0xBA000000",
        ),
    ],
    "osfmk/arm64/sweet_early.c": [
        (
            "static volatile uint32_t *early_fb = (volatile uint32_t *)(uintptr_t)0x9c000000;",
            "static volatile uint32_t *early_fb = (volatile uint32_t *)(uintptr_t)0xBBF11000;",
        ),
        ("#define EARLY_WIDTH 1080u", "#define EARLY_WIDTH 1024u"),
        ("#define EARLY_HEIGHT 2400u", "#define EARLY_HEIGHT 224u"),
        ("#define EARLY_STRIDE (4320u / 4)", "#define EARLY_STRIDE (4096u / 4)"),
        ("#define EARLY_SCALE 2u", "#define EARLY_SCALE 1u"),
        # A real-board abort dumps more than twelve lines of registers and
        # scrolls the original fault description off the clipped HDMI area.
        # Compress consecutive scanlines with an OR so thin horizontal
        # strokes survive; taking every second row alone rendered the
        # crash dump as unreadable blocks on the physical monitor (v4).
        ("#define EARLY_CELL_H (16u * EARLY_SCALE)",
         "#define EARLY_CELL_H (8u * EARLY_SCALE)"),
        ("for (unsigned int gy = 0; gy < 16; gy++) {",
         "for (unsigned int gy = 0; gy < 8; gy++) {"),
        ("(glyph[gy] & (1u << gx))",
         "((glyph[gy * 2] | glyph[gy * 2 + 1]) & (1u << gx))"),
    ],
    "osfmk/arm64/arm_vm_init.c": [
        (
            "*slot = 0x9c000000ULL | ARM_TTE_VALID | ARM_TTE_TYPE_BLOCK |",
            "*slot = 0xBA000000ULL | ARM_TTE_VALID | ARM_TTE_TYPE_BLOCK |",
        ),
        (
            "sweet_early_relocate(SWEET_EARLY_FB_VA);",
            "sweet_early_relocate(SWEET_EARLY_FB_VA + 0x1F11000ULL);",
        ),
    ],
    "osfmk/arm/cpu_common.c": [
        # The first hardware abort is an access to address 0x220 inside
        # current_percpu_base(): current_thread() is still NULL at entry.
        # On the single boot A76, offset zero addresses the master per-CPU
        # section until a first thread installs machine.pcpu_data_base.
        (
            "return current_thread()->machine.pcpu_data_base;",
            "thread_t thread = current_thread();\n"
            "\treturn thread ? thread->machine.pcpu_data_base : 0;",
        ),
    ],
}


def verify_layout() -> None:
    """A memory proof for the deliberately clipped 32-MiB early window."""
    framebuffer, stride, native_height = 0xBBF11000, 4096, 600
    block_size = 32 * 1024 * 1024
    block = framebuffer & ~(block_size - 1)
    assert block == 0xBA000000
    assert (framebuffer - block) == 0x1F11000
    assert (framebuffer + 224 * stride) < block + block_size
    assert framebuffer + native_height * stride > block + block_size
    # Marker bar: 21 marks * 48 px and 32 lines of height, inside 1024x224.
    assert 21 * 48 <= 1024
    assert 192 + 32 == 224
    assert (224 - 32) // 8 == 24


def prepare(root: Path) -> dict[Path, tuple[str, str]]:
    """Produce full replacements only if every expected anchor occurs once."""
    verify_layout()
    edits = {}
    for rel, changes in FIXES.items():
        path = root / rel
        old = path.read_text()
        new = old
        for before, after in changes:
            count = new.count(before)
            if count != 1:
                raise ValueError(f"{path}: expected one anchor {before!r}, found {count}")
            new = new.replace(before, after, 1)
        edits[path] = old, new
    return edits


def make_patch(root: Path, edits: dict[Path, tuple[str, str]]) -> str:
    """Produce a git-apply-compatible overlay, relative to the XNU root.

    We deliberately do not edit upstream `ios-topaz` patches: the overlay can
    be installed as the last patch in an isolated A733 CI build instead.
    """
    chunks = []
    for path, (old, new) in edits.items():
        rel = path.relative_to(root).as_posix()
        chunks.append(f"diff --git a/{rel} b/{rel}\n")
        chunks.extend(difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile=f"a/{rel}", tofile=f"b/{rel}", n=3,
        ))
    return "".join(chunks)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("xnu_root", type=Path)
    action = ap.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--check", action="store_true")
    action.add_argument("--emit-patch", type=Path, metavar="OUTPUT")
    args = ap.parse_args()
    changes = prepare(args.xnu_root)
    if args.emit_patch:
        result = make_patch(args.xnu_root, changes)
        args.emit_patch.write_text(result)
        print(f"A733 git patch: {args.emit_patch} ({len(result)} bytes)")
    elif args.apply:
        for path, (old, new) in changes.items():
            # Refuse to overwrite an existing backup: never hide a previous edit.
            backup = path.with_name(path.name + ".pre-a733")
            if backup.exists():
                raise SystemExit(f"backup exists, no edits made: {backup}")
        for path, (old, new) in changes.items():
            path.with_name(path.name + ".pre-a733").write_text(old)
            path.write_text(new)
            print(f"adapted: {path}")
    else:
        print("A733 CPU/IOKit XNU anchors match: PASS (no edits)")
    print("NOTE: early framebuffer is limited to 224 lines; no A733 driver or board boot verified")


if __name__ == "__main__":
    main()
