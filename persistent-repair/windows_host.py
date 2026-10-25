"""Windows host I/O only. The repair/consent state machine stays in repair.py.

Win32 references: learn.microsoft.com/windows/win32/api/winbase/ns-winbase-dcb,
ns-winbase-commtimeouts and nf-winbase-movefileexw; winioctl FSCTL_LOCK_VOLUME.
No WriteFile, serial commands, baud guesses or controller resets are used.
"""
import codecs
import ctypes as C
from contextlib import contextmanager
from functools import lru_cache
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
import time

from results import RepairError, read_regular


DWORD, WORD, BYTE, HANDLE = C.c_uint32, C.c_uint16, C.c_ubyte, C.c_void_p


class DCB(C.Structure):
    _fields_ = [("DCBlength", DWORD), ("BaudRate", DWORD), ("Flags", DWORD),
                ("wReserved", WORD), ("XonLim", WORD), ("XoffLim", WORD),
                ("ByteSize", BYTE), ("Parity", BYTE), ("StopBits", BYTE),
                ("XonChar", C.c_char), ("XoffChar", C.c_char), ("ErrorChar", C.c_char),
                ("EofChar", C.c_char), ("EvtChar", C.c_char), ("wReserved1", WORD)]


class Timeouts(C.Structure):
    _fields_ = [(name, DWORD) for name in ("ReadIntervalTimeout", "ReadTotalTimeoutMultiplier",
                "ReadTotalTimeoutConstant", "WriteTotalTimeoutMultiplier", "WriteTotalTimeoutConstant")]


def port_name(value):
    if not isinstance(value, str) or re.fullmatch(r"COM[1-9][0-9]{0,4}", value.upper()) is None:
        raise RepairError("Use an identified USB COM port such as COM7; no arbitrary device paths are accepted.")
    return value.upper()


def drive_name(value):
    path = str(PureWindowsPath(value))
    if re.fullmatch(r"[A-Za-z]:\\", path) is None:
        raise RepairError("Windows requires the SD drive root, for example E:\\, not a folder or network path.")
    return path[0].upper() + ":"


class NativeWindows:
    def __init__(self, kernel=None):
        self.native = kernel is None
        if kernel is None:
            if os.name != "nt":
                raise RepairError("Native Windows I/O is unavailable on this host.")
            kernel = C.WinDLL("kernel32", use_last_error=True)
            signatures = {
                "CreateFileW": (HANDLE, [C.c_wchar_p, DWORD, DWORD, C.c_void_p, DWORD, DWORD, HANDLE]),
                "CloseHandle": (C.c_int, [HANDLE]),
                "GetCommState": (C.c_int, [HANDLE, C.POINTER(DCB)]),
                "SetCommState": (C.c_int, [HANDLE, C.POINTER(DCB)]),
                "GetCommTimeouts": (C.c_int, [HANDLE, C.POINTER(Timeouts)]),
                "SetCommTimeouts": (C.c_int, [HANDLE, C.POINTER(Timeouts)]),
                "ReadFile": (C.c_int, [HANDLE, C.c_void_p, DWORD, C.POINTER(DWORD), C.c_void_p]),
                "DeviceIoControl": (C.c_int, [HANDLE, DWORD, C.c_void_p, DWORD, C.c_void_p, DWORD, C.POINTER(DWORD), C.c_void_p]),
                "MoveFileExW": (C.c_int, [C.c_wchar_p, C.c_wchar_p, DWORD]),
                "GetLogicalDrives": (DWORD, []),
                "SetThreadExecutionState": (DWORD, [DWORD]),
            }
            for name, (result, arguments) in signatures.items():
                function = getattr(kernel, name)
                function.restype, function.argtypes = result, arguments
        self.kernel = kernel

    def check(self, success, message):
        if not success:
            code = C.get_last_error() if self.native else 1
            raise RepairError(message + " (Windows error " + str(code) + ").")

    def is_admin(self):
        if not self.native:
            return True
        shell = C.WinDLL("shell32", use_last_error=True)
        shell.IsUserAnAdmin.restype = C.c_int
        shell.IsUserAnAdmin.argtypes = []
        return bool(shell.IsUserAnAdmin())

    def open(self, name, share=0):
        handle = self.kernel.CreateFileW(name, 0xC0000000, share, None, 3, 0, None)
        self.check(handle is not None and handle != C.c_void_p(-1).value,
                   "Cannot exclusively open the selected device; close other apps/monitors")
        return handle

    def move_file(self, source, destination, replace=False):
        self.check(self.kernel.MoveFileExW(str(source), str(destination), 8 | (1 if replace else 0)),
                   "Write-through file move failed; an existing staged destination is never overwritten")

    def roots(self):
        mask = self.kernel.GetLogicalDrives()
        self.check(mask, "Cannot enumerate local Windows drive letters")
        return [chr(65 + index) + ":\\" for index in range(26) if mask & (1 << index)]

    def serial(self, name):
        return SerialReader(self, port_name(name))

    @contextmanager
    def awake(self):
        old = self.kernel.SetThreadExecutionState(0x80000001)
        self.check(old, "Cannot keep the computer awake during repair")
        try:
            yield
        finally:
            self.kernel.SetThreadExecutionState(old | 0x80000000)

    def eject(self, drive):
        if re.fullmatch(r"[A-Z]:", drive) is None:
            raise RepairError("Invalid ejection target.")
        handle = self.open("\\\\.\\" + drive, share=3)
        try:
            for code in (0x90018, 0x90020, 0x2D4804, 0x2D4808):
                returned = DWORD()
                removal = BYTE(0)
                source = C.byref(removal) if code == 0x2D4804 else None
                size = 1 if source is not None else 0
                self.check(self.kernel.DeviceIoControl(handle, code, source, size, None, 0, C.byref(returned), None),
                           "Safe SD ejection failed. Close Explorer/apps; do not unplug or boot while it is mounted")
        finally:
            self.kernel.CloseHandle(handle)


