"""Validate private saved repair evidence without printing configuration or keys."""
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import xml.etree.ElementTree as ET


class RepairError(ValueError):
    """Evidence is missing, unsafe, incomplete, or incompatible."""


# Reviewed bytes: backup wrapper version gates changed in 0.7.0; other assets stay frozen.
ADVANCED_HASHES = {
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
_VENDOR_FIELDS = {"amazon_sha256", "bsa_sha256", "hcd_sha256"}
_BACKUP_FILES = (
    "DRIVE_A-corrected-main.bin", "DRIVE_A-raw-main.bin", "DRIVE_A-raw-oob.bin",
    "DRIVE_A-badblocks.tsv", "read-status.tsv", "helper-summary.txt",
    "helper-ecc-before.txt", "helper-ecc-after.txt",
)
_BACKUP_STATUSES = (
    "helper-copy", "local-before", "sysfs-before", "dmesg-before", "helper-read",
    "local-after", "sysfs-after", "dmesg-after", "capture-hashes", "verify-hashes", "sync-output",
)
_GEOMETRY = {
    "name": "DRIVE_A", "type": "nand", "size": "12058624", "erasesize": "131072",
    "writesize": "2048", "oobsize": "128", "offset": "203685888", "flags": "0x400",
    "dev": "90:18", "ecc_strength": "8", "ecc_step_size": "512", "bitflip_threshold": "6",
}


def _require(condition, message):
    if not condition:
        raise RepairError(message)


def is_linked(path):
    """Windows junctions/cloud reparse points need the same refusal as links."""
    path = Path(path)
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except FileNotFoundError:
        return False


def read_regular(path, limit=32 * 1024 * 1024):
    """Bounded regular-file read; refuse links, special files and changing data."""
    path = Path(path).absolute()
    _require(isinstance(limit, int) and limit >= 0, "Invalid verification read limit.")
    try:
        _require(not any(is_linked(p) for p in (path, *path.parents)), "Linked verification path refused.")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            before = os.fstat(stream.fileno())
            _require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, "Expected a bounded regular verification file.")
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            _require(len(data) <= limit and len(data) == before.st_size and
                     (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                     (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
                     "Verification file changed during reading.")
            return data
    except OSError:
        raise RepairError("Cannot read a required regular verification file.") from None


def digest(path):
    return hashlib.sha256(read_regular(path)).hexdigest()


def _text(path, limit=2 * 1024 * 1024):
    try:
        return read_regular(path, limit).decode("utf-8")
    except UnicodeError:
        raise RepairError("Verification text has an unsupported encoding.") from None


def _fields(text):
    values = {}
    _require(text.endswith("\n") and "\r" not in text, "Malformed verification fields.")
    for line in text.splitlines():
        _require("=" in line, "Malformed verification fields.")
        key, value = line.split("=", 1)
        _require(re.fullmatch(r"[a-z_][a-z_0-9]*", key) and key not in values, "Duplicate or invalid verification field.")
        values[key] = value
    return values


def _manifest(folder, filename, expected, allow_paths=False):
    text = _text(Path(folder) / filename, 64 * 1024)
    _require(text.endswith("\n") and "\r" not in text, "Malformed verification manifest.")
    recorded = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})  ([^\r\n]+)", line)
        _require(match is not None, "Malformed verification manifest.")
        value, raw = match.groups()
        parts = PurePosixPath(raw)
        name = parts.name if allow_paths else raw
        _require("\\" not in raw and ".." not in parts.parts and name in expected and name not in recorded,
                 "Unexpected or duplicate verification manifest entry.")
        recorded[name] = value.lower()
    _require(set(recorded) == set(expected), "Verification manifest is incomplete.")
    for name, value in recorded.items():
        _require(digest(Path(folder) / name) == value, "Saved artifact hash does not verify.")
    return recorded


def verify_advanced(directory):
    """Pin both the manifest and each asset to the independently reviewed bytes."""
    recorded = _manifest(directory, "SHA256SUMS", ADVANCED_HASHES)
    _require(recorded == ADVANCED_HASHES, "Advanced assets differ from the reviewed files.")


