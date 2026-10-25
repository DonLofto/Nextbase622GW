#!/usr/bin/env python3
"""Build the portable Windows ZIP on Windows, with a bundled Python runtime."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import zipfile
from build_release import (ADVANCED_DIRECTORY, ADVANCED_FILES, PREFLIGHT_DIRECTORY,
                           PREFLIGHT_FILES, PREFIX, VERSION, build, public_file)


def main():
    if sys.platform != "win32" or sys.maxsize <= 2**32:
        raise SystemExit("Build on 64-bit Windows with Python 3.12 and the pinned build requirements.")
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("The release build requires Python 3.12.")
    root = Path(__file__).resolve().parents[1]
    output = root / "dist" / f"Nextbase622GW-Windows-{VERSION}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        work = Path(directory)
        # Keep the runtime beside the EXE: elevated onefile extraction is discouraged upstream.
        command = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--onedir",
                   "--console", "--uac-admin", "--noupx", "--name", "Nextbase622GW-Repair",
                   "--distpath", str(work / "dist"), "--workpath", str(work / "build"),
                   "--specpath", str(work), "--paths", str(root / "persistent-repair")]
        resources = [(ADVANCED_DIRECTORY + name, ADVANCED_DIRECTORY) for name in (*ADVANCED_FILES, "SHA256SUMS")]
        resources += [(PREFLIGHT_DIRECTORY + name, PREFLIGHT_DIRECTORY) for name in (*PREFLIGHT_FILES, "SHA256SUMS")]
        resources += [("persistent-repair/windows-volume.ps1", "."), ("LICENSE", "licenses")]
        for name, destination in resources:
            command.extend(["--add-data", str(public_file(root, name)) + ":" + destination])
        python_license = Path(sys.base_prefix) / "LICENSE.txt"
        if not python_license.is_file():
            raise SystemExit("Python redistribution license is missing.")
        licenses = work / "licenses"
        licenses.mkdir()
        (licenses / "Python.txt").write_bytes(python_license.read_bytes())
        command.extend(["--add-data", str(licenses / "Python.txt") + ":licenses"])
        command.append(str(root / "persistent-repair/windows_entry.py"))
        subprocess.run(command, cwd=work, check=True)
        bundle = work / "dist/Nextbase622GW-Repair"
        candidate = work / "windows.zip"
        build(root, candidate)
        files = {}
        with zipfile.ZipFile(candidate, "a", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(bundle.rglob("*")):
                if path.is_dir():
                    if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
                        raise ValueError("Linked build directory refused.")
                    continue
                name = path.relative_to(bundle).as_posix()
                data = public_file(bundle, name).read_bytes()
                files[name] = hashlib.sha256(data).hexdigest()
                archive.writestr(PREFIX + name, data)
        os.replace(candidate, output)
        report = {"version": VERSION, "commit": os.environ.get("GITHUB_SHA"),
                  "python": platform.python_version(), "pyinstaller": importlib.metadata.version("pyinstaller"),
                  "asset": output.name, "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "runtime_files": files}
        (output.parent / "windows-build.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
