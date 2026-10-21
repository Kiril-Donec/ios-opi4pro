"""Tests for safe extraction of real Apple IPSW OS/Cryptex files by D22AP identity."""
import importlib.util
import plistlib
import tempfile
import unittest
import zipfile
from pathlib import Path

mod_path = Path(__file__).resolve().parents[1] / "tools" / "extract_iphone_x_ipsw.py"
spec = importlib.util.spec_from_file_location("extractipsw", mod_path)
ipsw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ipsw)


class SelectIPSWTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.file = Path(self.t.name) / "sample.ipsw"

    def make_ipsw(self, *, board="d22ap", variant="Erase", missing=None,
                  unsafe=None, include_update=True):
        names = {"OS": "Firmware/os/test-os.dmg",
                 "SystemOS": "Firmware/cryptex/sysos.dmg",
                 "AppOS": "Firmware/cryptex/appos.dmg"}
        if missing:
            del names[missing]
        if unsafe:
            names["OS"] = unsafe
        m = {k: {"Info": {"Path": v}} for k, v in names.items()}
        identities = [{"Info": {"DeviceClass": board,
                                "RestoreBehavior": variant}, "Manifest": m}]
        if include_update:
            identities.insert(0, {
                "Info": {"DeviceClass": board, "RestoreBehavior": "Update"},
                "Manifest": {k: {"Info": {"Path": "Update/" + v}} for k, v in names.items()}})
        manifest = {"BuildIdentities": identities}
        with zipfile.ZipFile(self.file, "w") as z:
            z.writestr("BuildManifest.plist", plistlib.dumps(manifest))
            for p in names.values():
                if p.startswith("../"):
                    continue
                z.writestr(p, b"FAKE-DMG-NOT-APPLE")
            if include_update:
                for p in names.values():
                    if p.startswith("../"):
                        continue
                    z.writestr("Update/" + p, b"FAKE-UPDATE-DMG")
        return names

    def test_selects_d22ap_erase_not_update(self):
        names = self.make_ipsw()
        report, selected = ipsw.examine(self.file)
        self.assertEqual(selected, names)
        self.assertEqual(report["device"], "iPhone10,3 / D22AP")
        self.assertEqual(report["total_uncompressed_bytes"], 3 * len(b"FAKE-DMG-NOT-APPLE"))

    def test_extract_three_only_to_new_directory(self):
        self.make_ipsw()
        out = Path(self.t.name) / "extracted"
        _, selected = ipsw.examine(self.file)
        hashes = ipsw.extract(self.file, out, selected)
        self.assertEqual(set(hashes), set(ipsw.COMPONENTS))
        self.assertEqual(sorted(p.name for p in out.iterdir()),
                         ["AppOS.dmg", "OS.dmg", "SystemOS.dmg"])
        self.assertEqual((out / "OS.dmg").read_bytes(), b"FAKE-DMG-NOT-APPLE")
        with self.assertRaises(FileExistsError):
            ipsw.extract(self.file, out, selected)

    def test_missing_component_fails(self):
        self.make_ipsw(missing="AppOS")
        with self.assertRaisesRegex(ValueError, "no complete"):
            ipsw.examine(self.file)

    def test_wrong_board_fails(self):
        self.make_ipsw(board="n104ap")
        with self.assertRaisesRegex(ValueError, "no complete"):
            ipsw.examine(self.file)

    def test_only_update_refused(self):
        self.make_ipsw(variant="Update", include_update=False)
        with self.assertRaisesRegex(ValueError, "Erase"):
            ipsw.examine(self.file)

    def test_traversal_fails(self):
        self.make_ipsw(unsafe="../escape.dmg")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            ipsw.examine(self.file)


if __name__ == "__main__":
    unittest.main()