def _a_mounts(text, targets):
    for target in targets:
        matches = [line.split() for line in text.splitlines() if len(line.split()) == 6 and line.split()[1] == target]
        _require(len(matches) == 1 and matches[0][0] == "a:" and matches[0][2] == "ambafs",
                 "Stock internal AmbaFS mount evidence is missing or ambiguous.")


def verify_preflight(folder, identity_hash, hook_hash, script_hash, firmware):
    folder = Path(folder)
    _manifest(folder, "SHA256SUMS", {"RESULT.txt", "failure-console.bin", "mounts.txt"})
    text = _text(folder / "RESULT.txt", 8192)
    _require(text.startswith("PREFLIGHT_VERIFIED\n"), "Device compatibility preflight did not succeed.")
    expected = dict(model="622GW", firmware=firmware, machine="armv7l",
                    identity_sha256=identity_hash, script_sha256=script_hash, hook_sha256=hook_hash,
                    fl_mount="ambafs_a", failure="BT_DEFAULT_CONFIG_CREATE_FAILED")
    fields = _fields(text.split("\n", 1)[1])
    _require(set(fields) == set(expected) | _VENDOR_FIELDS | {"kernel"} and
             all(fields[key] == value for key, value in expected.items()),
             "Device compatibility preflight does not match this session.")
    _require(re.fullmatch(r"[ -~]{1,64}", firmware) is not None and
             re.fullmatch(r"[A-Za-z0-9._+-]{1,128}", fields["kernel"]) is not None,
             "Firmware/kernel metadata is malformed.")
    _require(all(re.fullmatch(r"[0-9a-f]{64}", fields[key]) and fields[key] != "0" * 64 for key in _VENDOR_FIELDS),
             "Vendor hash evidence is malformed.")
    console = read_regular(folder / "failure-console.bin", 16384)
    _require(re.search(rb"bt_config\.xml.*Unable to Create defaul", console, re.S) is not None,
             "The documented configuration-creation failure is not established.")
    _a_mounts(_text(folder / "mounts.txt"), ("/tmp/FL0",))


def _status(folder, name):
    _require(read_regular(folder / (name + "-status.txt"), 1024) == b"exit_status=0\n",
             "A required capture command failed, timed out, or has no result.")
    read_regular(folder / (name + ".txt"), 2 * 1024 * 1024)


def _uint(value):
    _require(len(value) <= 20 and re.fullmatch(r"[0-9]+", value) is not None, "Invalid numeric capture field.")
    return int(value)


def _verify_read_records(folder):
    rows = _text(folder / "DRIVE_A-badblocks.tsv").splitlines()
    _require(len(rows) == 93 and rows[0] == "offset\tis_bad\terrno", "Incomplete bad-block query coverage.")
    for index, row in enumerate(rows[1:]):
        columns = row.split("\t")
        _require(len(columns) == 3 and columns[0] == str(index * 131072) and columns[1] in ("0", "1") and columns[2] == "0",
                 "Bad-block query coverage or status differs.")
    rows = _text(folder / "read-status.tsv").splitlines()
    _require(len(rows) == 6257 and rows[0] == "component\toffset\trequested\treturned\terrno\tcorrected_bits\tecc_failures",
             "Incomplete partition read coverage.")
    offset = 1
    for component, count, step, amount in (("corrected-main", 184, 65536, 65536), ("raw-main", 184, 65536, 65536), ("raw-oob", 5888, 2048, 128)):
        for index in range(count):
            columns = rows[offset].split("\t"); offset += 1
            _require(len(columns) == 7 and columns[:5] == [component, str(index * step), str(amount), str(amount), "0"] and columns[6] == "0",
                     "A partition read is failed, short, duplicated, or out of order.")
            _uint(columns[5])


