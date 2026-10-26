"""Protect reviewed assets and unchanged camera-tested capture behavior; these tests do not exercise hardware."""
import hashlib
from pathlib import Path
import struct
import unittest


ASSETS = Path(__file__).resolve().parents[1] / "advanced" / "internal-drive-a"

# Trusted reviewed bytes; only backup wrapper identity/runtime gates changed in 0.7.0.
# Never regenerate these expectations automatically when payloads change.
EXPECTED_SHA256 = {
    "usb.console": "2b19515c1ee1515adc54d58c62cac67679ad3493185cddfe92e5872a5a8527f3",
    "backup.autoexec.ash": "3721a8b33d9c7b2631030df90969482e09bfe836a1d3dbaee02bfc7cf832d470",
    "bt-nand-backup.sh": "5492a73791eedf4ede299bf5c407cb5dd4beaf3b71c1b64edc585aab73e9072e",
    "nb-mtd-readonly": "81a849c7863b9024d73e9195be06ffefd64eb5a28811c619d20c53f9814fcaf7",
    "nb-mtd-readonly.sha256": "a1b7fadcbe25e2f2c64ee1389083f45febd04b4dd63d19cec0081f443d8c1aad",
    "nb-mtd-readonly.c": "77055e64a359601745023875141cb615d1af8dd487a04f1c8b0e7105466cea46",
    "build-nb-mtd-readonly.sh": "2a81168cab971302cfa59e03d1959f0a4718ebc3a9df733f9a4696481160914c",
    "dry-run.autoexec.ash": "f4156bf5047427bd713d0da65299c65c3b78b774195a667ada3c0ba99e603891",
    "format-a-once.autoexec.ash": "a1b6e0d61727a797d795a761e26bc6a24ef10222c6e9234b96921a11bad19c45",
    "persistence.autoexec.ash": "3be8cfa85083666b5230ab8ca88dddc671f600dba9455a6ad89e64c6f9d9cbf4",
    "bt-persistence-capture.sh": "8196a3f846c1771bedd6ddc975aab15438c084a34141dbe3a7136fedf360b837",
}


class AdvancedAssetTests(unittest.TestCase):
    def test_backup_capture_body_stays_identical_to_hardware_tested_wrapper(self):
        text = (ASSETS / "bt-nand-backup.sh").read_bytes()
        body = text[text.index(b'for path in "$sd"/*;'):]
        self.assertEqual(hashlib.sha256(body).hexdigest(), "cf80cf582b5f4baa1e6bbb1d054c70ffed34a47419fc2e832a72b57416e5bd66")

    def test_assets_match_reviewed_bytes_and_build_provenance(self):
        for name, expected in EXPECTED_SHA256.items():
            with self.subTest(asset=name):
                path = ASSETS / name
                self.assertTrue(path.is_file(), name)
                self.assertFalse(path.is_symlink(), name)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

    def test_manifest_covers_exactly_the_frozen_assets(self):
        self.assertEqual(
            {path.name for path in ASSETS.iterdir()},
            set(EXPECTED_SHA256) | {"SHA256SUMS"},
            "asset directory must not acquire unmanifested captures or other files",
        )
        lines = (ASSETS / "SHA256SUMS").read_text(encoding="ascii").splitlines()
        recorded = {}
        for line in lines:
            digest, name = line.split("  ")
            self.assertEqual(Path(name).name, name)
            self.assertNotIn(name, recorded, "duplicate manifest entry")
            recorded[name] = digest
            self.assertEqual(hashlib.sha256((ASSETS / name).read_bytes()).hexdigest(), digest)
        self.assertEqual(recorded, EXPECTED_SHA256)

    def test_helper_adjacent_manifest_names_only_the_helper(self):
        self.assertEqual(
            (ASSETS / "nb-mtd-readonly.sha256").read_text(encoding="ascii"),
            EXPECTED_SHA256["nb-mtd-readonly"] + "  nb-mtd-readonly\n",
        )

    def test_assets_do_not_include_private_paths_or_an_active_hook(self):
        self.assertFalse((ASSETS / "autoexec.ash").exists())
        forbidden = (b"/Users/", b"GitHubForks/", b"docs/evidence/", b"/tmp/622gw-linux-analysis/")
        for name in (*EXPECTED_SHA256, "SHA256SUMS"):
            with self.subTest(asset=name):
                data = (ASSETS / name).read_bytes()
                for private_path in forbidden:
                    self.assertNotIn(private_path, data)

    def test_helper_is_bounded_elf32_arm_static_executable(self):
        data = (ASSETS / "nb-mtd-readonly").read_bytes()
        self.assertGreaterEqual(len(data), 52)
        header = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
        ident, elf_type, machine, version, entry, phoff, _, flags, ehsize, phsize, phnum, _, _, _ = header
        self.assertEqual(ident[:7], b"\x7fELF\x01\x01\x01")  # ELF32, little endian
        self.assertEqual((elf_type, machine, version), (2, 40, 1))  # EXEC, ARM
        self.assertEqual((ehsize, phsize), (52, 32))
        self.assertEqual(flags & 0xFF000000, 0x05000000)  # ARM EABI5
        self.assertTrue(flags & 0x200)  # soft-float ABI
        self.assertFalse(flags & 0x400)  # hard-float ABI
        self.assertGreater(phnum, 0)
        self.assertLessEqual(phoff + phnum * phsize, len(data))
        executable_entry = False
        for index in range(phnum):
            kind, offset, vaddr, _, filesz, memsz, permissions, _ = struct.unpack_from(
                "<IIIIIIII", data, phoff + index * phsize
            )
            self.assertNotIn(kind, (2, 3), "dynamic segment/interpreter is forbidden")
            self.assertLessEqual(offset + filesz, len(data))
            if kind == 1:
                self.assertLessEqual(filesz, memsz)
                executable_entry |= bool(permissions & 1 and vaddr <= entry < vaddr + filesz)
        self.assertTrue(executable_entry, "entry point must be in a file-backed executable LOAD segment")


if __name__ == "__main__":
    unittest.main()
