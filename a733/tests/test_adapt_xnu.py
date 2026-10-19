"""Exercise guarded CPU adaptation against minimal synthetic XNU snippets."""
import importlib.util
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

spec = importlib.util.spec_from_file_location("adapt", "tools/adapt_xnu_a733.py")
assert spec and spec.loader
adapt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapt)

with TemporaryDirectory() as temp:
    root = Path(temp)
    for rel, anchors in adapt.FIXES.items():
        file = root / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("\n".join(before for before, _ in anchors) + "\n")
    changes = adapt.prepare(root)
    assert len(changes) == 5
    for _, (before, after) in changes.items():
        assert before != after
    assert "0xBBF11000" in changes[root / "osfmk/arm64/sweet_early.c"][1]
    early = changes[root / "osfmk/arm64/sweet_early.c"][1]
    assert "#define EARLY_CELL_H (8u * EARLY_SCALE)" in early
    assert "for (unsigned int gy = 0; gy < 8; gy++)" in early
    assert "glyph[gy * 2]" in early
    assert "0xBA000000" in changes[root / "osfmk/arm64/start.s"][1]
    assert "0x1F11000" in changes[root / "osfmk/arm64/arm_vm_init.c"][1]
    patch = root / "a733-overlay.patch"
    patch.write_text(adapt.make_patch(root, changes))
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=root, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=root, check=True)
    for path, (_, after) in changes.items():
        assert path.read_text() == after
    subprocess.run(["git", "apply", "--reverse", "--check", str(patch)],
                   cwd=root, check=True)
    adapt.verify_layout()
    broken = root / "iokit/Kernel/arm/SweetCPU.cpp"
    broken.write_text("unexpected XNU revision")
    try:
        adapt.prepare(root)
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported XNU tree was silently accepted")

print("A733 XNU CPU patch anchoring and fail-closed behavior: PASS")