def verify_backup(folder, hook_hash):
    folder = Path(folder)
    result = ("PARTITION_CAPTURE_VERIFIED\nreason=all selected-partition components, statuses, lengths and hashes verified\n"
              "restorable_nand_backup=no\nfull_nand_backup=no\n"
              "Only the selected DRIVE_A partition was requested; no repair or internal write was attempted.\n"
              "A timed-out child may remain until reboot; its partial files may still change.\n")
    _require(_text(folder / "RESULT.txt", 8192) == result, "Partition capture did not finish successfully.")
    _require(read_regular(folder / "CAPTURE_FINISHED.txt", 1024) == b"Wrapper reached its final step; inspect RESULT.txt and per-command statuses.\n",
             "Partition capture final acknowledgement is missing.")
    _require(not read_regular(folder / "wrapper-errors.txt", 65536), "Partition capture wrapper reported an error.")
    for name in _BACKUP_STATUSES:
        _status(folder, name)
    try:
        for path in folder.iterdir():
            _require(not is_linked(path) and path.is_file() and not path.name.endswith(".partial") and "timeout" not in path.name.lower(),
                     "Capture contains linked, partial, or timeout evidence.")
    except OSError:
        raise RepairError("Cannot inspect saved partition capture.") from None
    _manifest(folder, "capture.sha256", _BACKUP_FILES, allow_paths=True)
    _require(read_regular(folder / "capture-hashes.txt", 8192) == read_regular(folder / "capture.sha256", 8192),
             "Saved partition hash records disagree.")
    for name, size in zip(_BACKUP_FILES[:3], (12058624, 12058624, 753664)):
        _require(len(read_regular(folder / name)) == size, "Partition artifact has the wrong length.")
    _verify_read_records(folder)
    summary = _text(folder / "helper-summary.txt", 8192)
    _require(summary.startswith("COMPLETE\n"), "Partition helper did not complete.")
    fields = _fields(summary.split("\n", 1)[1])
    expected = dict(component="complete", errno="0", corrected_main_bytes="12058624", raw_main_bytes="12058624",
                    raw_oob_bytes="753664", badblock_records="92", ecc_failures_before="0", ecc_failures_after="0",
                    restorable_nand_backup="no", full_nand_backup="no")
    _require(set(fields) == set(expected) | {"reason", "ecc_corrected_before", "ecc_corrected_after"} and
             all(fields[key] == value for key, value in expected.items()), "Partition helper summary differs from the reviewed geometry.")
    _require(_uint(fields["ecc_corrected_after"]) >= _uint(fields["ecc_corrected_before"]), "ECC counter chronology is inconsistent.")
    for side in ("before", "after"):
        ecc = _fields(_text(folder / ("helper-ecc-" + side + ".txt"), 8192))
        _require(set(ecc) == {"corrected", "failed", "badblocks", "bbtblocks"} and ecc["failed"] == "0",
                 "ECC record is incomplete or reports failures.")
        for value in ecc.values(): _uint(value)
        _require(ecc["corrected"] == fields["ecc_corrected_" + side], "ECC records and summary disagree.")
        geometry = _fields(_text(folder / ("sysfs-" + side + ".txt"), 8192))
        _require(set(geometry) == set(_GEOMETRY) | {"corrected_bits", "ecc_failures", "bad_blocks", "bbt_blocks"} and
                 all(geometry[key] == value for key, value in _GEOMETRY.items()) and geometry["ecc_failures"] == "0",
                 "Saved partition geometry or ECC state differs.")
        for key in ("corrected_bits", "ecc_failures", "bad_blocks", "bbt_blocks"): _uint(geometry[key])
        _require(bool(read_regular(folder / ("local-" + side + ".txt"), 2 * 1024 * 1024)), "Local metadata capture is empty.")
    provenance_text = _text(folder / "helper-provenance.txt", 8192)
    suffix = "Source helper remains in SD root; no duplicate binary is stored in this result directory.\n"
    _require(provenance_text.endswith(suffix), "Helper provenance is incomplete.")
    provenance = _fields(provenance_text[:-len(suffix)])
    helper_hash = ADVANCED_HASHES["nb-mtd-readonly"]
    expected = dict(source="/tmp/SD0/nb-mtd-readonly", source_sha256=helper_hash, ram_sha256=helper_hash,
                    wrapper_sha256=ADVANCED_HASHES["bt-nand-backup.sh"], autoexec_sha256=hook_hash)
    _require(set(provenance) == set(expected) | {"ram_executable"} and all(provenance[key] == value for key, value in expected.items()) and
             re.fullmatch(r"/tmp/nb-mtd-readonly-[1-9][0-9]*/nb-mtd-readonly", provenance["ram_executable"]) is not None,
             "Helper/source/hook provenance does not match this session.")
    for name, expected_hash in (("bt-nand-backup.sh.source", ADVANCED_HASHES["bt-nand-backup.sh"]),
                                ("autoexec.ash.source", hook_hash), ("nb-mtd-readonly.sha256.source", ADVANCED_HASHES["nb-mtd-readonly.sha256"]),
                                ("usb.console.used", ADVANCED_HASHES["usb.console"])):
        _require(digest(folder / name) == expected_hash, "Preserved staged source differs from the verified files.")


