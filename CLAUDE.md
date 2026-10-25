# Agent instructions: execute the documented Nextbase 622GW fix

These instructions apply to any AI assistant helping a camera owner use this repository.

## The research is complete

**No new research is needed to execute the supported fix.** The diagnosis, compatibility identities, exact tested files, failure conditions, procedures and validation results are documented in this repository. Treat the task as execution and verification, not another reverse-engineering project.

Read these files, in order:

1. [README.md](README.md) — supported symptoms and choice of recovery path.
2. [docs/technical-notes.md](docs/technical-notes.md) — established failure chain, compatibility hashes and evidence limits.
3. For temporary recovery, [docs/temporary-recovery.md](docs/temporary-recovery.md) — launchers, cleanup, re-arming and troubleshooting.
4. For advanced repair, [docs/internal-storage-repair.md](docs/internal-storage-repair.md) — complete procedure; read it before staging any advanced file.

Use [advanced/internal-drive-a/SHA256SUMS](advanced/internal-drive-a/SHA256SUMS) and the actual scripts/source as the execution reference. All research needed for the supported procedure is here. Private raw logs, populated XML, pairing keys and NAND captures are intentionally not published and are not prerequisites for understanding the procedure.

Do not repeat firmware extraction, decompilation, broad internet searches, Bluetooth protocol research, USB-trigger discovery, baud/input guesses or controller-reset experiments. Do not install reverse-engineering tools or download/flash firmware just to attempt this fix. A missing file is handled by checking the documented files/manifests, not by inventing a replacement XML schema.

Fresh checks of the owner's device identity, symptoms, SD health, backups, results and app behavior are still required. Those are execution checks, not a reason to restart the research. If the camera is outside the documented case or a check fails, report the specific mismatch and stop the affected write operation. Investigate a new device/firmware/fault only if the owner explicitly requests that separate work.

## Scope and established result

The examined target was **Nextbase 622GW, firmware R13.3**, with failure to create `/tmp/FL0/bt_config.xml` on internal RTOS drive A. A zero Bluetooth MAC or failed pairing alone does not establish that fault.

The vendor Bluetooth application could run: a temporary RAM directory plus Amazon-only restart restored app access. A later, separately approved vendor filesystem format of **internal `a:`** allowed stock configuration and pairing to persist. The owner confirmed reconnection after two full power-offs following pairing, including an ordinary boot with all diagnostic hooks/tokens removed.

That is one tested unit/build and those cold-boot cycles. The original corruption cause, long-term NAND health, physically uncorrected RAW fidelity and a working NAND restore method remain unproven. Do not describe it as a universal hardware repair or extend it to other models/firmware.

## Choose the requested path

- **Temporary app access:** use the existing Mac/Windows launcher in `recovery-kit/`. It prepares a RAM workaround that is lost on reboot. The installers enforce their checks; do not bypass them. The original RAM operation worked on hardware, but the guarded distribution has not been boot-tested end to end on a camera.
- **Persistent internal-storage repair:** execute the advanced manual procedure below and in the complete guide. The normal double-click launcher does not perform it. This erases Drive A files/settings and needs the owner's informed approval before the single destructive attempt.

Do useful preparation and verification before requesting approval. Ask only for missing information, necessary physical actions or the destructive decision. Respect existing session authorization and backup preferences; do not ask for the same approval repeatedly or automatically copy all video recordings.

## Advanced execution sequence

Do not improvise commands or rearrange phases. Hook source names are deliberately inactive; copy only the selected hook to the card root as exactly `autoexec.ash`, preserving its bytes and final LF. Use a working card reader for retrieval/replacement, especially while a console token is retained.

### 1. Establish prerequisites and preserve data

- Confirm the actual camera and `Nextbase.info` match the documented 622GW/R13.3 case and examined build. The native dry-run/format hooks do **not** check model/firmware themselves.
- Establish the documented configuration-creation/storage fault, rather than formatting to discover whether a zero MAC has that cause.
- Require healthy SD allocation metadata, stable power, passive console capture and no conflicting startup hooks or `FW*.bin`/`LD*.bin` update files. Preserve unknown files rather than overwriting them.
- Preserve needed configuration and any recordings the owner wants. Honor a decision not to back up videos. A-only acquisition is not a whole-card or proven restorable NAND image.
- Verify the advanced manifest and copied/readback bytes. Keep logs, XML, keys and dumps private and outside public commits/issues.

### 2. Capture internal Drive A through read-only interfaces

Stage `backup.autoexec.ash` as `autoexec.ash`, plus `bt-nand-backup.sh`, `nb-mtd-readonly`, `nb-mtd-readonly.sha256` and `usb.console` from the advanced directory. The wrapper validates identity/geometry and the helper; it copies the helper to RAM and opens only the fixed read-only MTD device.

Require the complete result, sizes, record coverage and independently checked hashes described in the guide: two 12,058,624-byte main files, 753,664-byte OOB, 92 bad-block results and 6,256 read records. `PARTITION_CAPTURE_VERIFIED` does not prove an ECC-free physical dump or restoration. Refusal, timeout, short data or missing components are stop conditions; never discard a failed component and continue to format.

