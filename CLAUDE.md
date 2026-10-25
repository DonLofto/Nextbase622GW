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

The underlying vendor `format a:` repair succeeded once on one unit. Existing app pairing survived two subsequent full power-offs, including an ordinary boot after hooks/tokens were removed. The new **0.3.0 guided launcher and its preflight are fixture-tested only; they have not run end to end on a camera**. Original corruption cause, long-term NAND health, physically uncorrected RAW fidelity and a working NAND restore route remain unproven.

## Use the guided path on macOS

Help the owner extract and verify the release, then open root **`Repair Bluetooth.command`**. It requires **macOS, Python 3.9+, an interactive Terminal, a working card reader, a body USB data cable and steady power**. There is no guided Windows path or noninteractive consent option.

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

Sessions live privately under **`~/Nextbase622GW Repairs/<UUID>/`** and bind to the card's inert **`nb-a-repair.json`**. Keep both intact on the same Mac/card. A relaunch only offers inspection or **`DISARM`**, never continuation or re-arming. After a controlled shutdown and with the card in its reader, DISARM removes only verified unchanged owned controls. Claims, results, the inert marker and private evidence remain. Disarming is not success. Missing/mismatched journals or modified/unknown files need review rather than automatic adoption/deletion.

## Separate paths

- **Manual persistent repair:** use the [complete manual guide](docs/internal-storage-repair.md), its exact sequence and [frozen advanced manifest](advanced/internal-drive-a/SHA256SUMS). Native hooks do not identify the model/build themselves. Do useful preparation first and obtain informed approval for one destructive attempt before staging it. A capture has no proven restore route. Keep consumed NBFA02; never rearm it.
- **Temporary app access:** use the existing Mac/Windows launchers inside `recovery-kit/`, documented in [temporary recovery](docs/temporary-recovery.md). That unchanged component is version **0.2.0**, is lost on reboot and is separate from the persistent launcher. Its original RAM operation worked on hardware; the guarded distribution remains untested end to end on a camera.
- **Windows:** no guided persistent support is claimed. Native Windows passive capture for the manual path is not validated; do not invent a tested workflow.

## Maintenance and privacy

Read the actual [launcher](persistent-repair/repair.py), [evidence verifiers](persistent-repair/results.py) and manifests before changing behavior. Keep frozen advanced camera-tested bytes and their trusted test hashes unchanged. The new preflight has a separate manifest. A distribution version change does not imply changing temporary ownership text or its manifest.

Run appropriate repository checks after changes:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tools/build_release.py --check
```

The [temporary guide](docs/temporary-recovery.md#development-checks) documents Windows PowerShell fixtures. Fixture, pseudo-terminal and CI tests do not establish camera hardware behavior. Do not rerun hardware experiments merely because another assistant/session starts, and do not conflate the manual repair result with validation of the new wizard/preflight.

Use the explicit public release allowlist. Never recursively archive the investigation workspace. Exclude private logs, device information, populated XML, pairing keys, recordings, firmware/vendor binaries, NAND captures, session journals and backups from public commits/issues. Raw private research is not required to understand or execute the supported procedure; sanitized diagnosis, files and checks are already here.