class SerialReader:
    def __init__(self, api, name):
        self.api, self.name = api, name
        self.handle, self.state, self.timeouts = None, None, None

    def __enter__(self):
        kernel = self.api.kernel
        self.handle = self.api.open("\\\\.\\" + self.name)
        try:
            state = DCB(); state.DCBlength = C.sizeof(DCB)
            self.api.check(kernel.GetCommState(self.handle, C.byref(state)), "Cannot read existing COM settings")
            self.state = DCB.from_buffer_copy(bytes(state))
            if state.BaudRate == 0:
                raise RepairError("The COM port has no valid existing baud rate; no guess is made.")
            timeouts = Timeouts()
            self.api.check(kernel.GetCommTimeouts(self.handle, C.byref(timeouts)), "Cannot read COM timeouts")
            self.timeouts = Timeouts.from_buffer_copy(bytes(timeouts))
            # Raw 8N1, preserving baud and DTR/RTS. Disable software flow control
            # so the driver cannot transmit XON/XOFF or discard/replace RX bytes.
            state.Flags = (state.Flags | 1) & ~((1 << 1) | (1 << 6) | (0xF << 8) | (1 << 14))
            state.ByteSize, state.Parity, state.StopBits = 8, 0, 0
            self.api.check(kernel.SetCommState(self.handle, C.byref(state)), "Cannot configure passive COM capture")
            polling = Timeouts(0xFFFFFFFF, 0, 0, timeouts.WriteTotalTimeoutMultiplier, timeouts.WriteTotalTimeoutConstant)
            self.api.check(kernel.SetCommTimeouts(self.handle, C.byref(polling)), "Cannot configure bounded COM reads")
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def read(self):
        buffer = C.create_string_buffer(16384); count = DWORD()
        self.api.check(self.api.kernel.ReadFile(self.handle, buffer, len(buffer), C.byref(count), None),
                       "Passive COM read failed; no reboot or retry is authorized")
        if count.value > len(buffer):
            raise RepairError("COM driver returned an invalid byte count.")
        return buffer.raw[:count.value]

    def __exit__(self, kind, error, traceback):
        failures = []
        try:
            if self.timeouts is not None and not self.api.kernel.SetCommTimeouts(self.handle, C.byref(self.timeouts)):
                failures.append("timeouts")
            if self.state is not None and not self.api.kernel.SetCommState(self.handle, C.byref(self.state)):
                failures.append("settings")
        finally:
            if self.handle is not None:
                self.api.kernel.CloseHandle(self.handle)
                self.handle = None
        if failures and kind is None:
            raise RepairError("COM capture stopped but original settings could not be restored.")


@lru_cache(maxsize=1)
def native():
    return NativeWindows()


def move_file(source, destination, replace=False):
    native().move_file(source, destination, replace)


