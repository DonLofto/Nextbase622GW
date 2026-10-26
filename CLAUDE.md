# Agent instructions: execute the documented Nextbase 622GW fix

These instructions apply to assistants helping camera owners use this repository.

## The research is complete

**No new research is needed to execute the supported fix.** Use the documented procedure, exact files and validation checks. Do not repeat firmware extraction, decompilation, broad internet searches, USB-trigger discovery, Bluetooth protocol research or controller-reset experiments. Do not download/flash firmware or invent replacement configuration XML.

Read:

1. [README.md](README.md) — supported problem, destructive warning and entry point.
2. [Guided repair](docs/guided-repair.md) — requirements, prompts, private evidence and interruption handling.
3. [Technical notes](docs/technical-notes.md) — established fault, compatibility identities and evidence limits.
4. [Manual procedure](docs/internal-storage-repair.md) — exact native phases and advanced asset reference; required before manual staging.

The supported case is **622GW / R13.3** with failure to create `/tmp/FL0/bt_config.xml` on internal RTOS Drive A. A zero MAC or failed pairing alone is insufficient. Fresh device identity, fault, SD health, preservation and app checks are execution requirements, not reasons to restart research. A mismatch stops the affected write operation. Investigate another device/build/fault only when explicitly requested as separate work.

The underlying vendor `format a:` repair succeeded once on one unit. Existing app pairing survived two subsequent full power-offs, including an ordinary boot after hooks/tokens were removed. The **0.6.0 Windows/macOS guided launchers are host/fixture-tested, not camera-tested end to end**. Windows/camera USB behavior is also unvalidated. Original corruption cause, long-term NAND health, physically uncorrected RAW fidelity and a working NAND restore route remain unproven.

## Use the guided path

Help the owner verify and fully extract the correct release ZIP. On Windows 10/11 x64, open **`Nextbase622GW-Repair.exe`** in the Windows kit and accept the administrator prompt. Python is bundled; keep the EXE beside its `_internal` directory. On macOS 15+, choose the Apple Silicon (`arm64`) or Intel (`x86_64`) Mac ZIP, extract it and open **`Repair Bluetooth.app`**. It opens Terminal and includes Python; the whole app can be moved together. Both require **an interactive console, a working card reader, a body USB data cable and steady power**. There is no noninteractive consent option. Windows administrator access enables the read-only card check/ejection, not format approval.

The launcher already handles staging/readback, ejection, passive capture, evidence verification and this sequence:

1. Exact build/fault preflight followed by the frozen read-only Drive A capture; verify complete results.
2. Harmless first-boot `NBFA01_DRYRUN`, then full-power-off `NBFA01_SKIP`; verify the retained empty claim and SD health.
3. Explicit typed **`FORMAT DRIVE A ONCE`**. The private journal consumes this authorization durably **before** format staging. Require one `NBFA02_BEGIN` and exact **`Drive 'A' format done.`**.
4. Stock cold boot with `NBFA02_SKIP` and Bluetooth startup; owner pairs and verifies actual camera/recordings access.
5. Remove format controls, stage the read-only observer, cold boot and reconnect using the existing pairing. Verify genuine A-backed AmbaFS and valid saved Bluetooth configuration/pairing XML; no RAM overlay.
6. Remove all verified owned active hooks/tokens, retain claims/results, check SD health and perform an ordinary cold boot. Require another app reconnection without pairing.

Do not manually stage another hook while the launcher owns the session, reorder phases, pre-answer app checks or bypass its destructive confirmation. Ask only for necessary physical actions, missing information or the destructive decision; respect existing authorization and preservation preferences. **The launcher does not copy videos.** Help owners preserve only what they want before starting.

## Stop and interruption rules

A refusal, incomplete capture, changed identity/control, unhealthy SD card, wrong marker or failed/missing result stops progression. Never patch out a guard, delete a claim, create a new session or format again to overcome a refusal.

**Ctrl+C stops the host launcher only.** It cannot cancel an in-camera format. There is no proven finite format deadline. If authorization was consumed and completion is unknown, keep camera power connected, preserve evidence and stop dependent actions; do not automatically reboot, retry or assume completion.

Sessions live privately under **`~/Nextbase622GW Repairs/<UUID>/`** (Windows: `%USERPROFILE%\Nextbase622GW Repairs\<UUID>\`) and bind to the card's inert **`nb-a-repair.json`**. Keep both intact on the same computer/account/card. A relaunch only offers inspection or **`DISARM`**, never continuation or re-arming. After a controlled shutdown and with the card in its reader, DISARM removes only verified unchanged owned controls. Claims, results, the inert marker and private evidence remain. Disarming is not success. Missing/mismatched journals or modified/unknown files need review rather than automatic adoption/deletion.

## Separate paths

- **Manual persistent repair:** use the [complete manual guide](docs/internal-storage-repair.md), its exact sequence and [frozen advanced manifest](advanced/internal-drive-a/SHA256SUMS). Native hooks do not identify the model/build themselves. Do useful preparation first and obtain informed approval for one destructive attempt before staging it. A capture has no proven restore route. Keep consumed NBFA02; never rearm it.
- **Temporary app access:** use the existing Mac/Windows launchers inside `recovery-kit/`, documented in [temporary recovery](docs/temporary-recovery.md). That unchanged component is version **0.2.0**, is lost on reboot and is separate from the persistent launcher. Its original RAM operation worked on hardware; the guarded distribution remains untested end to end on a camera.
- **Windows:** the guided path uses the same state machine and camera files, with a Windows-only host backend for metadata, status-only CHKDSK, safe ejection, write-through moves and passive USB COM capture. It preserves existing baud/DTR/RTS and restores serial settings. Ambiguous ports, wrong USB instances, internal/system disks, junctions/reparse points or failed checks stop it. Native host CI is not evidence of physical Windows/camera success. Do not bypass a refusal or guess COM/baud values.

## Maintenance and privacy

Read the actual [launcher](persistent-repair/repair.py), [Windows host](persistent-repair/windows_host.py), [evidence verifiers](persistent-repair/results.py) and manifests before changing behavior. Keep frozen advanced camera-tested bytes and their trusted test hashes unchanged. The preflight has a separate manifest. A distribution version change does not imply changing temporary ownership text or its manifest. Respect the owner's instruction not to use subagents.

Run appropriate repository checks after changes:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tools/build_release.py --check
```

The [temporary guide](docs/temporary-recovery.md#development-checks) documents Windows PowerShell fixtures. Fixture, pseudo-terminal and CI tests do not establish camera hardware behavior. Do not rerun hardware experiments merely because another assistant/session starts, and do not conflate the manual repair result with validation of the new wizard/preflight.

The Windows EXE is a portable directory build of the same Python workflow, not a separate repair implementation. The source-only `.cmd` and `.command` remain available for developers with Python. The Mac app uses its bundled engine for passive capture too; never change frozen `sys.executable` back into a Python-script invocation. The `--passive-reader` engine subcommand only captures RX and never dispatches the repair wizard. Use the [Windows packaging instructions](docs/guided-repair.md#building-the-windows-download) and [Mac packaging instructions](docs/guided-repair.md#building-the-mac-apps); never redistribute a lone EXE without `_internal`. The Mac apps are ad-hoc signed and not notarized; do not disable Gatekeeper or remove quarantine automatically.

Use the explicit public release allowlist. Never recursively archive the investigation workspace. Exclude private logs, device information, populated XML, pairing keys, recordings, firmware/vendor binaries, NAND captures, session journals and backups from public commits/issues. Raw private research is not required to understand or execute the supported procedure; sanitized diagnosis, files and checks are already here.
