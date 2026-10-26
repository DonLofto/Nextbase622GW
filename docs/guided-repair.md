# Guided Drive A repair

Release **0.6.0** provides **`Nextbase622GW-Repair.exe`** in the Windows ZIP and **`Repair Bluetooth.app`** in the Apple Silicon/Intel Mac ZIPs, in the extracted kit's root. Both use the same persistent-repair workflow, compatibility checks and typed format confirmation. The older launchers inside `recovery-kit/` perform temporary RAM recovery only.

**Formatting erases internal Drive A files/settings.** The underlying repair worked on one **Nextbase 622GW / R13.3**; pairing survived two full power-offs, including a boot without diagnostic hooks. The new host wizard and its compatibility preflight are fixture-tested, **not camera-tested end to end**. Other models/builds, long-term flash health and a working NAND restore method are unproven. A zero MAC alone is not a diagnosis.

## Before starting

You need:

- **Windows 10/11 x64:** Python is included. Open `Nextbase622GW-Repair.exe` and accept the administrator prompt for the read-only SD check and safe ejection; it does not approve formatting Drive A. Keep the EXE beside its `_internal` directory.
- **macOS 15+:** download the Apple Silicon (`arm64`) or Intel (`x86_64`) app for your Mac. Python is included; administrator access is not required. Choose Apple menu → About This Mac: “Chip” means Apple Silicon, “Processor: Intel” means Intel.
- A working **microSD reader**, the camera's card, and a USB **data** cable for the camera body's port. The mount's port is power only.
- Steady USB power, enough free space on the computer for private captures, and time to follow several shutdown/card-transfer/boot prompts without interrupting the camera.
- Any files, recordings or settings you want preserved already saved elsewhere. **The launcher does not copy video recordings.** Its Drive A capture is not a full NAND backup and has no proven restore route.

The Windows host uses built-in PowerShell and Win32 APIs. It checks an external FAT/exFAT card with status-only CHKDSK, locks/dismounts/ejects it, and captures a USB COM interface without sending commands. Existing baud and DTR/RTS settings are preserved; original serial settings are restored on exit. It remembers the USB interface identity across boots. Unsupported/locked readers, missing drivers or ambiguous ports stop the workflow. **Windows/camera USB behavior has not been physically validated.**

## Download, verify and open

