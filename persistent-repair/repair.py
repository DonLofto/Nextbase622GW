#!/usr/bin/env python3
"""Guided macOS/Windows Drive A repair. Camera writes use reviewed SD hooks."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import fnmatch
import glob
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid
import windows_host

from results import (ADVANCED_HASHES, RepairError, digest, read_regular, is_linked,
                     verify_advanced, verify_backup, verify_persistence,
                     verify_preflight)


MARKER = "nb-a-repair.json"
OWNER = "Nextbase622GW guided Drive A repair 1"
CONTROL_NAMES = {"autoexec.ash", "usb.console", "nb-a-preflight.sh", "bt-nand-backup.sh",
                 "nb-mtd-readonly", "nb-mtd-readonly.sha256", "bt-persistence-capture.sh"}
CLAIMS = {"NBFA01.claimed", "NBFA02.claimed", "bt-nand-backup.claimed",
          "bt-persistence-capture.claimed"}
PAYLOAD_NAMES = {"preflight.autoexec.ash", "nb-a-preflight.sh"}


def exists(path):
    return path.exists() or is_linked(path)


def plain_directory(path):
    path = Path(path).expanduser().absolute()
    if not path.is_dir() or any(is_linked(p) for p in (path, *path.parents)):
        raise RepairError("Directory is missing or linked; nothing was changed.")
    return path


def write_new(path, data):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if read_regular(path) != data:
        raise RepairError("Copied file did not verify; do not boot the camera.")


def verify_identity(card, expected=None):
    card = plain_directory(card)
    if [p.name for p in card.iterdir() if p.name.casefold() == "nextbase.info"] != ["Nextbase.info"]:
        raise RepairError("Require one regular Nextbase.info file with its original name.")
    data = read_regular(card / "Nextbase.info", limit=65536)
    fields = {"model": [], "firmware": [], "serial no": [], "sd card serial no": []}
    for line in data.decode("ascii", errors="replace").splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip().lower() in fields:
            fields[key.strip().lower()].append(value.strip())
    if fields["model"] != ["622GW"] or fields["firmware"] != ["R13.3"]:
        raise RepairError("Only one Model: 622GW and Firmware: R13.3 is supported.")
    identifiers = []
    for name in ("serial no", "sd card serial no"):
        values = fields[name]
        if (len(values) != 1 or re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", values[0]) is None
                or values[0].lower() in ("unknown", "none", "na")
                or re.fullmatch(r"(?:0[xX])?0+", values[0])):
            raise RepairError("Unique nonzero camera and SD-card serial fields are required.")
        identifiers.append(values[0])
    # Nextbase.info also contains changing battery, space, time and Bluetooth fields.
    material = "model=622GW\nfirmware=R13.3\nserial_no=%s\nsd_serial_no=%s\n" % tuple(identifiers)
    identity = hashlib.sha256(material.encode("ascii")).hexdigest()
    if expected is not None and identity != expected:
        raise RepairError("Camera/card identity changed; this session cannot adopt it.")
    return identity


def check_clean_card(card):
    for path in card.iterdir():
        name = path.name.casefold()
        if (name == MARKER or name in {n.casefold() for n in CLAIMS | CONTROL_NAMES}
                or any(fnmatch.fnmatchcase(name, pattern) for pattern in
                       ("fw*.bin", "ld*.bin", "autoexec*.ash", "usb*.console", "bt-*.sh",
                        "bt-*.claimed", "bt-nand-backup-*", "bt-persistence-capture-*",
                        "nb-bt-*", "nb-a-*", ".nb-a-stage-*"))):
            raise RepairError("Existing repair controls, claims, results or update files require review first.")


def check_conflicts(card, owned):
    for path in card.iterdir():
        name = path.name.casefold()
        if path.name in CLAIMS:
            plain_directory(path)
            continue
        if (any(fnmatch.fnmatchcase(name, pattern) for pattern in
                ("fw*.bin", "ld*.bin", "autoexec*.ash", "usb*.console", "bt-*.sh",
                 "bt-*.claimed", "nb-bt-*", "nb-a-*.sh", "nbfa*.claimed"))
                or name in {n.casefold() for n in CONTROL_NAMES}):
            if path.name not in owned:
                raise RepairError("An unknown update/startup control or claim appeared; nothing was staged.")


def verify_kit(root):
    advanced = root / "advanced/internal-drive-a"
    payload = root / "persistent-repair/payload"
    verify_advanced(advanced)
    lines = read_regular(payload / "SHA256SUMS", limit=4096).decode("ascii").splitlines()
    recorded = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9.-]+)", line)
        if not match or match[2] not in PAYLOAD_NAMES or match[2] in recorded:
            raise RepairError("Malformed or duplicated guided preflight manifest.")
        recorded[match[2]] = match[1]
    if set(recorded) != PAYLOAD_NAMES or any(digest(payload / n) != h for n, h in recorded.items()):
        raise RepairError("Guided preflight files failed verification. Download a fresh kit.")
    pinned = {advanced / name: value for name, value in ADVANCED_HASHES.items()}
    pinned.update({payload / name: value for name, value in recorded.items()})
    return advanced, payload, pinned


class Journal:
    def __init__(self, directory, data):
        self.directory, self.data = directory, data

    def save(self):
        plain_directory(self.directory)
        target = self.directory / "state.json"
        if is_linked(target):
            raise RepairError("Linked session journal refused.")
        with tempfile.NamedTemporaryFile(dir=self.directory, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write((json.dumps(self.data, indent=2) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        durable_replace(temporary, target)

    @classmethod
    def create(cls, base, card, identity):
        if exists(card / MARKER):
            raise RepairError("This card already has a session. Inspect/disarm it; do not start another repair.")
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
        plain_directory(base)
        session = str(uuid.uuid4())
        directory = base / session
        directory.mkdir(mode=0o700)
        data = {"owner": OWNER, "session": session, "identity": identity, "phase": "prepared",
                "owned": {}, "stage": None, "captures": {}, "format_consent_consumed": False}
        journal = cls(directory, data)
        journal.save()
        marker = {k: data[k] for k in ("owner", "session", "identity")}
        write_new(card / MARKER, (json.dumps(marker, sort_keys=True) + "\n").encode("ascii"))
        return journal

    @classmethod
    def load(cls, base, card, identity):
        marker = json.loads(read_regular(card / MARKER, limit=4096))
        if (not isinstance(marker, dict) or set(marker) != {"owner", "session", "identity"} or marker["owner"] != OWNER
                or marker["identity"] != identity or not isinstance(marker["session"], str)
                or re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", marker["session"]) is None):
            raise RepairError("Unknown or changed session marker; automatic adoption is refused.")
        directory = plain_directory(base / marker["session"])
        data = json.loads(read_regular(directory / "state.json", limit=1048576))
        if not isinstance(data, dict) or any(data.get(k) != v for k, v in marker.items()):
            raise RepairError("Local journal does not match this card.")
        validate_owned(data.get("owned"))
        if not isinstance(data.get("format_consent_consumed"), bool) or not isinstance(data.get("phase"), str):
            raise RepairError("Session state is invalid; automatic adoption is refused.")
        return cls(directory, data)

    def authorize_format(self, confirmation):
        if (confirmation != "FORMAT DRIVE A ONCE" or self.data.get("phase") != "rehearsed"
                or self.data.get("format_consent_consumed")):
            raise RepairError("Format was not authorized, or its one authorization is already consumed.")
        self.data.update(format_consent_consumed=True, phase="format_pending")
        self.save()  # Durable before removing the rehearsal hook or staging format bytes.


def validate_owned(owned):
    if not isinstance(owned, dict) or any(
            n not in CONTROL_NAMES or not isinstance(h, str) or re.fullmatch(r"[0-9a-f]{64}", h) is None
            for n, h in owned.items()):
        raise RepairError("Journal contains unknown control names or invalid hashes.")


def check_binding(card, journal):
    verify_identity(card, journal.data["identity"])
    expected = {k: journal.data[k] for k in ("owner", "session", "identity")}
    if json.loads(read_regular(card / MARKER, limit=4096)) != expected:
        raise RepairError("Card session marker changed; no controls were changed.")


def is_windows():
    return os.name == "nt"


def durable_replace(source, destination):
    if is_windows():
        windows_host.move_file(source, destination, replace=True)
    else:
        os.replace(source, destination)
        fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def move_exclusive(source, destination):
    if is_windows():
        windows_host.move_file(source, destination)
        return
    subprocess.run(["/bin/mv", "-n", str(source), str(destination)], check=True)
    if exists(source):
        raise RepairError("A destination appeared during staging; it was not overwritten.")


def stage_controls(card, journal, files, phase, expected=None):
    check_binding(card, journal)
    check_conflicts(card, set())
    hashes = {n: digest(p) for n, p in files.items()}
    validate_owned(hashes)
    if expected is not None and hashes != expected:
        raise RepairError("Source files differ from the verified kit; nothing was staged.")
    if hashes.get("autoexec.ash") == ADVANCED_HASHES["format-a-once.autoexec.ash"]:
        if (not journal.data["format_consent_consumed"] or journal.data["phase"] != "format_pending"
                or phase != "format_armed"):
            raise RepairError("The format publisher requires fresh, durable, consumed approval.")
        require_empty_claim(card, "NBFA01.claimed")
        if exists(card / "NBFA02.claimed"):
            raise RepairError("Format claim already exists; it will never be re-armed.")
    if "autoexec.ash" not in files or journal.data["owned"]:
        raise RepairError("Previous controls must be disarmed before staging another phase.")
    if any(exists(card / n) for n in files):
        raise RepairError("Existing control files were not overwritten.")
    stage = card / (".nb-a-stage-" + str(uuid.uuid4()))
    journal.data.update(phase=phase, owned=hashes, stage=stage.name)
    journal.save()
    stage.mkdir(mode=0o700)
    for name, source in files.items():
        write_new(stage / name, read_regular(source))
        if digest(stage / name) != hashes[name]:
            raise RepairError("Staged source changed; do not boot the camera.")
    for name in [n for n in files if n != "autoexec.ash"] + ["autoexec.ash"]:
        move_exclusive(stage / name, card / name)
        if digest(card / name) != hashes[name]:
            raise RepairError("Installed control changed; do not boot the camera.")
    stage.rmdir()
    journal.data["stage"] = None
    journal.save()


def clear_controls(card, journal):
    check_binding(card, journal)
    owned = journal.data["owned"]
    validate_owned(owned)
    for name, expected in owned.items():
        if exists(card / name) and digest(card / name) != expected:
            raise RepairError("A control was modified; automatic removal refused.")
    stage = None
    if journal.data.get("stage"):
        name = journal.data["stage"]
        if not isinstance(name, str) or re.fullmatch(r"\.nb-a-stage-[0-9a-f-]{36}", name) is None:
            raise RepairError("Unsafe staging directory in journal.")
        stage = card / name
        if exists(stage):
            plain_directory(stage)
            for path in stage.iterdir():
                if path.name not in owned or digest(path) != owned[path.name]:
                    raise RepairError("Staging contains unknown bytes; automatic removal refused.")
    # Validate all bytes before deletion; the active startup hook is removed first.
    for name in ["autoexec.ash", "usb.console"] + sorted(CONTROL_NAMES - {"autoexec.ash", "usb.console"}):
        if name in owned and exists(card / name):
            (card / name).unlink()
    if stage is not None and exists(stage):
        for path in stage.iterdir():
            path.unlink()
        stage.rmdir()
    journal.data.update(owned={}, stage=None)
    journal.save()


def require_empty_claim(card, name):
    path = plain_directory(card / name)
    if any(path.iterdir()):
        raise RepairError("Native one-shot claim is not an empty directory; stop.")


def snapshot_results(source, destination):
    source = plain_directory(source)
    files = list(source.iterdir())
    if not files or len(files) > 100:
        raise RepairError("Result directory is empty or unexpectedly large.")
    captured = {p.name: read_regular(p, limit=16 * 1024 * 1024) for p in files}
    if sum(map(len, captured.values())) > 40 * 1024 * 1024:
        raise RepairError("Result directory exceeds the documented capture size.")
    destination.mkdir(mode=0o700)
    for name, data in captured.items():
        write_new(destination / name, data)
        if digest(source / name) != hashlib.sha256(data).hexdigest():
            raise RepairError("Card result changed while copying; stop.")


def boot_ready(data, phase):
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", data.decode("utf-8", errors="replace"))
    lines = [line.strip(" \t\r\x00") for line in text.splitlines()
             if "echo " not in line and "if mkdir" not in line]
    def count(marker):
        return sum(bool(re.search(r"(?:^|\s)" + re.escape(marker) + r"$", line)) for line in lines)
    if any(s in text.lower() for s in ("syntax error", "preflight refused:", "preflight incomplete:", "nand capture refused:", "format failed")):
        raise RepairError("Console reports a refusal or failure. Preserve its private capture; stop.")
    dry, skip = count("NBFA01_DRYRUN"), count("NBFA01_SKIP")
    begin, used, done = count("NBFA02_BEGIN"), count("NBFA02_SKIP"), count("Drive 'A' format done.")
    if max(dry, skip, begin, used, done) > 1:
        raise RepairError("Repeated one-shot output; no automatic continuation.")
    if phase == "backup":
        return count("NAND capture wrapper ended; inspect SD result files.") == 1
    if phase in ("dryrun", "rehearsal_skip"):
        if (phase == "dryrun" and skip) or (phase == "rehearsal_skip" and dry) or begin or done:
            raise RepairError("Wrong rehearsal branch; stop.")
        return bool(dry if phase == "dryrun" else skip)
    if phase == "format":
        if used:
            raise RepairError("Format claim was already consumed; never retry it.")
        if not (begin and done):
            return False
        begin_line = next(i for i, line in enumerate(lines) if re.search(r"(?:^|\s)NBFA02_BEGIN$", line))
        done_line = next(i for i, line in enumerate(lines) if re.search(r"(?:^|\s)Drive 'A' format done\.$", line))
        return begin_line < done_line
    if phase == "stock":
        if begin or done:
            raise RepairError("A second format was observed; stop and preserve the capture.")
        return bool(used and re.search(r"\b(?:AMSG_EVENT_)?BT_BOOTED\b", text))
    if phase == "observer":
        if begin or done:
            raise RepairError("Unexpected format during persistence observation; stop.")
        return count("Persistence observer ended; inspect SD results.") == 1
    raise RepairError("Unknown boot phase.")


def read_live_capture(path, limit=32 * 1024 * 1024):
    """Poll an append-only private stream; immutable result checks stay strict."""
    if not exists(path):
        return b""
    if any(is_linked(p) for p in (path, *path.parents)):
        raise RepairError("Linked live capture refused.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise RepairError("Live capture is not a bounded regular stream.")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise RepairError("Live capture exceeded its size limit.")
    return data


def passive_reader_command(tool, output):
    command = [sys.executable, "--passive-reader"] if getattr(sys, "frozen", False) else [sys.executable, str(tool)]
    return command + ["--output", str(output)]


class MacHost:
    label = "macOS"

    def __init__(self, port=None):
        self.port = port

    def roots(self):
        return glob.glob("/Volumes/*")

    def info(self, card):
        result = subprocess.run(["/usr/sbin/diskutil", "info", "-plist", str(card)], capture_output=True, check=True)
        info = plistlib.loads(result.stdout)
        if (info.get("Internal") is not False or info.get("MountPoint") != str(card)
                or info.get("FilesystemType") not in ("exfat", "msdos")
                or info.get("WritableVolume") is not True or info.get("WritableMedia") is not True):
            raise RepairError("Require the root of a writable external exFAT/FAT SD volume.")

    def verify(self, card):
        self.info(card)
        result = subprocess.run(["/usr/sbin/diskutil", "verifyVolume", str(card)], capture_output=True,
                                env={**os.environ, "LC_ALL": "C"})
        if result.returncode != 0:
            raise RepairError("SD filesystem verification failed. Preserve data and resolve it separately; no repair was run.")
        return result.stdout + result.stderr

    def eject(self, card):
        subprocess.run(["/usr/sbin/diskutil", "eject", str(card)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def capture(self, tool, output, phase):
        if exists(output):
            raise RepairError("Capture path already exists; stale output cannot authorize another boot.")
        with (output.parent / (output.name + "-reader.txt")).open("xb") as errors:
            command = passive_reader_command(tool, output)
            if self.port:
                command.extend(["--port", self.port])
            process = subprocess.Popen(command,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errors)
            started = time.monotonic()
            try:
                while True:
                    raw = output / "serial-rx.bin"
                    data = read_live_capture(raw)
                    if boot_ready(data, phase):
                        break
                    if process.poll() is not None:
                        raise RepairError("Console closed before the required result. No reboot or retry is authorized.")
                    # shortcut: format has no proven deadline; the owner can stop capture
                    # with Ctrl+C, which never interrupts camera power or retries anything.
                    if phase != "format" and time.monotonic() - started > 1200:
                        raise RepairError("Required console result missing; partial evidence retained.")
                    time.sleep(0.25)
            finally:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        process.wait(timeout=5)
        if process.returncode != 0:
            raise RepairError("Passive reader reported an error; inspect its private log.")
        data = read_regular(output / "serial-rx.bin", limit=32 * 1024 * 1024)
        if not boot_ready(data, phase):
            raise RepairError("Required boot result was not captured.")
        return data


def default_host(port=None):
    if is_windows():
        return windows_host.WindowsHost(port=port, ready=boot_ready)
    return MacHost(port)


class Wizard:
    def __init__(self, root, volume=None, session_root=None, host=None, ask=input, say=print):
        self.root = root
        self.volume = Path(volume).expanduser().absolute() if volume else None
        self.session_root = session_root or Path.home() / "Nextbase622GW Repairs"
        self.host, self.ask, self.say = host if host is not None else default_host(), ask, say
        self.journal = None
        self.advanced, self.payload, self.pinned = verify_kit(root)

    def answer(self, prompt):
        try:
            return self.ask(prompt).strip()
        except (EOFError, KeyboardInterrupt) as error:
            raise RepairError("Stopped by the owner. No operation will be retried.") from error

    def confirm(self, prompt):
        if self.answer(prompt + " Type YES: ") != "YES":
            raise RepairError("Owner did not confirm; no automatic continuation.")

    def card(self, identity=None):
        if self.volume is not None:
            candidates = [plain_directory(self.volume)]
        else:
            candidates = []
            for name in self.host.roots():
                try:
                    path = plain_directory(Path(name))
                    verify_identity(path, identity)
                    candidates.append(path)
                except (RepairError, OSError):
                    continue
        if len(candidates) != 1:
            raise RepairError("Expected one compatible card. Connect only that card or use --volume PATH.")
        card = candidates[0]
        verify_identity(card, identity)
        self.host.info(card)
        return card

    def check_owned(self, card, retired=None):
        verify_identity(card, self.journal.data["identity"])
        loaded = Journal.load(self.session_root, card, self.journal.data["identity"])
        if loaded.directory != self.journal.directory:
            raise RepairError("Returned card belongs to a different session.")
        for name, expected in self.journal.data["owned"].items():
            path = card / name
            if name == "usb.console" and not exists(path) and retired:
                path = card / retired
            if digest(path) != expected:
                raise RepairError("Returned control bytes changed or are missing; stop.")
        check_conflicts(card, set(self.journal.data["owned"]))

    def returned(self, retired=None):
        self.say("Stop recording, shut the camera down normally, then move its card to the reader.")
        self.confirm("Is the camera fully off and the card connected through its reader?")
        card = self.card(self.journal.data["identity"])
        self.check_owned(card, retired)
        return card

    def stage(self, card, phase, hook, extra):
        files = {name: self.advanced / name for name in extra}
        files["autoexec.ash"] = hook
        self.install(card, files, phase)

    def install(self, card, files, phase):
        verify_kit(self.root)
        if any(path not in self.pinned for path in files.values()):
            raise RepairError("An unverified source cannot be staged.")
        stage_controls(card, self.journal, files, phase,
                       expected={name: self.pinned[path] for name, path in files.items()})

    def boot(self, card, phase):
        self.check_owned(card)
        if phase in ("rehearsal_skip", "format"):
            require_empty_claim(card, "NBFA01.claimed")
        if phase == "stock":
            require_empty_claim(card, "NBFA02.claimed")
        output = self.journal.directory / ("boot-" + phase)
        if exists(output):
            raise RepairError("This boot already has evidence; it will not be repeated automatically.")
        self.journal.data["phase"] = "boot_" + phase
        self.journal.save()
        self.host.eject(card)
        self.say("Card safely ejected. Put it into the powered-off camera, connect the BODY USB data port")
        self.say("to this computer and turn it on. Keep USB power connected. Passive capture is waiting.")
        self.say("Ctrl+C stops this launcher only. It does not stop a format or authorize another attempt.")
        data = self.host.capture(self.root / "tools/capture_rtos.py", output, phase)
        if not boot_ready(data, phase):
            raise RepairError("Required result missing; stop.")
        self.journal.data["captures"][phase] = hashlib.sha256(data).hexdigest()
        self.journal.save()
        self.say("Required console result captured privately.")

    def recheck_capture(self, phase):
        path = self.journal.directory / ("boot-" + phase) / "serial-rx.bin"
        data = read_regular(path, limit=32 * 1024 * 1024)
        if (hashlib.sha256(data).hexdigest() != self.journal.data["captures"].get(phase)
                or not boot_ready(data, phase)):
            raise RepairError("Saved boot evidence changed; stop.")

    def inspect_or_disarm(self, card):
        self.journal = Journal.load(self.session_root, card, verify_identity(card))
        self.say("Existing session: " + self.journal.data["phase"])
        self.say("Private evidence: " + str(self.journal.directory))
        self.say("Restarting never resumes or re-arms a format. NBFA02 and all results are retained.")
        if self.journal.data["format_consent_consumed"]:
            self.say("Format authorization was consumed. If its result is unknown, no retry or completion is assumed.")
        if self.answer("Type DISARM to remove verified owned controls from this reader, or Return to quit: ") == "DISARM":
            self.confirm("Is the camera fully off, with this card in its reader?")
            known = {name: {value} for name, value in ADVANCED_HASHES.items() if name in CONTROL_NAMES}
            known["autoexec.ash"] = {digest(self.advanced / n) for n in
                                    ("dry-run.autoexec.ash", "format-a-once.autoexec.ash", "persistence.autoexec.ash")}
            known["autoexec.ash"].add(digest(self.payload / "preflight.autoexec.ash"))
            known["nb-a-preflight.sh"] = {digest(self.payload / "nb-a-preflight.sh")}
            validate_owned(self.journal.data["owned"])
            if any(h not in known.get(n, set()) for n, h in self.journal.data["owned"].items()):
                raise RepairError("Journal no longer identifies this kit's controls; manual review required.")
            clear_controls(card, self.journal)
            self.journal.data["phase"] = "disarmed"
            self.journal.save()
            self.host.eject(card)
            self.say("Owned controls removed and card ejected. Results/claims retained; this is not a success verdict.")

    def run(self):
        self.say("Nextbase 622GW / R13.3 — guided internal Drive A repair (" + getattr(self.host, "label", "computer") + ")")
        self.say("Formatting erases A's settings/files. Proven on one camera; this new wizard is host-tested only.")
        self.say("You need a card reader, body USB data cable and steady power.")
        self.answer("With the camera off, connect its microSD through the reader. Press Return: ")
        card = self.card()
        if exists(card / MARKER):
            self.inspect_or_disarm(card)
            return
        check_clean_card(card)
        self.confirm("Does the camera screen also say 622GW/R13.3, is the camera OFF, and is the card in a reader?")
        self.confirm("Have you preserved the files/settings/recordings you need and arranged steady USB power? No videos are copied by this tool.")
        health = self.host.verify(card)
        identity = verify_identity(card)
        self.journal = Journal.create(self.session_root, card, identity)
        write_new(self.journal.directory / "initial-sd-check.txt", health)
        write_new(self.journal.directory / "Nextbase.info", read_regular(card / "Nextbase.info", limit=65536))
        self.say("Keep this private evidence folder: " + str(self.journal.directory))

        self.say("1/5 Prepare: check the exact build/fault and capture Drive A through read-only interfaces.")
        files = {n: self.advanced / n for n in ("bt-nand-backup.sh", "nb-mtd-readonly", "nb-mtd-readonly.sha256", "usb.console")}
        files.update({"nb-a-preflight.sh": self.payload / "nb-a-preflight.sh",
                      "autoexec.ash": self.payload / "preflight.autoexec.ash"})
        self.install(card, files, "backup_staged")
        self.boot(card, "backup")
        card = self.returned("bt-nand-backup-1/usb.console.used")
        for name in ("nb-a-preflight", "bt-nand-backup-1"):
            snapshot_results(card / name, self.journal.directory / name)
        hook_hash, script_hash = digest(files["autoexec.ash"]), digest(files["nb-a-preflight.sh"])
        verify_preflight(self.journal.directory / "nb-a-preflight", identity, hook_hash, script_hash)
        verify_backup(self.journal.directory / "bt-nand-backup-1", hook_hash)
        self.say("Exact build/fault and complete A capture verified. A restore method is NOT proven.")
        clear_controls(card, self.journal)

        for name in ("NBFA01.claimed", "NBFA02.claimed"):
            if exists(card / name):
                raise RepairError("Native claim already exists before rehearsal; stop.")
        self.stage(card, "rehearsal_staged", self.advanced / "dry-run.autoexec.ash", ("usb.console",))
        self.boot(card, "dryrun")
        card = self.returned()
        require_empty_claim(card, "NBFA01.claimed")
        self.boot(card, "rehearsal_skip")
        card = self.returned()
        require_empty_claim(card, "NBFA01.claimed")
        if exists(card / "NBFA02.claimed"):
            raise RepairError("Format claim exists before approval; never re-arm it.")
        self.recheck_capture("dryrun")
        self.recheck_capture("rehearsal_skip")
        verify_preflight(self.journal.directory / "nb-a-preflight", identity, hook_hash, script_hash)
        verify_backup(self.journal.directory / "bt-nand-backup-1", hook_hash)
        write_new(self.journal.directory / "pre-format-sd-check.txt", self.host.verify(card))
        self.journal.data["phase"] = "rehearsed"
        self.journal.save()

        self.say("2/5 Run once: ALL files/settings on internal Drive A will be erased.")
        self.say("The capture has no proven restore route. Power-loss/application isolation and lasting repair are not guaranteed.")
        self.say("Approval is consumed before staging; restarting cannot authorize a second attempt.")
        self.journal.authorize_format(self.answer("To approve ONE internal A format, type FORMAT DRIVE A ONCE: "))
        clear_controls(card, self.journal)
        self.stage(card, "format_armed", self.advanced / "format-a-once.autoexec.ash", ("usb.console",))
        self.boot(card, "format")
        self.journal.data["phase"] = "format_success"
        self.journal.save()
        card = self.returned()
        require_empty_claim(card, "NBFA02.claimed")

        self.say("3/5 Pair: next boot must SKIP formatting and start stock Bluetooth.")
        self.boot(card, "stock")
        self.confirm("Stop recording → Connected App → Setup phone → OK. Pair in the Nextbase app. Can it show the camera/recordings?")
        card = self.returned()
        require_empty_claim(card, "NBFA02.claimed")
        clear_controls(card, self.journal)
        if exists(card / "bt-persistence-capture.claimed"):
            raise RepairError("Observer claim already exists; stop.")
        self.stage(card, "observer_staged", self.advanced / "persistence.autoexec.ash",
                   ("bt-persistence-capture.sh", "usb.console"))

        self.say("4/5 Verify after reboot: use the existing pairing; do NOT choose Setup phone again.")
        self.boot(card, "observer")
        self.confirm("Can the existing app camera show the camera/recordings without pairing again?")
        card = self.returned("bt-persistence-capture-1/usb.console.used")
        snapshot_results(card / "bt-persistence-capture-1", self.journal.directory / "bt-persistence-capture-1")
        verify_persistence(self.journal.directory / "bt-persistence-capture-1")

        self.say("5/5 Clean up: remove owned startup controls; retain NBFA claims and private evidence.")
        clear_controls(card, self.journal)
        check_conflicts(card, set())
        if any(exists(card / n) for n in ("autoexec.ash", "usb.console", "usb.multi.console")):
            raise RepairError("An active hook/token remains; ordinary startup is not established.")
        require_empty_claim(card, "NBFA02.claimed")
        write_new(self.journal.directory / "final-sd-check.txt", self.host.verify(card))
        self.journal.data["phase"] = "cleaned"
        self.journal.save()
        self.host.eject(card)
        self.say("Card ejected. Return it to the powered-off camera and boot normally. Choose Power On if the PC menu appears.")
        self.confirm("Does the app reconnect and show the camera/recordings without Setup phone or pairing again?")
        self.journal.data["phase"] = "complete"
        self.journal.save()
        self.say("Repair verified by your two existing-pairing reconnections. All active hooks/tokens are removed.")
        self.say("Keep NBFA02, the inert session marker and private evidence. Do not repeat the format.")


def resource_root():
    directory = Path(__file__).resolve().parent
    return directory if getattr(sys, "frozen", False) else directory.parent


def interactive_console():
    # Windows isatty() also accepts NUL; require a real console input handle.
    return (sys.stdin is not None and sys.stdin.isatty()
            and (not is_windows() or windows_host.native().interactive_console()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--volume", type=Path, help="explicit mounted SD root if automatic selection is ambiguous")
    parser.add_argument("--port", help="an already identified passive serial path if automatic selection is ambiguous")
    parser.add_argument("--check-kit", action="store_true", help="verify repair files only; no device access")
    args = parser.parse_args(argv)
    if args.check_kit:
        try:
            verify_kit(resource_root())
            read_regular(Path(windows_host.__file__).with_name("windows-volume.ps1"), limit=65536)
            print("Repair kit files verified. No device was accessed.")
            return 0
        except (RepairError, OSError, ValueError) as error:
            print("Stopped: " + str(error), file=sys.stderr)
            return 1
    if sys.platform not in ("darwin", "win32"):
        parser.error("The guided launcher supports macOS and Windows; use the manual path elsewhere.")
    if sys.version_info < (3, 9) or not interactive_console():
        parser.error("Python 3.9+ and an interactive terminal are required; no noninteractive confirmation option exists.")
    wizard = None
    try:
        host = default_host(args.port)
        wizard = Wizard(resource_root(), args.volume, host=host)
        with host.awake() if hasattr(host, "awake") else nullcontext():
            wizard.run()
        return 0
    except (RepairError, OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        print("Stopped: " + str(error), file=sys.stderr)
        if wizard and wizard.journal:
            print("Private session: " + str(wizard.journal.directory), file=sys.stderr)
            if wizard.journal.data.get("format_consent_consumed"):
                print("Format approval is consumed. If completion is unknown, keep camera power connected; never re-arm or retry.", file=sys.stderr)
            print("Restarting offers inspection/disarming only. No automatic retry occurs.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