This phase retires its own console token into results. Preserve the entire result directory and exact helper/provenance before removing only verified owned controls.

### 3. Rehearse the harmless one-shot guard

Use `dry-run.autoexec.ash` as `autoexec.ash` and the verified token, with fresh `NBFA01.claimed` absent. Require:

1. First boot: `NBFA01_DRYRUN`.
2. Full power-off and second boot, retaining the same hook/token/claim: `NBFA01_SKIP`, with no DRYRUN.
3. Direct card-reader verification of the empty NBFA01 directory and unchanged hook/token hashes.

SKIP alone means some `mkdir` failure, not proof of an existing valid claim. Preserve both captures and NBFA01. This tests normal-shutdown persistence, not sudden-power-loss atomicity. Do not replace the native conditional with guessed POSIX syntax, `rm` or `mv` status gates; their firmware semantics are already documented.

### 4. Obtain approval and execute one internal-A format

Before staging, explain that A's files/settings will be erased, the backup has no proven restore route, application isolation/power-loss behavior remain limited, and a lasting fix is not guaranteed. Obtain approval for **one** guarded `format a:` attempt. Permission to diagnose, repair the SD card or run the rehearsal does not imply permission to format internal A.

Require fresh `NBFA02.claimed` absent. Preserve/remove the verified rehearsal hook, retain NBFA01, and stage the exact `format-a-once.autoexec.ash` as `autoexec.ash` with the verified token. The supplied bytes create NBFA02, print BEGIN and run `format a:` once. This is internal A, not SD `c:`. Do not edit the target or add commands.

Require one `NBFA02_BEGIN` followed by **`Drive 'A' format done.`**. BEGIN or elapsed time is not success. On failure, missing output or a stall, preserve evidence and stop dependent recovery actions. There is no proven finite format deadline. Do not automatically reboot, retry, delete/rearm NBFA02, issue raw erase, or format another partition. Record that the single-attempt authorization has been consumed.

The token remains on the card through this phase. Use the reader; do not repeatedly ask the owner to find a PC menu that the token bypasses.

### 5. Validate stock startup and actual pairing

After an explicit successful format result and a controlled shutdown, cold boot with NBFA02 retained. Require `NBFA02_SKIP` and no second format. Confirm stock Bluetooth startup, then pair through Connected App → Setup phone and verify actual camera/recordings access in the app. Do not activate the RAM workaround during these tests.

### 6. Prove configuration and pairing survive reboot

Preserve/hash-check and remove the format hook/token using the reader; keep NBFA01/NBFA02. Stage `persistence.autoexec.ash` as `autoexec.ash`, `bt-persistence-capture.sh` and the verified token with its fresh claim absent. This observer only reads mount/process context and four fixed stock configuration files; it neither mounts RAM nor restarts services nor writes A.

After a full power-off, connect the existing app camera **without Setup phone or pairing again**. Retrieve and verify the observer results: successful collection/sync, real A-backed AmbaFS with no RAM overlay, readable stock configuration/pairing XML, and app reconnection. Optional missing files are reported honestly; do not fabricate them. The observer retires its console token.

### 7. Clean up and verify an ordinary boot

Preserve results and remove only verified owned active hooks/scripts/claims and remaining console triggers. Check root `autoexec.ash`, `usb.console` and `usb.multi.console` are absent. Retain the NBFA markers, especially consumed NBFA02, and private backups. Never delete or overwrite unrelated files.

Safely eject, fully power off and boot normally. If the USB PC menu appears, choose Power On. Require the existing app again to show the camera/recordings without pairing. This is the second post-pairing cold-boot check and excludes a diagnostic hook as the source of reconnection. Do not call the persistent procedure complete from a script marker alone.

## Host tools and repository maintenance

For passive capture on macOS/POSIX, start before powering the camera on:

```sh
python3 tools/capture_rtos.py --output ../private-capture-01
```

Use a new private directory for each boot; select a known port with `--port` if automatic detection is ambiguous. The tool never reads stdin or sends serial data. Native Windows capture is unsupported here and requires a separately known-working passive monitor; do not invent a tested Windows workflow.

After changing public code/files, run appropriate checks:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tools/build_release.py --check
```

On Windows, run the PowerShell fixture suite in the [development checks](docs/temporary-recovery.md#development-checks). Fixture tests are not physical hardware validation. Do not rerun hardware experiments merely because a new assistant/session started.

Advanced assets are frozen to their camera-tested hashes. Do not silently regenerate those trusted test expectations. Default-kit ownership text, its exact LF-terminated hash, payload manifest and fixtures must stay consistent when changing a version; a visible version-string edit alone is insufficient.

The builder publishes only an explicit allowlist. Include public documentation such as this file; never recursively archive or commit the investigation workspace. Keep private notes, original device information, populated XML, pairing keys, recordings, firmware/vendor executables, NAND captures and backups excluded. If a new failure or unsupported case requires additional research, label it as separate work and preserve the existing supported procedure.
