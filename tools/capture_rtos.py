#!/usr/bin/env python3
"""Passive POSIX serial capture. Never reads stdin or transmits serial data.

Uses the capture method tested on macOS: exclusive nonblocking open, raw 8N1,
and unchanged input/output baud rates. Windows is unsupported; a separate known
passive serial monitor would be required and has not been validated here.
"""
import argparse
import codecs
import glob
import os
from pathlib import Path
import select
import sys
import time


def wait_for_port(port, seconds):
    deadline = time.monotonic() + seconds
    print("Waiting for serial port; boot the camera when ready. Ctrl+C stops.",
          file=sys.stderr, flush=True)
    while True:
        candidates = [port] if port and Path(port).exists() else []
        if not port:
            candidates = sorted(glob.glob("/dev/cu.usbmodem*"))
        if len(candidates) > 1:
            raise ValueError("Multiple serial ports found; use --list and select one with --port")
        if candidates:
            return candidates[0]
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("No serial port appeared within the requested wait")
        time.sleep(min(0.2, remaining))


def capture(port, output):
    import fcntl
    import termios

    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    old = None
    total = 0
    reason = "Disconnected (EOF)"
    status = 0
    try:
        fcntl.ioctl(fd, termios.TIOCEXCL)
        old = termios.tcgetattr(fd)
        attr = list(old)
        attr[6] = list(old[6])
        attr[0] = 0
        attr[1] = 0
        attr[3] = 0
        attr[2] = ((attr[2] & ~(termios.PARENB | termios.CSTOPB | termios.CSIZE))
                   | termios.CS8 | termios.CLOCAL | termios.CREAD)
        attr[6][termios.VMIN] = 0
        attr[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attr)
        with (output / "serial-settings.txt").open("x", encoding="ascii") as settings:
            settings.write(repr(old) + "\n")
        decoder = codecs.getincrementaldecoder("utf-8")("backslashreplace")
        with (output / "serial-rx.bin").open("xb", buffering=0) as raw, \
                (output / "serial-rx.txt").open("x", encoding="utf-8", newline="") as decoded:
            print(f"Opened {port}; passive RX only; baud rates unchanged.", file=sys.stderr, flush=True)
            try:
                while True:
                    readable, _, _ = select.select([fd], [], [], 1)
                    if not readable:
                        continue
                    try:
                        data = os.read(fd, 16384)
                    except BlockingIOError:
                        continue
                    except OSError as error:
                        reason = f"Serial read error: {error} (partial capture retained)"
                        status = 1
                        break
                    if not data:
                        break
                    raw.write(data)
                    total += len(data)
                    text = decoder.decode(data)
                    decoded.write(text)
                    decoded.flush()
                    sys.stdout.write(text)
                    sys.stdout.flush()
            except KeyboardInterrupt:
                reason = "Stopped by Ctrl+C"
            text = decoder.decode(b"", final=True)
            decoded.write(text)
            sys.stdout.write(text)
            sys.stdout.flush()
    finally:
        if old is not None:
            try:
                termios.tcsetattr(fd, termios.TCSANOW, old)
            except termios.error:
                pass  # An unplugged port may no longer accept terminal settings.
        os.close(fd)
    print(f"{reason}; saved {total} raw bytes to {output}", file=sys.stderr, flush=True)
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="explicit serial path; otherwise wait for a unique /dev/cu.usbmodem*")
    parser.add_argument("--output", type=Path, help="new local capture directory (must not exist)")
    parser.add_argument("--wait-seconds", type=int, default=600, metavar="0..600",
                        help="maximum wait for port appearance, default 600 seconds")
    parser.add_argument("--list", action="store_true", help="list matching macOS ports without opening them")
    args = parser.parse_args(argv)
    if os.name != "posix":
        parser.error("Windows is unsupported; a separate passive monitor is required and is unvalidated")
    if not 0 <= args.wait_seconds <= 600:
        parser.error("--wait-seconds must be between 0 and 600")
    if args.list:
        for port in sorted(glob.glob("/dev/cu.usbmodem*")):
            print(port)
        return 0
    if args.output is None:
        parser.error("--output is required (a new local directory)")
    try:
        args.output.mkdir()  # Exclusive creation also refuses files and symlinks.
    except OSError as error:
        parser.error(f"Cannot create new output directory: {error}")
    try:
        return capture(wait_for_port(args.port, args.wait_seconds), args.output)
    except KeyboardInterrupt:
        print(f"Stopped before capture; output directory: {args.output}", file=sys.stderr)
        return 0
    except (OSError, ValueError) as error:
        print(f"Capture failed: {error}; partial files, if any, remain in {args.output}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