Download the **Windows ZIP** or the **Mac ZIP for your chip**, plus `SHA256SUMS.txt`, from the [0.6.0 release](https://github.com/DonLofto/Nextbase622GW/releases/tag/v0.6.0). Verify the ZIP you downloaded.

On **Windows PowerShell**, from your download folder:

```powershell
$name = 'Nextbase622GW-Windows-0.6.0.zip'
$lines = @(Get-Content -LiteralPath .\SHA256SUMS.txt | Where-Object { $_.EndsWith("  $name") })
if ($lines.Count -ne 1) { throw 'Missing or duplicate checksum' }
$expected = ($lines[0] -split '  ', 2)[0]
if ((Get-FileHash -LiteralPath $name -Algorithm SHA256).Hash -ine $expected) { throw 'ZIP checksum mismatch' }
```

On **macOS Terminal**, from your download folder:

```sh
# For Intel, change arm64 to x86_64.
grep '  Nextbase622GW-Mac-arm64-0.6.0.zip$' SHA256SUMS.txt | shasum -a 256 -c -
```

Require `OK`; stop on any error or mismatch. Extract the **entire ZIP** onto the computer, outside the card, and keep its folders together. Windows users open **`Nextbase622GW-Repair.exe`**; no Python installation is required. The EXE is unsigned, so Windows may show a publisher warning. Only run a verified download from this repository's release.

Stop recording, fully power the camera off, and connect its card through the reader. Disconnect other compatible camera cards. On Windows, open **`Nextbase622GW-Repair.exe`** and accept the administrator prompt; on Mac, open **`Repair Bluetooth.app`**, which opens Terminal for the prompts. Follow the prompts. Do not copy the launcher or whole kit to the SD card. Extract outside junctions, symlinks or cloud placeholder folders, which the tool refuses.

### Opening the Mac app

The Mac app is ad-hoc signed for code integrity and **is not notarized or signed with Developer ID**. If macOS blocks it, verify the download first, try opening it, then follow **System Settings → Privacy & Security → Open Anyway** for this app and confirm. Do not disable Gatekeeper or run a command that removes quarantine. [Apple's opening instructions](https://support.apple.com/en-ie/102445).

No Python installation is needed. The repair runs without administrator privileges. Keep the entire `.app` together; you may move it to Applications. It opens Terminal so you can read the warnings and type the format confirmation. Closing the window stops the host; it cannot cancel a format already running in the camera.

For an explicitly identified card path, from Terminal in the extracted folder:

```sh
'Repair Bluetooth.app/Contents/MacOS/Launch' --volume /Volumes/NEXTBASE
```

On Windows, from an **administrator Command Prompt** in the extracted kit root:

```bat
Nextbase622GW-Repair.exe --volume E:\
```

Use your actual card path/letter. Do not guess a disk or serial device. The launcher keeps the computer awake while running; keep the cable and camera power connected as instructed.

If multiple serial interfaces are present, disconnect unrelated devices or pass an already identified interface with `--port PATH`. On Mac, list candidates without opening them using `'Repair Bluetooth.app/Contents/Resources/repair-engine' --passive-reader --list`.

On Windows, identify the camera's USB COM interface in Device Manager, then use `Nextbase622GW-Repair.exe --volume E:\ --port COM7` with its actual port. Do not guess COM numbers or baud rates. Close other serial monitors before starting. The USB console driver must expose a COM interface; this kit does not install drivers or change PowerShell policy permanently.

## What the prompts do

The tool verifies the kit and camera/card identity, refuses existing hooks/update files or previous claims, and checks the SD filesystem without repairing it. You must confirm the camera screen also says **622GW / R13.3**, that it is powered off during card handling, and that you have preserved what you need.

| Phase | What happens |
|---|---|
| **1. Prepare** | A read-only device preflight requires the exact runtime/vendor hashes, genuine A-backed storage and the documented configuration-creation failure. The frozen reader captures Drive A. The computer verifies lengths, read coverage, statuses, hashes and provenance. Two further cold boots must show `NBFA01_DRYRUN`, then `NBFA01_SKIP`, with the empty claim retained. The SD filesystem is checked again. |
| **2. Run once** | After the warnings, approve exactly one format by typing **`FORMAT DRIVE A ONCE`**. Approval is durably consumed before the unchanged native format hook is staged. The tool requires one `NBFA02_BEGIN` and the exact vendor result **`Drive 'A' format done.`**. |
| **3. Pair** | A stock cold boot must show `NBFA02_SKIP` and Bluetooth startup, with no second format. Stop recording, open **Connected App → Setup phone → OK**, pair using the Nextbase app, and confirm it shows the camera or recordings. |
| **4. Verify after reboot** | The format hook is removed and a read-only observer is staged. After a full power-off, reconnect the app using its **existing pairing**, without Setup phone. The computer checks saved configuration/pairing XML and genuine A-backed mounts, with no RAM overlay. |
| **5. Clean up** | Verified owned active hooks/scripts/tokens are removed; NBFA claims and results remain. After the final SD check and ejection, boot normally and confirm the existing app reconnects without pairing again. Choose **Power On** if the PC menu appears. |

For each diagnostic boot, the launcher ejects the card and waits for passive USB console output. Return it to the **powered-off** camera, connect the body USB data port to this computer, and power on. The diagnostic trigger may skip the PC menu. When prompted to retrieve results, stop recording, shut down normally, and return the card to the reader. Do not try to retrieve diagnostic results through the camera's PC menu.

Console markers alone do not prove app access. Answer app questions from what you actually see. The final success report requires both existing-pairing reconnections and removal of active controls. The tool neither flashes firmware nor guesses Bluetooth XML, repairs the SD filesystem, resets the controller or automatically retries a format.

## If it stops or is interrupted

Read the reported error and keep the private session folder. A failed/missing check or result stops progression; do not bypass it or start a fresh session to retry.

**Ctrl+C stops the launcher, not an operation already running inside the camera.** A format has no proven completion deadline. If approval was consumed and completion is unknown, keep camera power connected, preserve the evidence and seek review; do not unplug merely to retry, delete the claim or assume success.

For safe removal of staged controls after a controlled shutdown:

1. With the camera fully off, connect the **same card** through the reader and reopen the launcher on the **same computer and account** (administrator on Windows).
2. An existing session offers its status and private evidence path. Press Return to quit, or type **`DISARM`** and confirm card handling to remove only unchanged, verified owned controls.
3. The tool retains claims, results, the inert session marker and private evidence, then ejects the card. Disarming is **not** a repair-success verdict.

Relaunching never resumes, re-arms or starts another format, even if the first attempt was interrupted before staging. Modified/unowned files or a missing/mismatched journal require review; they are not automatically deleted or adopted. Do not remove markers or create a new journal to get around a refusal.

## Evidence and privacy

Each attempt stores a private UUID session under **`%USERPROFILE%\Nextbase622GW Repairs\`** on Windows or **`~/Nextbase622GW Repairs/`** on macOS, including `state.json`, identity, SD checks, console captures and retrieved preflight/Drive A/persistence results. The card's inert **`nb-a-repair.json`** binds it to that session. Keep both and use the same computer/account/card throughout; do not edit the journal or move/delete it during repair.

These captures can contain camera/phone identifiers, configuration and pairing keys. Keep them out of public commits and issues. For support, share only sanitized model, firmware, tool version, error and session phase. The launcher never copies video recordings.

The session binds the model/firmware and unique camera/card serial fields. Changing battery, used-space, clock or Bluetooth-status fields in `Nextbase.info` do not invalidate that identity; missing or duplicated serial fields do.

[Research, compatibility hashes and evidence limits](technical-notes.md) · [Full manual procedure](internal-storage-repair.md) · [Agent instructions](../CLAUDE.md)

## Building the Windows download

End users download the Windows ZIP; the following is for maintainers. On **64-bit Windows with Python 3.12**, from a clean checkout:

```powershell
python -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install --require-hashes -r tools/windows-build-requirements.txt
.\.venv-build\Scripts\python.exe tools/build_windows.py
```

The output is `dist/Nextbase622GW-Windows-0.6.0.zip` with the EXE, bundled runtime, repair resources, README, CLAUDE and source. `dist/windows-build.json` records the source commit in CI and runtime hashes. Python's redistribution license and the project license are included under `_internal/licenses/`.

[Native Windows CI](../.github/workflows/test.yml) extracts the ZIP, copies only the EXE and `_internal` into an isolated directory, and runs it with no Python on `PATH`. It verifies packaged assets, rejects tampered assets and noninteractive/automatic consent, and checks the console/admin manifest. The full shared consent/workflow tests run separately. These tests do not exercise camera hardware or the interactive UAC desktop prompt.

The portable directory layout follows [PyInstaller's warning against elevated single-file extraction](https://pyinstaller.org/en/stable/operating-mode.html). There is no installer, self-update service or new camera payload. The source-only `Repair Bluetooth.cmd` remains usable with Python 3.9+ as administrator. Build requirements are pinned with PyPI wheel hashes; they are not user requirements.

## Building the Mac apps

End users download an app ZIP; Python is included. Maintainers build natively on **macOS with Python 3.12**, once per architecture:

```sh
python3.12 -m venv .venv-build
.venv-build/bin/python -m pip install --require-hashes -r tools/macos-build-requirements.txt
.venv-build/bin/python tools/build_macos.py
```

Outputs are `dist/Nextbase622GW-Mac-arm64-0.6.0.zip` or `dist/Nextbase622GW-Mac-x86_64-0.6.0.zip`, plus a build report with source commit/engine hashes in CI. The app embeds a non-elevated PyInstaller engine with Python, the unchanged camera resources, passive reader and redistribution licenses. Its Finder launcher opens the bundled command in Terminal through Launch Services; it does not require Automation permission. The app is ad-hoc signed, not notarized. No signing account or private certificate is embedded.

CI builds on macOS 15 for both chips, extracts with `ditto`, moves the app into a path containing spaces/apostrophes, and runs with no Python on PATH. Tests check resources, signatures/executable permissions, noninteractive/automatic-consent refusal, and the bundled passive reader through a real pseudoterminal, including no transmission and terminal-setting restoration. A pseudoterminal is not a camera. Hardware repair and Gatekeeper approval on a downloaded/quarantined app remain separate from these checks.

The source-only ZIP still includes `Repair Bluetooth.command` and `Repair Bluetooth.cmd` for Python 3.9+ users. No camera payload or destructive consent rule changes with packaging. Extract the Mac ZIP using Finder/Archive Utility or `ditto -x -k` to preserve executable permissions and signing metadata.
