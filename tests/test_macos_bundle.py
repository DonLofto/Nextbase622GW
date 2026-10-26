"""Mac app/reader packaging tests; no physical storage or serial device is used."""
import importlib.util
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from test_persistent_repair import load_wizard

ROOT = Path(__file__).resolve().parents[1]


def load_entry():
    repair = load_wizard()
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        spec = importlib.util.spec_from_file_location("mac_entry", ROOT / "persistent-repair/mac_entry.py")
        entry = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {"repair": repair}):
            spec.loader.exec_module(entry)
        return entry
    finally:
        sys.path.pop(0)


class MacEntryTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "runtime path alias fixture")
    def test_kit_check_canonicalizes_module_directory_but_refuses_linked_helper(self):
        repair = load_wizard()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            alias = base / "module-alias"
            alias.symlink_to(ROOT / "persistent-repair", target_is_directory=True)
            with mock.patch.object(repair.windows_host, "__file__", str(alias / "windows_host.py")), mock.patch("builtins.print"):
                self.assertEqual(repair.main(["--check-kit"]), 0)
            helper = base / "windows-volume.ps1"
            helper.symlink_to(ROOT / "persistent-repair/windows-volume.ps1")
            with mock.patch.object(repair.windows_host, "__file__", str(base / "windows_host.py")), mock.patch("builtins.print"):
                self.assertEqual(repair.main(["--check-kit"]), 1)

    def test_frozen_reader_command_does_not_treat_engine_as_python(self):
        repair = load_wizard()
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", "/example/engine"):
            self.assertEqual(repair.passive_reader_command(Path("capture.py"), Path("capture")),
                             ["/example/engine", "--passive-reader", "--output", "capture"])
        self.assertEqual(repair.passive_reader_command(Path("capture.py"), Path("capture")),
                         [sys.executable, "capture.py", "--output", "capture"])

    def test_passive_reader_is_dispatched_before_interactive_wizard_and_never_pauses(self):
        entry = load_entry()
        with mock.patch.object(entry.capture_rtos, "main", return_value=0) as reader, mock.patch.object(entry, "main", side_effect=AssertionError("wizard must not run")), mock.patch("builtins.input", side_effect=AssertionError("no stdin reads")):
            self.assertEqual(entry.run(["--passive-reader", "--list"]), 0)
            reader.assert_called_once_with(["--list"])

    def test_normal_wizard_result_is_preserved_and_console_pauses(self):
        entry = load_entry()
        with mock.patch.object(entry, "main", return_value=1) as wizard, mock.patch.object(entry, "interactive_console", return_value=True), mock.patch("builtins.input") as pause:
            self.assertEqual(entry.run([]), 1)
            wizard.assert_called_once_with([])
            pause.assert_called_once()


@unittest.skipUnless(sys.platform == "darwin" and os.environ.get("NB_REPAIR_APP"), "built Mac app required")
class NativeMacAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.app = self.directory / "Moved repair's folder/Repair Bluetooth.app"
        self.app.parent.mkdir()
        subprocess.run(["/usr/bin/ditto", os.environ["NB_REPAIR_APP"], str(self.app)], check=True)
        self.engine = self.app / "Contents/Resources/repair-engine"
        self.launch = self.app / "Contents/MacOS/Launch"
        self.environment = {**os.environ, "PATH": str(self.directory / "no-python"),
                            "PYTHONHOME": str(self.directory / "no-runtime"), "PYTHONPATH": str(self.directory / "no-source")}

    def run_app(self, *args, engine=False):
        return subprocess.run([str(self.engine if engine else self.launch), *args], cwd=self.directory,
                              env=self.environment, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=90)

    def test_moved_app_needs_no_python_or_checkout(self):
        for args in (("--help",), ("--check-kit",)):
            result = self.run_app(*args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Repair kit files verified", result.stdout)
        self.assertTrue((self.app / "Contents/Resources/CLAUDE.md").is_file())

    def test_noninteractive_and_automatic_confirmation_are_refused(self):
        result = self.run_app(engine=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("interactive terminal", result.stderr)
        result = self.run_app("--yes")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_bundle_metadata_signature_and_executable_permissions(self):
        info = plistlib.loads((self.app / "Contents/Info.plist").read_bytes())
        self.assertEqual(info["CFBundleExecutable"], "Launch")
        self.assertEqual(info["LSMinimumSystemVersion"], "15.0")
        for path in (self.launch, self.engine, self.app / "Contents/Resources/Repair Bluetooth.command"):
            self.assertTrue(os.access(path, os.X_OK))
        result = subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(self.app)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_bundled_passive_reader_captures_pty_and_restores_settings_without_tx(self):
        import pty
        import select
        import termios
        repair = load_wizard()
        master, slave = pty.openpty()
        original = termios.tcgetattr(slave)
        output = self.directory / "capture"
        failures = []
        def produce():
            try:
                deadline = time.monotonic() + 20
                while not (output / "serial-rx.bin").exists():
                    if time.monotonic() > deadline:
                        raise AssertionError("bundled reader never opened")
                    time.sleep(0.01)
                os.write(master, b"NBFA02_BEGIN\n")
                time.sleep(0.2)
                os.write(master, b"Drive 'A' format done.\n")
            except BaseException as error:
                failures.append(error)
        producer = threading.Thread(target=produce)
        producer.start()
        try:
            with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", str(self.engine)), mock.patch.dict(os.environ, self.environment):
                data = repair.MacHost(os.ttyname(slave)).capture(Path("no-python-source.py"), output, "format")
            self.assertEqual(data, b"NBFA02_BEGIN\nDrive 'A' format done.\n")
            self.assertFalse(select.select([master], [], [], 0.05)[0], "reader transmitted data")
            restored = termios.tcgetattr(slave)
            # Darwin adds PENDIN when restoring canonical input; it is kernel state.
            restored[3] &= ~termios.PENDIN
            original[3] &= ~termios.PENDIN
            self.assertEqual(restored, original)
            self.assertEqual(failures, [])
        finally:
            producer.join(timeout=21)
            os.close(master)
            os.close(slave)


if __name__ == "__main__":
    unittest.main()
