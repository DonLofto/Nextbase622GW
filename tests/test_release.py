"""Release tests protect the boundary between public tools and private captures."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def load_builder(self):
        path = ROOT / "tools/build_release.py"
        self.assertTrue(path.is_file(), "public release builder has not been implemented")
        spec = importlib.util.spec_from_file_location("build_release", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_release_uses_allowlist_and_verifiable_payloads(self):
        builder = self.load_builder()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            for name in builder.PUBLIC_FILES:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(("public fixture " + name + "\n").encode())
            (root / "docs/evidence").mkdir(parents=True)
            (root / "docs/evidence/private.xml").write_text("PRIVATE_PAIRING_KEY")
            (root / "HANDOFF.md").write_text("PRIVATE_DEVICE_ID")
            output = Path(directory) / "kit.zip"
            builder.build(root, output)
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                self.assertEqual(set(names), {builder.PREFIX + n for n in builder.PUBLIC_FILES} |
                                 {builder.PREFIX + "recovery-kit/SHA256SUMS",
                                  builder.PREFIX + builder.ADVANCED_DIRECTORY + "SHA256SUMS",
                                  builder.PREFIX + "persistent-repair/payload/SHA256SUMS"})
                self.assertFalse(any(b"PRIVATE_" in archive.read(n) for n in names))
                manifest = archive.read(builder.PREFIX + "recovery-kit/SHA256SUMS").decode()
                for line in manifest.splitlines():
                    digest, name = line.split("  ", 1)
                    data = archive.read(builder.PREFIX + "recovery-kit/payload/" + name)
                    self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
                advanced = archive.read(builder.PREFIX + builder.ADVANCED_DIRECTORY + "SHA256SUMS").decode()
                self.assertEqual(len(advanced.splitlines()), len(builder.ADVANCED_FILES))
                for line in advanced.splitlines():
                    digest, name = line.split("  ", 1)
                    data = archive.read(builder.PREFIX + builder.ADVANCED_DIRECTORY + name)
                    self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
                preflight = archive.read(builder.PREFIX + "persistent-repair/payload/SHA256SUMS").decode()
                self.assertEqual(len(preflight.splitlines()), 2)
                for line in preflight.splitlines():
                    digest, name = line.split("  ", 1)
                    data = archive.read(builder.PREFIX + "persistent-repair/payload/" + name)
                    self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
                mode = archive.getinfo(builder.PREFIX + "recovery-kit/Recover Bluetooth.command").external_attr >> 16
                self.assertTrue(mode & 0o100)

    def test_missing_file_does_not_replace_existing_release(self):
        builder = self.load_builder()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            output = Path(directory) / "kit.zip"
            output.write_bytes(b"existing release")
            with self.assertRaises(FileNotFoundError):
                builder.build(root, output)
            self.assertEqual(output.read_bytes(), b"existing release")

    def test_symlink_is_not_followed_into_private_data(self):
        builder = self.load_builder()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            for name in builder.PUBLIC_FILES:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("fixture\n")
            public = root / builder.PUBLIC_FILES[0]
            public.unlink()
            private = Path(directory) / "private.txt"
            private.write_text("PRIVATE")
            public.symlink_to(private)
            with self.assertRaises(ValueError):
                builder.build(root, Path(directory) / "kit.zip")

    def test_concurrent_source_edit_cannot_make_archive_manifest_stale(self):
        builder = self.load_builder()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "source"
            root.mkdir()
            for name in builder.PUBLIC_FILES:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"original snapshot\n")
            token = root / "recovery-kit/payload/usb.console"
            advanced_token = root / builder.ADVANCED_DIRECTORY / "usb.console"
            preflight_script = root / "persistent-repair/payload/nb-a-preflight.sh"
            read_bytes = Path.read_bytes
            changed = set()

            def read_then_concurrently_edit(path):
                data = read_bytes(path)
                if path in (token, advanced_token, preflight_script) and path not in changed:
                    changed.add(path)
                    path.write_bytes(b"source edited after capture\n")
                return data

            output = Path(directory) / "kit.zip"
            with mock.patch.object(Path, "read_bytes", read_then_concurrently_edit):
                builder.build(root, output)
            self.assertEqual(changed, {token, advanced_token, preflight_script}, "All source edits must happen during this build")
            with zipfile.ZipFile(output) as archive:
                for manifest_name, directory in (
                    ("recovery-kit/SHA256SUMS", "recovery-kit/payload/"),
                    (builder.ADVANCED_DIRECTORY + "SHA256SUMS", builder.ADVANCED_DIRECTORY),
                    ("persistent-repair/payload/SHA256SUMS", "persistent-repair/payload/"),
                ):
                    manifest = archive.read(builder.PREFIX + manifest_name).decode()
                    for line in manifest.splitlines():
                        digest, name = line.split("  ", 1)
                        archived = archive.read(builder.PREFIX + directory + name)
                        self.assertEqual(digest, hashlib.sha256(archived).hexdigest())


if __name__ == "__main__":
    unittest.main()
