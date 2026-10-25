#!/usr/bin/env python3
"""Build a public-only ZIP; never recursively archive the investigation workspace."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile
import zipfile

VERSION = "0.3.0"
PREFIX = f"Nextbase622GW-recovery-{VERSION}/"
PAYLOAD_FILES = ("autoexec.ash", "nb-bt-recover.sh", "usb.console")
ADVANCED_DIRECTORY = "advanced/internal-drive-a/"
ADVANCED_FILES = tuple(sorted((
    "usb.console", "backup.autoexec.ash", "bt-nand-backup.sh",
    "nb-mtd-readonly", "nb-mtd-readonly.sha256", "nb-mtd-readonly.c",
    "build-nb-mtd-readonly.sh", "dry-run.autoexec.ash",
    "format-a-once.autoexec.ash", "persistence.autoexec.ash",
    "bt-persistence-capture.sh",
)))
PREFLIGHT_DIRECTORY = "persistent-repair/payload/"
PREFLIGHT_FILES = ("preflight.autoexec.ash", "nb-a-preflight.sh")
PUBLIC_FILES = (
    ".gitattributes",
    ".gitignore",
    ".github/workflows/test.yml",
    "README.md",
    "Repair Bluetooth.command",
    "CLAUDE.md",
    "LICENSE",
    "docs/technical-notes.md",
    "docs/temporary-recovery.md",
    "docs/guided-repair.md",
    "docs/internal-storage-repair.md",
    *(ADVANCED_DIRECTORY + name for name in ADVANCED_FILES),
    "persistent-repair/repair.py",
    "persistent-repair/results.py",
    *(PREFLIGHT_DIRECTORY + name for name in PREFLIGHT_FILES),
    "recovery-kit/Recover Bluetooth.command",
    "recovery-kit/Recover Bluetooth.cmd",
    "recovery-kit/prepare-macos.sh",
    "recovery-kit/prepare-windows.ps1",
    *("recovery-kit/payload/" + name for name in PAYLOAD_FILES),
    "tests/test_macos_installer.py",
    "tests/test_payload.py",
    "tests/test_release.py",
    "tests/test_advanced_assets.py",
    "tests/test_capture_rtos.py",
    "tests/test_persistent_repair.py",
    "tests/test_persistent_results.py",
    "tests/test_persistent_preflight.py",
    "tests/test_windows_installer.ps1",
    "tools/build_release.py",
    "tools/capture_rtos.py",
)


def public_file(root: Path, name: str) -> Path:
    path = root / name
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError(f"Refusing symlink in public file path: {name}")
    if not path.is_file():
        raise FileNotFoundError(f"Missing public release file: {name}")
    return path


def file_manifest(root: Path, directory: str, names: tuple) -> bytes:
    lines = []
    for name in names:
        data = public_file(root, directory + name).read_bytes()
        lines.append(hashlib.sha256(data).hexdigest() + "  " + name + "\n")
    return "".join(lines).encode("ascii")


def payload_manifest(root: Path) -> bytes:
    return file_manifest(root, "recovery-kit/payload/", PAYLOAD_FILES)


def advanced_manifest(root: Path) -> bytes:
    return file_manifest(root, ADVANCED_DIRECTORY, ADVANCED_FILES)


def preflight_manifest(root: Path) -> bytes:
    return file_manifest(root, PREFLIGHT_DIRECTORY, PREFLIGHT_FILES)


def build(root: Path, output: Path) -> Path:
    root = root.resolve()
    entries = [(name, public_file(root, name).read_bytes()) for name in PUBLIC_FILES]
    captured = dict(entries)
    manifest = "".join(
        hashlib.sha256(captured["recovery-kit/payload/" + name]).hexdigest()
        + "  " + name + "\n" for name in PAYLOAD_FILES
    ).encode("ascii")
    entries.append(("recovery-kit/SHA256SUMS", manifest))
    advanced = "".join(
        hashlib.sha256(captured[ADVANCED_DIRECTORY + name]).hexdigest()
        + "  " + name + "\n" for name in ADVANCED_FILES
    ).encode("ascii")
    entries.append((ADVANCED_DIRECTORY + "SHA256SUMS", advanced))
    preflight = "".join(
        hashlib.sha256(captured[PREFLIGHT_DIRECTORY + name]).hexdigest()
        + "  " + name + "\n" for name in PREFLIGHT_FILES
    ).encode("ascii")
    entries.append((PREFLIGHT_DIRECTORY + "SHA256SUMS", preflight))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".zip", delete=False) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries:
                entry = zipfile.ZipInfo(PREFIX + name, date_time=(2026, 10, 25, 0, 0, 0))
                entry.create_system = 3
                mode = 0o100755 if name.endswith((".command", ".sh")) else 0o100644
                entry.external_attr = mode << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, data)
        os.replace(temporary, output)
        return output
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true", help="check the source payload manifest")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    expected = payload_manifest(root)
    if args.check:
        actual = (root / "recovery-kit/SHA256SUMS").read_bytes()
        if actual != expected:
            raise SystemExit("Payload manifest is stale; regenerate before release.")
        if (root / ADVANCED_DIRECTORY / "SHA256SUMS").read_bytes() != advanced_manifest(root):
            raise SystemExit("Advanced manifest is stale; regenerate before release.")
        if (root / PREFLIGHT_DIRECTORY / "SHA256SUMS").read_bytes() != preflight_manifest(root):
            raise SystemExit("Guided preflight manifest is stale; regenerate before release.")
        print("Temporary, advanced and guided preflight manifests verified.")
        return
    output = args.output or root / "dist" / f"Nextbase622GW-recovery-{VERSION}.zip"
    build(root, output)
    print(output)
    print("SHA256 " + hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
