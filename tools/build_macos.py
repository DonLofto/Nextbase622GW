#!/usr/bin/env python3
"""Build a standalone Mac app; the Finder launcher opens its bundled console in Terminal."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from build_release import (ADVANCED_DIRECTORY, ADVANCED_FILES, PREFLIGHT_DIRECTORY,
                           PREFLIGHT_FILES, PREFIX, VERSION, build, public_file)


def main():
    architecture = platform.machine()
    if sys.platform != "darwin" or architecture not in ("arm64", "x86_64") or sys.version_info[:2] != (3, 12):
        raise SystemExit("Build natively on macOS with Python 3.12 and the pinned Mac build requirements.")
    root = Path(__file__).resolve().parents[1]
    output = root / "dist" / f"Nextbase622GW-Mac-{architecture}-{VERSION}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        work = Path(directory)
        command = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--onefile", "--console",
                   "--noupx", "--name", "repair-engine", "--target-arch", architecture,
                   "--distpath", str(work / "engine"), "--workpath", str(work / "build"), "--specpath", str(work),
                   "--paths", str(root / "persistent-repair"), "--paths", str(root / "tools")]
        resources = [(ADVANCED_DIRECTORY + name, ADVANCED_DIRECTORY) for name in (*ADVANCED_FILES, "SHA256SUMS")]
        resources += [(PREFLIGHT_DIRECTORY + name, PREFLIGHT_DIRECTORY) for name in (*PREFLIGHT_FILES, "SHA256SUMS")]
        resources += [("persistent-repair/windows-volume.ps1", "."), ("LICENSE", "licenses"),
                      ("tools/Python-LICENSE.txt", "licenses")]
        for name, destination in resources:
            command.extend(["--add-data", str(public_file(root, name)) + ":" + destination])
        command.append(str(root / "persistent-repair/mac_entry.py"))
        subprocess.run(command, cwd=work, check=True)
        app = work / "Repair Bluetooth.app"
        contents = app / "Contents"
        executable = contents / "MacOS/Launch"
        executable.parent.mkdir(parents=True)
        files = contents / "Resources"
        files.mkdir()
        shutil.copy2(work / "engine/repair-engine", files / "repair-engine")
        for name in ("README.md", "CLAUDE.md", "LICENSE"):
            shutil.copy2(public_file(root, name), files / name)
        (contents / "Info.plist").write_bytes(plistlib.dumps({
            "CFBundleExecutable": "Launch", "CFBundleIdentifier": "org.nextbase622gw.repair",
            "CFBundleName": "Repair Bluetooth", "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": VERSION, "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "15.0", "LSUIElement": True,
        }))
        executable.write_text('''#!/bin/bash
set -eu
CONTENTS=$(cd -P "$(/usr/bin/dirname "$0")/.." && pwd)
if [ "$#" -gt 0 ]; then
    exec /usr/bin/caffeinate -i "$CONTENTS/Resources/repair-engine" "$@"
fi
exec /usr/bin/open -a Terminal "$CONTENTS/Resources/Repair Bluetooth.command"
''', encoding="utf-8")
        terminal = files / "Repair Bluetooth.command"
        terminal.write_text('''#!/bin/bash
set -eu
RESOURCES=$(cd -P "$(/usr/bin/dirname "$0")" && pwd)
exec /usr/bin/caffeinate -i "$RESOURCES/repair-engine" "$@"
''', encoding="utf-8")
        executable.chmod(0o755)
        terminal.chmod(0o755)
        subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(app)], check=True)
        subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)], check=True)
        app_archive = work / "app.zip"
        subprocess.run(["/usr/bin/ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(app_archive)], check=True)
        candidate = work / "mac.zip"
        build(root, candidate)
        entries = {}
        with zipfile.ZipFile(candidate, "a") as archive, zipfile.ZipFile(app_archive) as packed:
            for info in packed.infolist():
                data = packed.read(info.filename)
                entries[info.filename] = hashlib.sha256(data).hexdigest()
                info.filename = PREFIX + info.filename
                archive.writestr(info, data)
        os.replace(candidate, output)
        report = {"version": VERSION, "commit": os.environ.get("GITHUB_SHA"), "architecture": architecture,
                  "python": platform.python_version(), "pyinstaller": importlib.metadata.version("pyinstaller"),
                  "asset": output.name, "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "app_entries": entries}
        (output.parent / f"mac-{architecture}-build.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
