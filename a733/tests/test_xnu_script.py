"""Fail-closed static checks; only a real v59 U-Boot can validate syntax."""
from pathlib import Path

s = Path("tools/sd-boot-xnu-experimental.cmd").read_text()
lines = [line.strip() for line in s.splitlines()]
assert sum(line.startswith("if ") for line in lines) == sum(
    line == "fi" for line in lines
), "every command failure must close its guard"
for forbidden in ("mmc write", "ext4write", "fatwrite", "saveenv", "sf write"):
    assert forbidden not in s.lower(), f"accidental persistent write: {forbidden}"
assert s.index("/ios-a733/stage0.uimg") < s.index("/ios-a733/a733-xnu.payload")
assert s.index("/ios-a733/a733-xnu.payload") < s.index("setexpr a733_end")
assert s.index("setexpr a733_end") < s.index("fdt set /chosen a733,xnu-payload-start")
assert s.index("fdt set /chosen a733,xnu-payload-end") < s.index("bootm ")
assert "0x52000000" in s and "0x43000000" in s and "0x42000000" in s
assert "setexpr a733_end 0x52000000 + 0x${filesize}" in s
assert "a733,xnu-payload-end <0x0 0x${a733_end}>" in s
assert "<0x0 ${a733_end}>" not in s
assert "while true; do sleep 1; done" in s
print("experimental XNU boot script guarded and non-persistent: PASS")
