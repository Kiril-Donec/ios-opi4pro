"""The CPU test must be explicit, read-only and independent of an XNU image."""
from pathlib import Path

s = Path("tools/sd-boot-a76-probe.cmd").read_text()
lines = [x.strip() for x in s.splitlines()]
assert sum(x.startswith("if ") for x in lines) == sum(x == "fi" for x in lines)
assert "fdt set /chosen a733,a76-probe <0x1>" in s
assert "xnu.payload" not in s
assert s.index("stage0-v4.uimg") < s.index("fdt set /chosen a733,a76-probe")
assert s.index("a733,a76-probe") < s.index("bootm ")
for op in ("mmc write", "saveenv", "ext4write", "fatwrite", "sf write"):
    assert op not in s.lower()
source = Path("src/xnu_boot.c").read_text()
assert 'fdt_chosen_u64(dt, "a733,a76-probe", &probe)' in source
assert 'const int has_start = !probe_only &&' in source
assert 'const int has_end = !probe_only &&' in source
assert 'fdt_chosen_u64(dt, "a733,xnu-payload-start", &start)' in source
assert 'fdt_chosen_u64(dt, "a733,xnu-payload-end", &end)' in source
assert 'fdt_chosen_u64(dt, "linux,initrd-start", &start)' not in source
ld = Path("linker.ld").read_text()
assert "__image_size = __secondary_stack_top - 0x41000000;" in ld, (
    "ARM64 Image header must cover the PSCI A76 secondary stack"
)
print("A76 CPU_ON isolated U-Boot probe is guarded and read-only: PASS")
