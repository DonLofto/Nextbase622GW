"""Windows host tests use a fake kernel; native-only tests touch temp files only."""
import ctypes as C
import importlib.util
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_host():
    sys.path.insert(0, str(ROOT / "persistent-repair"))
    try:
        spec = importlib.util.spec_from_file_location("windows_guided", ROOT / "persistent-repair/windows_host.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class FakeKernel:
    def __init__(self, module):
        self.m = module
        self.calls = []
        self.state = module.DCB()
        self.state.DCBlength = C.sizeof(module.DCB)
        self.state.BaudRate = 57600
        self.state.Flags = 0x7FFF
        self.state.ByteSize, self.state.Parity, self.state.StopBits = 7, 2, 1
        self.timeouts = module.Timeouts(10, 20, 30, 40, 50)
        self.incoming = [b"NBFA02_BEGIN\n", b"Drive 'A' format done.\n"]
        self.fail = None

    def CreateFileW(self, name, access, share, security, creation, flags, template):
        self.calls.append(("open", name, access, share))
        return 99

    def GetCommState(self, handle, output):
        self.calls.append(("get-state",))
        C.memmove(output, C.byref(self.state), C.sizeof(self.state))
        return self.fail != "get-state"

    def SetCommState(self, handle, source):
        data = C.string_at(source, C.sizeof(self.state))
        self.calls.append(("set-state", data))
        return self.fail != "set-state"

    def GetCommTimeouts(self, handle, output):
        C.memmove(output, C.byref(self.timeouts), C.sizeof(self.timeouts))
        return self.fail != "get-timeouts"

    def SetCommTimeouts(self, handle, source):
        self.calls.append(("set-timeouts", C.string_at(source, C.sizeof(self.timeouts))))
        return self.fail != "set-timeouts"

    def ReadFile(self, handle, output, size, count, overlap):
        if self.fail == "read": return 0
        if self.fail == "interrupt" and not self.incoming: raise KeyboardInterrupt()
        data = self.incoming.pop(0) if self.incoming else b""
        C.memmove(output, data, len(data))
        C.cast(count, C.POINTER(C.c_uint32))[0] = len(data)
        self.calls.append(("read", len(data)))
        return 1

    def DeviceIoControl(self, handle, code, incoming, length, outgoing, outlength, count, overlap):
        self.calls.append(("ioctl", code))
        return self.fail != code

    def FlushFileBuffers(self, handle):
        self.calls.append(("flush",))
        return 1

    def CloseHandle(self, handle):
        self.calls.append(("close", handle))
        return 1

    def MoveFileExW(self, source, destination, flags):
        self.calls.append(("move", source, destination, flags))
        return self.fail != "move"

    def GetLogicalDrives(self):
        return (1 << 2) | (1 << 4)

    def SetThreadExecutionState(self, flags):
        self.calls.append(("awake", flags))
        return 0x80000000


class WindowsHostTests(unittest.TestCase):
    def setUp(self):
        self.w = load_host()
        self.kernel = FakeKernel(self.w)
        self.api = self.w.NativeWindows(kernel=self.kernel)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()

    def host(self, query=None, port="COM7"):
        self.api.is_admin = lambda: True
        return self.w.WindowsHost(port=port, ready=lambda data, phase: b"Drive 'A' format done.\n" in data,
                                  api=self.api, query=query or self.query)

    def query(self, action, root=None):
        if action == "Ports":
            return [{"Port": "COM7", "Instance": "USB\\VID_FAKE\\SYNTHETIC"}]
        return {"Root": str(root), "Filesystem": "exFAT", "BusType": "USB", "IsBoot": False,
                "IsSystem": False, "IsReadOnly": False, "IsOffline": False, "Health": "Healthy",
                "VolumeHealth": "Healthy"}

    def test_fixed_width_windows_structures(self):
        self.assertEqual(C.sizeof(self.w.DCB), 28)
        self.assertEqual(C.sizeof(self.w.Timeouts), 20)

    def test_serial_preserves_baud_dtr_rts_and_restores_exact_state(self):
        with self.api.serial("COM7") as serial:
            self.assertEqual(serial.read(), b"NBFA02_BEGIN\n")
        configured = self.w.DCB.from_buffer_copy(next(c[1] for c in self.kernel.calls if c[0] == "set-state"))
        self.assertEqual(configured.BaudRate, self.kernel.state.BaudRate)
        self.assertEqual((configured.ByteSize, configured.Parity, configured.StopBits), (8, 0, 0))
        self.assertEqual(configured.Flags & 0x3030, self.kernel.state.Flags & 0x3030)
        self.assertEqual(configured.Flags & 0x0F02, 0)
        state_sets = [c[1] for c in self.kernel.calls if c[0] == "set-state"]
        self.assertEqual(state_sets[-1], bytes(self.kernel.state))
        self.assertEqual([c[1] for c in self.kernel.calls if c[0] == "set-timeouts"][-1], bytes(self.kernel.timeouts))
        self.assertEqual(self.kernel.calls[0][3], 0, "COM access must be exclusive")
        self.assertEqual(self.kernel.calls[-1], ("close", 99))

    def test_serial_failure_closes_and_restores_without_transmitting(self):
        self.kernel.fail = "read"
        with self.assertRaises(self.w.RepairError):
            with self.api.serial("COM7") as serial: serial.read()
        self.assertEqual(self.kernel.calls[-1], ("close", 99))
        self.assertTrue(any(c[0] == "set-state" and c[1] == bytes(self.kernel.state) for c in self.kernel.calls))
        self.assertFalse(any(c[0].lower().startswith("write") for c in self.kernel.calls))
        for name in ("COM0", "E:", "COM7;format", "\\\\server\\COM7"):
            with self.subTest(name=name), self.assertRaises(self.w.RepairError):
                self.api.serial(name)

    def test_serial_setup_failure_closes_handle(self):
        self.kernel.fail = "get-state"
        with self.assertRaises(self.w.RepairError):
            with self.api.serial("COM7"): pass
        self.assertEqual(self.kernel.calls[-1], ("close", 99))

    def test_windows_file_moves_flush_and_never_replace_staged_destination(self):
        self.api.move_file("stage", "destination")
        self.api.move_file("temporary", "journal", replace=True)
        self.assertEqual([c[-1] for c in self.kernel.calls if c[0] == "move"], [8, 9])
        self.kernel.fail = "move"
        with self.assertRaises(self.w.RepairError): self.api.move_file("stage", "destination")

    def test_ejection_locks_before_dismount_and_stops_on_lock_failure(self):
        self.api.eject("E:")
        codes = [c[1] for c in self.kernel.calls if c[0] == "ioctl"]
        self.assertEqual(codes, [0x90018, 0x90020, 0x2D4804, 0x2D4808])
        self.assertEqual(self.kernel.calls[-1], ("close", 99))
        self.kernel.calls.clear(); self.kernel.fail = 0x90018
        with self.assertRaises(self.w.RepairError): self.api.eject("E:")
        self.assertEqual([c[1] for c in self.kernel.calls if c[0] == "ioctl"], [0x90018])
        self.assertEqual(self.kernel.calls[-1], ("close", 99))

    def test_volume_rejects_system_internal_readonly_ambiguous_and_bad_health(self):
        for change in ({"IsSystem": True}, {"IsBoot": True}, {"BusType": "NVMe"}, {"IsReadOnly": True},
                       {"Filesystem": "NTFS"}, {"IsOffline": True}, {"Health": "Warning"}):
            def query(action, root=None): return {**self.query(action, root), **change}
            with self.subTest(change=change), self.assertRaises(self.w.RepairError): self.host(query).info(PureWindowsPath("E:/"))
        for root in ("C:/folder", "E:relative", "//server/share", "/"):
            with self.subTest(root=root), self.assertRaises(self.w.RepairError): self.host().info(PureWindowsPath(root))
        self.host().info(PureWindowsPath("E:/"))

    def test_disk_check_is_status_only_and_refuses_nonzero_exit(self):
        host = self.host()
        result = mock.Mock(returncode=0, stdout=b"clean", stderr=b"")
        with mock.patch.object(self.w.subprocess, "run", return_value=result) as run:
            self.assertEqual(host.verify(PureWindowsPath("E:/")), b"clean")
            self.assertEqual(run.call_args.args[0][-1], "E:")
            self.assertFalse(any(str(a).startswith("/") for a in run.call_args.args[0][1:]))
            self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        result.returncode = 3
        with mock.patch.object(self.w.subprocess, "run", return_value=result):
            with self.assertRaises(self.w.RepairError): host.verify(PureWindowsPath("E:/"))

    def test_passive_capture_records_bytes_and_pins_usb_instance(self):
        host = self.host()
        output = self.folder / "capture"
        data = host.capture(None, output, "format")
        self.assertEqual(data, b"NBFA02_BEGIN\nDrive 'A' format done.\n")
        self.assertEqual((output / "serial-rx.bin").read_bytes(), data)
        self.assertEqual((output / "serial-rx.txt").read_bytes(), data)
        self.assertTrue((output / "serial-settings.txt").is_file())
        self.assertEqual(host.instance, "USB\\VID_FAKE\\SYNTHETIC")
        with self.assertRaises(self.w.RepairError): host.capture(None, output, "format")
        host.query = lambda action, root=None: [{"Port": "COM7", "Instance": "USB\\OTHER"}]
        with self.assertRaises(self.w.RepairError): host.wait_port(seconds=0)

    def test_ambiguous_or_non_usb_ports_never_open(self):
        for ports in ([{"Port": "COM7", "Instance": "BTHENUM\\fake"}],
                      [{"Port": "COM7", "Instance": "USB\\ONE"}, {"Port": "COM8", "Instance": "USB\\TWO"}]):
            host = self.host(query=lambda action, root=None: ports, port=None)
            with self.assertRaises(self.w.RepairError): host.wait_port(seconds=0)
            self.assertFalse(self.kernel.calls)

    def test_capture_failure_retains_partial_evidence_and_closes_port(self):
        self.kernel.fail = "read"
        output = self.folder / "partial"
        with self.assertRaises(self.w.RepairError): self.host().capture(None, output, "format")
        self.assertTrue((output / "serial-rx.bin").is_file())
        self.assertEqual(self.kernel.calls[-1], ("close", 99))

    def test_cancelling_capture_keeps_partial_data_and_restores_port(self):
        self.kernel.fail = "interrupt"; self.kernel.incoming = [b"NBFA02_BEGIN\n"]
        output = self.folder / "interrupted"
        with self.assertRaises(KeyboardInterrupt): self.host().capture(None, output, "format")
        self.assertEqual((output / "serial-rx.bin").read_bytes(), b"NBFA02_BEGIN\n")
        self.assertEqual(self.kernel.calls[-1], ("close", 99))

    def test_sleep_prevention_is_scoped_and_restored_on_error(self):
        with self.assertRaises(ValueError):
            with self.api.awake(): raise ValueError("stop")
        self.assertEqual(self.kernel.calls, [("awake", 0x80000001), ("awake", 0x80000000)])

    def repair_module(self):
        sys.path.insert(0, str(ROOT / "persistent-repair"))
        try:
            spec = importlib.util.spec_from_file_location("windows_shared_repair", ROOT / "persistent-repair/repair.py")
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            return module
        finally:
            sys.path.pop(0)

    def test_shared_file_operations_use_write_through_windows_moves(self):
        repair = self.repair_module()
        backend = types.SimpleNamespace(move_file=mock.Mock())
        source, target = self.folder / "source", self.folder / "target"
        source.write_bytes(b"new")
        with mock.patch.object(repair, "is_windows", return_value=True), mock.patch.object(repair, "windows_host", backend):
            repair.move_exclusive(source, target)
            backend.move_file.assert_called_once_with(source, target)
            backend.move_file.reset_mock()
            repair.durable_replace(source, target)
            backend.move_file.assert_called_once_with(source, target, replace=True)

    def test_reparse_points_are_refused_as_well_as_symlinks(self):
        repair = self.repair_module()
        path = self.folder / "junction-like"
        path.mkdir()
        fake = mock.Mock(st_file_attributes=0x400)
        with mock.patch.object(type(path), "is_symlink", return_value=False), mock.patch.object(type(path), "lstat", return_value=fake):
            self.assertTrue(repair.is_linked(path))
            with self.assertRaises(repair.RepairError): repair.plain_directory(path)

    def test_shared_card_detection_uses_the_host_drive_roots(self):
        repair = self.repair_module()
        card = self.folder / "card"; card.mkdir()
        (card / "Nextbase.info").write_bytes(b"Model: 622GW\nFirmware: R13.3\nSerial No: CAMERA-FIXTURE\nSD Card Serial No: ABCD1234\n")
        host = types.SimpleNamespace(roots=lambda: [card], info=lambda path: None)
        wizard = repair.Wizard(ROOT, host=host, session_root=self.folder / "private")
        self.assertEqual(wizard.card(), card)

    @unittest.skipUnless(os.name == "nt", "native Windows launcher")
    def test_native_cmd_launcher_help(self):
        spec = importlib.util.spec_from_file_location("windows_release_builder", ROOT / "tools/build_release.py")
        builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
        archive = builder.build(ROOT, self.folder / "download.zip")
        import zipfile
        with zipfile.ZipFile(archive) as bundle: bundle.extractall(self.folder / "extracted kit with spaces")
        extracted = self.folder / "extracted kit with spaces" / builder.PREFIX / "Repair Bluetooth.cmd"
        for launcher in (ROOT / "Repair Bluetooth.cmd", extracted):
            result = subprocess.run([os.environ["COMSPEC"], "/d", "/c", str(launcher), "--help"],
                                    capture_output=True, timeout=30, env={**os.environ, "NB_REPAIR_NO_PAUSE": "1"})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(b"--volume", result.stdout)

    @unittest.skipUnless(os.name == "nt", "native Windows junction fixture")
    def test_native_junction_cannot_redirect_private_reads(self):
        repair = self.repair_module()
        target = self.folder / "real"; target.mkdir()
        (target / "private.txt").write_bytes(b"synthetic private data")
        junction = self.folder / "junction"
        result = subprocess.run([os.environ["COMSPEC"], "/d", "/c", "mklink", "/J", str(junction), str(target)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        try:
            self.assertTrue(repair.is_linked(junction))
            with self.assertRaises(repair.RepairError): repair.read_regular(junction / "private.txt")
        finally:
            os.rmdir(junction)

    @unittest.skipUnless(os.name == "nt", "native Windows API/PowerShell/CMD fixture")
    def test_native_windows_no_clobber_and_durable_replace(self):
        api = self.w.NativeWindows()
        source, target = self.folder / "source", self.folder / "target"
        source.write_bytes(b"new"); target.write_bytes(b"keep")
        with self.assertRaises(self.w.RepairError): api.move_file(source, target)
        self.assertEqual(source.read_bytes(), b"new"); self.assertEqual(target.read_bytes(), b"keep")
        api.move_file(source, target, replace=True)
        self.assertFalse(source.exists()); self.assertEqual(target.read_bytes(), b"new")

    @unittest.skipUnless(os.name == "nt", "native Windows read-only metadata")
    def test_native_powershell_query_and_system_drive_refusal(self):
        host = self.w.WindowsHost(ready=lambda data, phase: False)
        self.assertIsInstance(host.query("Ports"), list)
        root = PureWindowsPath(os.environ["SystemDrive"] + "\\")
        info = host.query("Info", root)
        self.assertIsInstance(info, dict)
        self.assertIn("Filesystem", info)
        self.assertIn("IsSystem", info)
        with self.assertRaises(self.w.RepairError): host.info(root)


if __name__ == "__main__": unittest.main()
