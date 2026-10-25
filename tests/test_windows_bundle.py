"""Frozen entrypoint tests; native smoke tests never open storage or serial ports."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from test_persistent_repair import load_wizard

ROOT = Path(__file__).resolve().parents[1]


class BundleTests(unittest.TestCase):
    def test_windows_null_input_is_refused_before_device_access(self):
        repair = load_wizard()
        api = mock.Mock()
        api.interactive_console.return_value = False
        with mock.patch.object(sys, "platform", "win32"), mock.patch.object(sys.stdin, "isatty", return_value=True), mock.patch.object(repair, "is_windows", return_value=True), mock.patch.object(repair.windows_host, "native", return_value=api), mock.patch.object(repair, "default_host", side_effect=AssertionError("device access")), mock.patch.object(sys, "stderr"):
            with self.assertRaises(SystemExit) as stopped:
                repair.main([])
            self.assertEqual(stopped.exception.code, 2)

    def test_native_console_query_refuses_nonconsole_handle(self):
        repair = load_wizard()
        kernel = mock.Mock()
        kernel.GetStdHandle.return_value = 99
        kernel.GetConsoleMode.return_value = 0
        api = repair.windows_host.NativeWindows(kernel=kernel)
        self.assertFalse(api.interactive_console())
        kernel.GetStdHandle.assert_called_with(-10)
        kernel.GetConsoleMode.return_value = 1
        self.assertTrue(api.interactive_console())

    def test_build_stages_on_destination_drive(self):
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            spec = importlib.util.spec_from_file_location("build_windows", ROOT / "tools/build_windows.py")
            builder = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(builder)
        finally:
            sys.path.pop(0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with mock.patch.object(builder, "__file__", str(root / "tools/build_windows.py")), mock.patch.object(sys, "platform", "win32"), mock.patch.object(sys, "version_info", (3, 12)), mock.patch.object(builder.tempfile, "TemporaryDirectory", side_effect=RuntimeError("stop before compilation")) as stage:
                with self.assertRaisesRegex(RuntimeError, "stop before compilation"):
                    builder.main()
            self.assertEqual(stage.call_args.kwargs.get("dir"), root / "dist")
            self.assertTrue((root / "dist").is_dir())

    def test_source_and_frozen_resource_roots(self):
        repair = load_wizard()
        self.assertEqual(repair.resource_root(), ROOT)
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(repair, "__file__", str(ROOT / "_internal/repair.py")):
            self.assertEqual(repair.resource_root(), ROOT / "_internal")

    def test_check_kit_is_read_only_and_refuses_changed_payload(self):
        repair = load_wizard()
        with mock.patch.object(repair, "default_host", side_effect=AssertionError("hardware access")), mock.patch("builtins.print"):
            self.assertEqual(repair.main(["--check-kit"]), 0)
            with tempfile.TemporaryDirectory() as directory:
                with mock.patch.object(repair, "resource_root", return_value=Path(directory)):
                    self.assertEqual(repair.main(["--check-kit"]), 1)

    def test_exe_keeps_console_open_after_result(self):
        repair = load_wizard()
        path = ROOT / "persistent-repair/windows_entry.py"
        spec = importlib.util.spec_from_file_location("windows_entry", path)
        entry = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {"repair": repair}):
            spec.loader.exec_module(entry)
        with mock.patch.object(entry, "main", return_value=1), mock.patch.object(entry, "interactive_console", return_value=True), mock.patch("builtins.input") as pause:
            self.assertEqual(entry.run(), 1)
            pause.assert_called_once()


@unittest.skipUnless(os.name == "nt" and os.environ.get("NB_REPAIR_EXE"), "built Windows EXE required")
class NativeBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        original = Path(os.environ["NB_REPAIR_EXE"]).resolve()
        self.bundle = self.directory / "portable"
        self.bundle.mkdir()
        shutil.copy2(original, self.bundle / original.name)
        shutil.copytree(original.parent / "_internal", self.bundle / "_internal")
        self.exe = self.bundle / original.name
        self.environment = {**os.environ, "PATH": str(self.directory / "no-python"),
                            "PYTHONHOME": str(self.directory / "no-runtime"),
                            "PYTHONPATH": str(self.directory / "no-source")}

    def run_exe(self, *args):
        return subprocess.run([str(self.exe), *args], cwd=self.directory, env=self.environment,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=90)

    def test_no_python_install_or_source_tree_needed(self):
        for args in (("--help",), ("--check-kit",)):
            result = self.run_exe(*args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Repair kit files verified", result.stdout)
        self.assertTrue((self.bundle / "_internal/python312.dll").is_file())
        self.assertTrue((self.bundle / "_internal/licenses/Python.txt").is_file())

    def test_missing_or_modified_payload_refuses(self):
        payload = self.bundle / "_internal/advanced/internal-drive-a/format-a-once.autoexec.ash"
        payload.write_bytes(payload.read_bytes() + b"changed")
        result = self.run_exe("--check-kit")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Stopped:", result.stderr)

    def test_interactive_consent_cannot_be_bypassed(self):
        result = self.run_exe()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("interactive terminal", result.stderr)
        result = self.run_exe("--yes")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_console_and_administrator_manifest(self):
        import pefile
        pe = pefile.PE(str(self.exe))
        self.addCleanup(pe.close)
        self.assertEqual(pe.OPTIONAL_HEADER.Subsystem, 3)  # Windows console
        self.assertEqual(pe.FILE_HEADER.Machine, 0x8664)  # x64
        resources = [entry for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries if entry.id == 24]
        self.assertEqual(len(resources), 1)
        entry = resources[0].directory.entries[0].directory.entries[0].data.struct
        manifest = pe.get_data(entry.OffsetToData, entry.Size)
        self.assertIn(b'level="requireAdministrator"', manifest)


if __name__ == "__main__":
    unittest.main()
