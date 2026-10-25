"""Exercise the passive reader against a local POSIX pseudoterminal only."""
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest

if os.name == "posix":
    import pty
    import termios


TOOL = Path(__file__).resolve().parents[1] / "tools" / "capture_rtos.py"


@unittest.skipUnless(os.name == "posix", "POSIX pseudoterminal test; Windows capture is unsupported")
class PassiveCaptureTests(unittest.TestCase):
    def wait_for(self, predicate, process, message):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            if process.poll() is not None:
                self.fail(f"reader exited early ({process.returncode}): {message}")
            time.sleep(0.01)
        self.fail(message)

    def test_captures_nul_and_split_utf8_without_transmitting_or_reading_stdin(self):
        self.assertTrue(TOOL.is_file(), "passive reader has not been implemented")
        master, slave = pty.openpty()
        stdin_read, stdin_write = os.pipe()
        process = None
        try:
            original = termios.tcgetattr(slave)
            sentinel = b"THIS MUST NOT REACH THE SERIAL PORT\n"
            os.write(stdin_write, sentinel)
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "capture"
                process = subprocess.Popen(
                    [sys.executable, str(TOOL), "--port", os.ttyname(slave), "--output", str(output)],
                    stdin=stdin_read, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                ready = bytearray()

                def opened():
                    if select.select([process.stderr], [], [], 0)[0]:
                        ready.extend(os.read(process.stderr.fileno(), 8192))
                    return b"Opened " in ready

                self.wait_for(opened, process, "reader did not configure the pseudoterminal")
                active = termios.tcgetattr(slave)
                self.assertEqual(active[4:6], original[4:6], "baud rates must remain unchanged")
                self.assertEqual(active[2] & termios.CSIZE, termios.CS8)
                self.assertFalse(active[2] & (termios.PARENB | termios.CSTOPB))
                self.assertFalse(active[3] & (termios.ICANON | termios.ECHO))
                first = b"NBFA02_BEGIN\x00\r\nDrive 'A' format done.\xffUTF8 \xc3"
                second = b"\xb1\n"
                os.write(master, first)
                raw = output / "serial-rx.bin"
                self.wait_for(lambda: raw.exists() and raw.stat().st_size == len(first), process,
                              "first bytes were not captured")
                os.write(master, second)
                self.wait_for(lambda: raw.stat().st_size == len(first + second), process,
                              "remaining bytes were not captured")
                process.send_signal(signal.SIGINT)
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, bytes(ready) + stderr)
                self.assertEqual(raw.read_bytes(), first + second)
                decoded = "NBFA02_BEGIN\x00\r\nDrive 'A' format done.\\xffUTF8 ñ\n".encode("utf-8")
                self.assertEqual((output / "serial-rx.txt").read_bytes(), decoded)
                self.assertEqual(stdout, decoded)
                self.assertTrue((output / "serial-settings.txt").is_file())
                self.assertIn(b"Stopped", stderr)
                restored = termios.tcgetattr(slave)
                # macOS sets transient PENDIN when canonical mode is restored.
                restored[3] &= ~getattr(termios, "PENDIN", 0)
                original[3] &= ~getattr(termios, "PENDIN", 0)
                self.assertEqual(restored, original)
                self.assertFalse(select.select([master], [], [], 0.05)[0], "reader transmitted serial data")
                os.set_blocking(stdin_read, False)
                self.assertEqual(os.read(stdin_read, 4096), sentinel, "reader consumed stdin")
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
            for fd in (master, slave, stdin_read, stdin_write):
                os.close(fd)

    def test_existing_output_is_refused_without_touching_it(self):
        self.assertTrue(TOOL.is_file(), "passive reader has not been implemented")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "existing"
            output.mkdir()
            sentinel = output / "keep.txt"
            sentinel.write_bytes(b"existing evidence\n")
            result = subprocess.run(
                [sys.executable, str(TOOL), "--port", str(Path(directory) / "missing-port"),
                 "--output", str(output)],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=3,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"exist", result.stderr.lower())
            self.assertEqual(list(output.iterdir()), [sentinel])
            self.assertEqual(sentinel.read_bytes(), b"existing evidence\n")

    def test_wait_cannot_exceed_ten_minutes(self):
        self.assertTrue(TOOL.is_file(), "passive reader has not been implemented")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capture"
            result = subprocess.run(
                [sys.executable, str(TOOL), "--output", str(output), "--wait-seconds", "601"],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=3,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
