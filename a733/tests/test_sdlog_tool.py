#!/usr/bin/env python3
"""a733_sdlog.py against a model of sdlog_flush() in bsd/dev/a733_sdmmc.c."""
from __future__ import annotations

import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import a733_sdlog as tool  # noqa: E402

SECTOR = 512
BUF = 128 * SECTOR      # LOG_BUF_SECTORS


class KernelModel:
    """Same arithmetic as sdlog_flush(): sector-granular, marker, header."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.size = path.stat().st_size // SECTOR * SECTOR
        self.data_bytes = self.size - SECTOR
        self.console = bytearray()
        self.flushed = 0

    def write(self, sector: int, data: bytes) -> None:
        assert len(data) % SECTOR == 0 and 0 <= sector and (sector * SECTOR + len(data)) <= self.size
        with self.path.open("r+b") as f:
            f.seek(sector * SECTOR)
            f.write(data)

    def flush(self) -> None:
        total = len(self.console)
        start = self.flushed - self.flushed % SECTOR
        while True:
            off = start % self.data_bytes
            room = min(BUF, self.data_bytes - off)
            n = min(total - start, room)
            buf = bytearray(self.console[start:start + n])
            if start + n == total:
                buf += tool.MARK[:min(len(tool.MARK), room - n)]
            padded = max(SECTOR, -(-len(buf) // SECTOR) * SECTOR)
            buf += b" " * (padded - len(buf))
            self.write(1 + off // SECTOR, bytes(buf))
            start += n
            if start >= total:
                break
        wrapped = ", file WRAPPED (older text continues after the END line)" if total > self.data_bytes else ""
        head = (f"A733 XNU console log, Orange Pi 4 Pro. {total} bytes logged since boot{wrapped}.\n"
                "Find the line \"A733 LOG END\": the newest text is just above it.\n").encode()
        head = head[:SECTOR - 1].ljust(SECTOR - 1) + b"\n"
        self.write(0, head)
        self.flushed = total


def console_text(n: int, seed: int) -> bytes:
    rnd = random.Random(seed)
    out = bytearray()
    i = 0
    while len(out) < n:
        out += f"[{seed}:{i:06d}] A733 SD: line {rnd.randrange(10**6)}\n".encode()
        i += 1
    return bytes(out[:n])


class SdlogTool(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        tool.prepare(self.dir / tool.NAME, 1, False)
        self.path = self.dir / tool.NAME

    def test_prepare_layout_and_path_forms(self) -> None:
        data = self.path.read_bytes()
        self.assertEqual(len(data), 1 << 20)
        self.assertTrue(data.startswith(tool.PREPARED))
        self.assertTrue(all(data[i:i + SECTOR] == tool.BLANK_SECTOR for i in range(SECTOR, len(data), SECTOR)))
        self.assertEqual(tool.extract(data), ("", ["The board has not written to this file yet."]))
        self.assertEqual(tool.log_path(str(self.dir)), self.path)
        self.assertEqual(tool.log_path(str(self.path)), self.path)
        with self.assertRaises(SystemExit):
            tool.prepare(self.path, 1, False)

    def test_incremental_flushes_read_back_in_order(self) -> None:
        k = KernelModel(self.path)
        text = console_text(300_000, 1)
        pos = 0
        for step in (1, 77, 511, 512, 513, 40_000, 70_000, 189_000):
            k.console += text[pos:pos + step]
            pos += step
            k.flush()
            got, notes = tool.extract(self.path.read_bytes())
            self.assertEqual(got.encode(), bytes(k.console))
            self.assertEqual(notes, [])
        self.assertEqual(bytes(k.console), text[:pos])

    def test_wrapped_file_keeps_the_newest_text(self) -> None:
        k = KernelModel(self.path)
        text = console_text(3_500_000, 2)
        for i in range(0, len(text), 60_000):
            k.console += text[i:i + 60_000]
            k.flush()
        got, notes = tool.extract(self.path.read_bytes())
        self.assertTrue(text.endswith(got.encode()))
        self.assertGreater(len(got), k.data_bytes - 2 * len(tool.MARK) - SECTOR)
        self.assertTrue(any("wrapped" in n for n in notes))

    def test_second_boot_ignores_the_old_tail(self) -> None:
        k = KernelModel(self.path)
        k.console += console_text(400_000, 3)
        k.flush()
        k2 = KernelModel(self.path)             # next boot, file not cleared
        k2.console += console_text(5_000, 4)
        k2.flush()
        got, notes = tool.extract(self.path.read_bytes())
        self.assertEqual(got.encode(), bytes(k2.console))
        self.assertEqual(notes, [])

    def test_clear_keeps_size(self) -> None:
        k = KernelModel(self.path)
        k.console += console_text(10_000, 5)
        k.flush()
        tool.clear(self.path)
        data = self.path.read_bytes()
        self.assertEqual(len(data), 1 << 20)
        self.assertTrue(data.startswith(tool.PREPARED))


if __name__ == "__main__":
    unittest.main()
