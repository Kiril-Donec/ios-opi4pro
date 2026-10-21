"""Read-only host tests for real iOS 16 userland preflight and safe staging."""
import importlib.util
import json
import plistlib
import struct
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "inspect_ios16_root.py"
spec = importlib.util.spec_from_file_location("iosroot", TOOL)
iosroot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iosroot)


def fake_macho(dylinker=None):
    # Synthetic TEST fixture. Not an Apple executable, never shipped to a device.
    cmds = b""
    if dylinker is not None:
        content = dylinker.encode() + b"\0"
        size = 12 + len(content)
        size = (size + 7) & ~7
        cmds += struct.pack("<3I", iosroot.LC_LOAD_DYLINKER, size, 12) + content.ljust(size - 12, b"\0")
    cmds += struct.pack("<4I", iosroot.LC_CODE_SIGNATURE, 16, 0, 0)
    header = struct.pack("<8I", iosroot.MH_MAGIC_64, iosroot.ARM64, 0, 2,
                         1 + int(dylinker is not None), len(cmds), 0, 0)
    return header + cmds


class RootPreflightTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name) / "root"
        self.root.mkdir()
        self.write("sbin/launchd", fake_macho("/usr/lib/dyld"))
        self.write("usr/lib/dyld", fake_macho())
        self.write("System/Library/xpc/launchd.plist",
                   plistlib.dumps({"LaunchDaemons": {"com.apple.test": {"Label": "com.apple.test"}}}))
        self.write("System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64", b"real-byte-test-fixture")
        self.write("System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64.01", b"extra-test-fixture")
        self.write("System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64.27.dylddata", b"data-test-fixture")
        self.write("System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64.28.dyldlinkedit", b"linkedit-test-fixture")
        self.write("System/Library/CoreServices/SystemVersion.plist",
                   plistlib.dumps({"ProductVersion": "16.7.16", "ProductBuildVersion": "20H392"}))

    def write(self, relative, blob):
        file = self.root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(blob)
        return file

    def test_collect_real_component_names_and_dylinker(self):
        result, paths = iosroot.analyze(self.root)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["ios_version"], "16.7.16")
        self.assertEqual(result["files"]["launchd"]["macho"]["dylinker"], "/usr/lib/dyld")
        self.assertTrue(result["files"]["launchd"]["macho"]["has_code_signature_command"])
        self.assertIn("dyld_shared_cache_arm64.01", result["files"])
        self.assertIn("dyld_shared_cache_arm64.27.dylddata", result["files"])
        self.assertIn("dyld_shared_cache_arm64.28.dyldlinkedit", result["files"])
        self.assertEqual(result["files"]["launchd_plist"]["launchd_job_count"], 1)
        self.assertEqual(len(paths), 7)
        self.assertTrue(result["fits_existing_16mib_md0"])
        self.assertFalse(result["complete_root"])

    def test_stage_refuses_overwrite_and_reproduces_exact_files(self):
        result, paths = iosroot.analyze(self.root)
        out = Path(self.t.name) / "stage"
        manifest = iosroot.stage_files(out, paths)
        self.assertEqual(len(manifest), 7)
        for relative, src in paths:
            self.assertEqual((out / relative).read_bytes(), src.read_bytes())
        self.assertTrue((out / "A733_PROBE_NOT_A_COMPLETE_IOS_ROOT.txt").exists())
        self.assertEqual(len(json.loads((out / "a733-probe-manifest.json").read_text())), 7)
        with self.assertRaises(FileExistsError):
            iosroot.stage_files(out, paths)

    def test_missing_cache_is_fatal(self):
        (self.root / "System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64").unlink()
        result, _ = iosroot.analyze(self.root)
        self.assertTrue(any("missing arm64 dyld shared cache" in x for x in result["errors"]))

    def test_untrusted_architecture_refused(self):
        self.write("sbin/launchd", b"NOT-A-REAL-MACHO")
        result, _ = iosroot.analyze(self.root)
        self.assertTrue(any("Mach-O" in x for x in result["errors"]))

    def test_symlink_escape_is_refused(self):
        target = self.root / "sbin/launchd"
        target.unlink()
        target.symlink_to(Path(self.t.name) / "outside-file")
        (Path(self.t.name) / "outside-file").write_bytes(fake_macho())
        result, _ = iosroot.analyze(self.root)
        self.assertTrue(any("escapes root" in x for x in result["errors"]))

    def test_oversize_is_reported_not_silently_packed(self):
        target = self.root / "System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64"
        with target.open("r+b") as f:
            f.truncate(iosroot.CURRENT_MD0_LIMIT + 1024)
        result, _ = iosroot.analyze(self.root)
        self.assertFalse(result["fits_existing_16mib_md0"])
        self.assertTrue(any("16-MiB" in x for x in result["warnings"]))

    def test_wrong_major_version_flagged(self):
        self.write("System/Library/CoreServices/SystemVersion.plist",
                   plistlib.dumps({"ProductVersion": "17.0"}))
        result, _ = iosroot.analyze(self.root)
        self.assertIn("not an iOS 16 system root", result["errors"])


if __name__ == "__main__":
    unittest.main()