def _one(parent, name):
    nodes = parent.findall(name)
    _require(len(nodes) == 1, "Required Bluetooth XML structure is missing or ambiguous.")
    return nodes[0]


def _hex_value(text, count):
    text = (text or "").strip()
    pattern = r"[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){" + str(count - 1) + "}"
    _require(re.fullmatch(pattern, text) is not None and any(c not in "0:" for c in text),
             "Bluetooth identity or pairing key is absent or invalid.")


def _xml(folder, name):
    data = read_regular(folder / name, 1048576)
    _require(read_regular(folder / (name + ".status.txt"), 1024) == ("COPIED bytes=" + str(len(data)) + "\n").encode(),
             "Required Bluetooth XML was not fully copied.")
    _manifest(folder, name + ".sha256", {name}, allow_paths=True)
    _require(b"\x00" not in data and b"<!DOCTYPE" not in data.upper() and b"<!ENTITY" not in data.upper(),
             "Unsupported XML encoding or declarations.")
    try:
        document = ET.fromstring(data.decode("utf-8"))
    except (ET.ParseError, UnicodeError):
        raise RepairError("Saved Bluetooth XML is malformed.") from None
    _require(document.tag == "X_BROADCOM_COM_BluetoothAdapter", "Saved Bluetooth XML has an unsupported root.")
    return document


def verify_persistence(folder):
    folder = Path(folder)
    result = ("collection_exit_status=0\nRead-only observation; inspect context, per-file statuses and hashes.\n"
              "No pairing or persistence success is established by this marker.\nsync_exit_status=0\n")
    _require(_text(folder / "RESULT.txt", 8192) == result, "Persistence collection or sync did not succeed.")
    for name in ("collect", "sync-output"): _status(folder, name)
    context = _text(folder / "context.txt")
    for field in ("mount_context_status", "directory_listing_status"):
        _require(re.findall(r"^" + field + r"=(.*)$", context, re.M) == ["0"], "Persistence context collection failed.")
    targets = ("/tmp/FL0", "/pref")
    _a_mounts(context, targets)
    for target in targets:
        matches = []
        for line in context.splitlines():
            fields = line.split()
            if len(fields) >= 10 and fields[0].isdigit() and fields[4] == target:
                matches.append(fields)
        _require(len(matches) == 1, "Internal mountinfo is missing or ambiguous.")
        fields = matches[0]
        _require("-" in fields and fields[fields.index("-") + 1:fields.index("-") + 3] == ["ambafs", "a:"],
                 "Persistence files are not backed by internal AmbaFS.")
    config = _one(_xml(folder, "bt_config.xml"), "bt_config")
    _require((_one(config, "enable").text or "").strip() == "1", "Saved Bluetooth configuration is disabled.")
    _hex_value(_one(config, "bd_addr").text, 6)
    devices = _one(_xml(folder, "bt_devices.xml"), "bt_devices").findall("device")
    _require(bool(devices), "No saved paired device was observed.")
    for device in devices:
        _require(bool((_one(device, "device_name").text or "").strip()), "Saved paired device has no name.")
        _hex_value(_one(device, "bd_addr").text, 6)
        _require((_one(device, "Link_key_present").text or "").strip() == "1", "Saved paired device has no pairing key.")
        _hex_value(_one(device, "link_key").text, 16)
    for name in ("si_devices.xml", "bt.conf"):
        status_text = _text(folder / (name + ".status.txt"), 1024)
        if status_text == "MISSING (optional)\n":
            _require(not os.path.lexists(folder / name), "Optional-file absence conflicts with saved data.")
            continue
        data = read_regular(folder / name, 1048576)
        _require(status_text == "COPIED bytes=" + str(len(data)) + "\n", "Optional configuration copy failed.")
        _manifest(folder, name + ".sha256", {name}, allow_paths=True)