class WindowsHost:
    label = "Windows"

    def __init__(self, port=None, ready=None, api=None, query=None):
        self.api = api if api is not None else native()
        if not self.api.is_admin():
            raise RepairError("Run the Windows repair launcher as administrator for SD checks/safe ejection.")
        self.port = port_name(port) if port else None
        self.instance = None
        self.ready = ready
        self.query = query or self.powershell

    def powershell(self, action, root=None):
        executable = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        command = [str(executable), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                   str(Path(__file__).with_name("windows-volume.ps1")), "-Action", action]
        if root is not None:
            command.extend(["-Volume", drive_name(root) + "\\"])
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True)
        if result.returncode != 0:
            raise RepairError("Windows storage/USB query failed. Use an administrator terminal and check the reader/driver.")
        try:
            return json.loads(result.stdout.decode("utf-8-sig"))
        except (UnicodeError, ValueError):
            raise RepairError("Windows storage/USB metadata is missing or malformed.") from None

    def roots(self):
        return self.api.roots()

    def awake(self):
        return self.api.awake()

    def info(self, card):
        drive = drive_name(card)
        info = self.query("Info", drive + "\\")
        if (not isinstance(info, dict) or str(info.get("Root", "")).upper() != drive + "\\"
                or str(info.get("Filesystem", "")).upper() not in ("EXFAT", "FAT", "FAT32")
                or str(info.get("BusType", "")).upper() not in ("USB", "SD", "MMC")
                or any(info.get(key) is not False for key in ("IsBoot", "IsSystem", "IsReadOnly", "IsOffline"))
                or info.get("Health") != "Healthy" or info.get("VolumeHealth") != "Healthy"):
            raise RepairError("Require one healthy writable external USB/SD FAT/exFAT volume; system/internal disks are refused.")

    def verify(self, card):
        self.info(card)
        executable = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32/chkdsk.exe"
        result = subprocess.run([str(executable), drive_name(card)], stdin=subprocess.DEVNULL, capture_output=True)
        if result.returncode != 0:
            raise RepairError("Read-only CHKDSK did not report a clean volume. Close apps and resolve the SD fault separately; no repair was run.")
        return result.stdout + result.stderr

    def eject(self, card):
        self.info(card)
        self.api.eject(drive_name(card))

    def wait_port(self, seconds=600):
        deadline = time.monotonic() + seconds
        while True:
            records = self.query("Ports")
            if not isinstance(records, list):
                raise RepairError("Windows USB COM-port list is malformed.")
            ports = []
            for item in records:
                if not isinstance(item, dict) or not isinstance(item.get("Instance"), str):
                    raise RepairError("Windows USB COM-port identity is malformed.")
                name = port_name(item.get("Port"))
                instance = item["Instance"].upper()
                if not instance.startswith("USB\\"):
                    continue
                if self.instance and instance != self.instance:
                    continue
                if not self.instance and self.port and name != self.port:
                    continue
                ports.append({"Port": name, "Instance": instance})
            if len(ports) > 1:
                raise RepairError("Multiple USB COM ports found; use an identified --port COM7 or disconnect unrelated devices.")
            if ports:
                self.instance = ports[0]["Instance"]
                return ports[0]
            if time.monotonic() >= deadline:
                raise RepairError("The expected USB COM interface did not appear. Check Device Manager/cable; no port or baud is guessed.")
            time.sleep(0.2)

    def capture(self, tool, output, phase):
        if not callable(self.ready):
            raise RepairError("No shared boot-result validator was supplied.")
        try:
            output.mkdir(mode=0o700)  # Exclusive; no reuse of stale captures.
        except OSError:
            raise RepairError("Capture path exists or cannot be created; stale evidence is never reused.") from None
        decoder = codecs.getincrementaldecoder("utf-8")("backslashreplace")
        data = bytearray()
        with (output / "serial-rx.bin").open("xb", buffering=0) as raw, \
                (output / "serial-rx.txt").open("x", encoding="utf-8", newline="") as text:
            port = self.wait_port()
            with self.api.serial(port["Port"]) as reader:
                settings = {**port, "baud_unchanged": reader.state.BaudRate,
                            "original_dcb_hex": bytes(reader.state).hex(),
                            "original_timeouts_hex": bytes(reader.timeouts).hex()}
                with (output / "serial-settings.txt").open("x", encoding="utf-8", newline="") as saved:
                    saved.write(json.dumps(settings, indent=2) + "\n")
                started = time.monotonic()
                try:
                    while True:
                        chunk = reader.read()
                        if len(data) + len(chunk) > 32 * 1024 * 1024:
                            raise RepairError("Passive capture exceeded its byte limit; partial evidence retained.")
                        raw.write(chunk); data.extend(chunk)
                        text.write(decoder.decode(chunk)); text.flush()
                        if self.ready(bytes(data), phase):
                            break
                        if phase != "format" and time.monotonic() - started > 1200:
                            raise RepairError("Required console result missing; partial evidence retained.")
                        if not chunk:
                            time.sleep(0.05)
                finally:
                    text.write(decoder.decode(b"", final=True)); text.flush()
                    os.fsync(raw.fileno()); os.fsync(text.fileno())
        captured = read_regular(output / "serial-rx.bin", limit=32 * 1024 * 1024)
        if captured != bytes(data) or not self.ready(captured, phase):
            raise RepairError("Saved console result did not verify.")
        return captured
