# Advanced: internal Drive A repair

**This manual procedure destroys the existing files/settings on internal Drive A.** It is separate from the temporary double-click recovery. It was performed once on one Nextbase **622GW / R13.3** with the specific configuration-creation fault described below. Stock Bluetooth and retained app pairing worked afterward, including after all active hooks/tokens were removed. This does not guarantee the same outcome on another camera or establish long-term NAND health.

Release **0.2.0** includes [inactive advanced assets](../advanced/internal-drive-a/). None of their hook filenames is `autoexec.ash`: a hook becomes active only when deliberately copied to the card root and renamed. The ordinary Mac/Windows launchers never select this operation. Read this entire guide before copying a hook.

## Mandatory prerequisites and stop conditions

- Read the camera's root `Nextbase.info` and camera information screen. Require exactly model **622GW**, firmware **R13.3**, and the examined runtime/build described in [technical notes](technical-notes.md#compatibility-identities). Stop for missing, duplicate, different or ambiguous identity. **The native RTOS dry-run/format files do not check model or firmware themselves.** These manual checks are mandatory even if another script previously accepted the card.
- Establish the same fault: stock startup cannot create its default `/tmp/FL0/bt_config.xml`, configuration initialization aborts, and internal A has the corresponding filesystem problem. Missing XML or a zero Bluetooth MAC alone is insufficient. If the fault differs or the diagnostic evidence is unavailable, stop; do not try formatting as a discovery test.
- Have a **working card reader** and direct access to the card. Verify it now. All retrieval/replacement below uses the reader, because a retained USB console token can bypass the usual PC Connection menu.
- Preserve needed recordings, readable configuration, existing hooks and other card files on another device, with checked sizes/hashes. The partition capture below is additional evidence, not a substitute for file backups or a tested restore method. Stop if losing any remaining A files/settings is unacceptable.
- Check the SD filesystem with the host's non-repairing verification mode. Require a clean result before staging and again before the destructive phase. If it reports corruption, stop, preserve the files first, and resolve the SD problem separately or use another verified card. Do not rely on a successful file copy alone. Neither the advanced assets nor this guide's format command repair the SD filesystem.
- Use stable power and a sound data cable connected to the **camera body's** USB port. Keep the computer awake. Stop recording before shutdown/card handling and before the attempt where controls permit. The hook's delay is **not** an application-quiescence mechanism: the tested operation did not prove all firmware clients were stopped or isolated.
- Be able to save **passive USB serial console output** from the diagnostic boot. Interactive console input was not demonstrated. Required markers and the vendor result must be observed; elapsed time or a new directory alone is insufficient.
- Resolve existing startup/console hooks before proceeding. Never overwrite unknown files. Remove an older temporary kit with its matching removal tool. Root `FW*.bin` / `LD*.bin`, another `autoexec.ash`, `usb.multi.console`, or an unrelated recovery hook must not be present. Preserve unknown claims/results for investigation.

There is no automatic retry, raw-erase fallback, factory reset or firmware installation in this procedure. Stop after any refusal, incomplete backup, failed/missing marker, syntax error, unhealthy card or failed/missing format result. Keep a consumed format claim; deleting it would rearm the destructive operation.

With the powered-off camera's card in the reader, a macOS read-only check is `diskutil verifyVolume /Volumes/CARD`, substituting the card's verified mounted volume. On Windows, use `chkdsk E:` with the correct card letter and **no repair switches**, from an elevated Command Prompt; Microsoft documents this form as reporting status without fixing errors. Close applications using the card and require a completed clean check; do not accept an inconclusive/in-use check. Do not add `/f`, `/r`, `/x`, cleanup switches or schedule a repair as part of this procedure. SD repair, if necessary, is a separate decision after preservation. [Microsoft chkdsk reference](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/chkdsk).

## Prepare passive console capture

From the extracted release root on macOS/POSIX, start the supplied [passive reader](../tools/capture_rtos.py) **before powering on the camera**:

```sh
python3 tools/capture_rtos.py --output ../private-rtos-backup
```

The reader uses Python 3's standard library; verify that Python 3 is available before staging. Use a different, nonexistent private output directory for every boot. On macOS it waits up to 600 seconds for a unique `/dev/cu.usbmodem*` interface, saves raw `serial-rx.bin`, decoded `serial-rx.txt` and `serial-settings.txt`, and displays received output. Use `python3 tools/capture_rtos.py --list` to list those candidates without opening them. If automatic selection is ambiguous, or using another POSIX host, select the already identified interface with `--port PATH`; do not guess a device. The camera route was tested on macOS. Stop the reader with Ctrl+C after the required result has been saved. It sends no commands or user input to the camera, and closing it does not power the camera off. Do not open the same port in two readers or change baud/input settings as an attempted fix.

This project's capture reader does **not support native Windows**. Advanced Windows use requires a separately known-working passive serial monitor and equivalent complete saved logs; that workflow has not been validated here. If you cannot reliably record the required markers, stop. The default Windows temporary-recovery launcher is separate and unchanged.

## Verify the assets and understand the phases

Work from an extracted `Nextbase622GW-recovery-0.2.0.zip`, outside the card. In `advanced/internal-drive-a`, verify **every** line of `SHA256SUMS` before use. On macOS:

```sh
shasum -a 256 -c SHA256SUMS
```

In Windows PowerShell, from that same directory:

```powershell
Get-Content -LiteralPath .\SHA256SUMS | ForEach-Object {
    $expected, $name = $_ -split '  ', 2
    if ((Get-FileHash -LiteralPath $name -Algorithm SHA256).Hash -ine $expected) {
        throw "Hash mismatch: $name"
    }
}
```

The helper's adjacent `nb-mtd-readonly.sha256` must also match its executable. The supplied ARM helper was executed on the examined camera; its source/build script is included for inspection. Rebuilding requires a matching toolchain and separate validation; a different executable is not covered by that result.

| Phase | Source hook to copy/rename to root `autoexec.ash` | Other root files | USB token behavior |
|---|---|---|---|
| Read-only partition capture | `backup.autoexec.ash` | `bt-nand-backup.sh`, `nb-mtd-readonly`, `nb-mtd-readonly.sha256`, `usb.console` | Capture retires its token into results |
| Harmless two-boot rehearsal | `dry-run.autoexec.ash` | `usb.console` | Retained through both boots |
| One destructive attempt | `format-a-once.autoexec.ash` | `usb.console` | Retained; does not remove itself |
| Read-only persistence capture | `persistence.autoexec.ash` | `bt-persistence-capture.sh`, `usb.console` | Capture retires its token into results |

For **each** change: power the camera off, use the reader, preserve/hash-check the previous owned hook before removal, copy only the files for the next phase, and rename only the chosen hook to exactly `autoexec.ash`. Show filename extensions; do not create `autoexec.ash.txt` or edit the hook in a text editor. Preserve its ASCII/LF bytes. Read back the card's copied files and compare their SHA256 values with the source manifest, using the source hook's manifest entry for the renamed `autoexec.ash`. Safely eject the reader before returning the card to the powered-off camera.

Start the passive reader **before powering on**; it waits for the interface. Connect the camera body to the computer with a USB data cable and power on. The token can suppress the normal PC menu. **Always retrieve through the card reader after a safe shutdown; do not depend on a PC menu appearing.** Keep every capture private.

## 1. Preserve Drive A before changing it

Stage the partition-capture phase from the table. Require a fresh `bt-nand-backup.claimed` name; if it or earlier result folders already exist, preserve them and establish their history before changing anything. Do not delete a claim merely to force another capture.

The wrapper validates model/runtime, exact DRIVE_A geometry, read-only MTD selection and the helper hash, then executes a verified helper copy in RAM. The helper requests corrected main, requested-RAW main/OOB, bad-block information and ECC counters. It never opens NAND writable. The helper read has a 120-second polling budget; metadata/hashing have separate budgets. SD operations or a kernel-blocked child can still stall, so a timer alone is not a completion check.

Wait for the wrapper's final console message, then shut down safely and retrieve the **entire** fresh `bt-nand-backup-N` directory, the root helper and its manifest through the reader. Preserve all partial/error files too. Independently verify each copied file's size/hash against the card; verify `capture.sha256`. Proceed only if all of these agree:

- `RESULT.txt`: `PARTITION_CAPTURE_VERIFIED`; helper exit zero, summary `COMPLETE`, all metadata/hash/sync statuses zero, no timeout.
- `DRIVE_A-corrected-main.bin`: **12,058,624 bytes**.
- `DRIVE_A-raw-main.bin`: **12,058,624 bytes**; the filename means requested RAW mode.
- `DRIVE_A-raw-oob.bin`: **753,664 bytes**.
- `DRIVE_A-badblocks.tsv`: exact header plus **92** successful query records, with no block silently skipped.
- `read-status.tsv`: exact header plus **6,256** successful full-length records: 184 corrected-main, 184 requested-RAW main and 5,888 OOB. Require no failed ECC/query/read status.
- The eight artifact hashes verify, source/RAM helper hashes match, and before/after kernel/sysfs/ECC files are present.

The saved `capture.sha256` contains camera-side absolute paths. On the computer, compare its digest values **by basename** with fresh hashes of the retrieved eight files; do not expect those camera paths to exist on the host or rewrite the original manifest. From the retrieved result directory on macOS:

```sh
shasum -a 256 DRIVE_A-corrected-main.bin DRIVE_A-raw-main.bin DRIVE_A-raw-oob.bin \
  DRIVE_A-badblocks.tsv read-status.tsv helper-summary.txt helper-ecc-before.txt helper-ecc-after.txt
```

On Windows, use `Get-FileHash -Algorithm SHA256 -LiteralPath` with those same eight filenames and compare the hash values. Also compare your copied metadata/status files with fresh reader-side hashes before relying on them. Any mismatch is a stop condition.

**A complete capture is still not a restorable NAND backup.** The successful unit showed ECC activity during requested RAW reads, so uncorrected physical fidelity remains unproven. NAND outside DRIVE_A, shared BBT/tail/gaps and possible translation metadata elsewhere are absent. No validated writeback/restore route exists. An incomplete/refused capture is a stop condition, not permission to discard the missing component and continue.

## 2. Rehearse the native one-shot guard over two cold boots

Remove only the verified backup hook; keep its results and claim. Stage `dry-run.autoexec.ash` as `autoexec.ash` and the original verified `usb.console`. `NBFA01.claimed` must be absent before the first rehearsal; if already present, stop and investigate its provenance.

The unedited hook contains one native RTOS compound line, preceded by a 20,000-millisecond delay:

```text
sleep 20000
if mkdir c:\NBFA01.claimed; then echo NBFA01_DRYRUN; else echo NBFA01_SKIP; fi
```

1. First boot: require `NBFA01_DRYRUN`, with no syntax/storage error. It creates an SD directory and makes no internal A change.
2. Shut down normally, fully power off, and cold boot with the **same hook, token and claim retained**. Require `NBFA01_SKIP` and no new `NBFA01_DRYRUN`.
3. Use the reader to verify that `NBFA01.claimed` exists as an empty directory, the hook/token still match their expected hashes, and `NBFA02.claimed` is absent. Preserve both logs. `SKIP` alone is insufficient: any mkdir failure can select that branch.

Keep NBFA01. The rehearsal demonstrates normal-shutdown claim persistence and branch behavior on this card/firmware; it does not prove exactly-once execution after sudden power loss or SD corruption. Recheck the SD filesystem. Stop if any acceptance condition is missing.

## 3. Explicitly choose one destructive Drive A format

Continue only after consciously accepting loss of A's files/settings and the unproven restore, power-loss and application-isolation limits. Review the exact hook again. The vendor operation targets **internal `a:`**, not SD `c:`. It replaces filesystem metadata and can program/erase-replace NAND blocks through the FTL; it is not a harmless configuration reset.

With the camera off and card in the reader, preserve/remove the verified dry-run hook. **Retain NBFA01. Require NBFA02 absent.** Copy the unmodified `format-a-once.autoexec.ash` as `autoexec.ash`, plus the verified token, and read back both hashes. The supplied file is exactly:

```text
sleep 20000
if mkdir c:\NBFA02.claimed; then echo NBFA02_BEGIN; format a:; else echo NBFA02_SKIP; fi
```

Safely eject and boot with stable power and passive console recording. Require **one** `NBFA02_BEGIN` followed by the vendor **`Drive 'A' format done.`**. BEGIN alone is not success. On `format failed`, a missing result, a stall or any unexpected output, preserve evidence and stop; do not delete NBFA02, retry, add commands or fall back to raw erase. There is no proven finite format deadline. Do not interrupt power merely because a marker appeared.

The tested format returned success once. Its normal write path selected A/NFTL partition 10 rather than firmware/calibration or SD recording storage, but shared lower-level error/metadata effects were not exhaustively proven absent. The formatter assumes working initialized geometry; this is not a verified repair for broken FTL initialization or unreadable NAND.

## 4. Stock startup, pairing and cold-boot validation

After the successful attempt and a normal shutdown, cold boot once with **NBFA02 retained**. Require `NBFA02_SKIP`, no BEGIN/second format, and stock Bluetooth startup. No temporary RAM-recovery hook may be active. Pair through **Connected App → Setup phone** and confirm actual app camera/recordings access. A vendor success line or `BT_BOOTED` alone is not this functional check.

Use the reader to preserve/hash-check and remove the format hook and retained token, keeping NBFA01/NBFA02. Stage the persistence-capture phase with fresh `bt-persistence-capture.claimed` absent. Its 20-second read collection and five-second sync only record mounts/process context and up to 1 MiB each from the four named stock configuration files; optional missing files are explicit. It does not mount RAM, restart services, pair a phone or write A.

Perform a **full power-off/cold boot** and connect the existing app camera **without Setup phone or pairing again**. Retrieve the observer results with the reader and verify hashes/statuses. Require successful collection/sync, `/tmp/FL0` backed by `a:` AmbaFS in actual mountinfo with no RAM bind overlay, readable stock configuration/pairing XML, and actual existing-app reconnection. Inspect `/pref` separately; do not infer its backing filesystem merely because `/tmp` is tmpfs. Missing optional `si_devices.xml` or `bt.conf` is recorded, not fabricated. If files or app behavior disagree, stop and investigate rather than reformat.

Before a final **ordinary cold boot**, remove only the verified owned active `autoexec.ash`, `usb.console` if still present, and staged helper/script files. Check that no diagnostic startup hook or alternate console token remains. Preserve results and the NBFA claims, especially NBFA02. With no active hooks/tokens, fully power off and boot normally, then confirm the existing app again shows the camera/recordings without re-pairing. This is the second post-pairing cold-boot check and excludes a diagnostic hook as the reason for reconnection.

On the examined unit, both the observer cold boot and this final hook-free ordinary boot reconnected successfully. That is the demonstrated persistence boundary; repeated weeks of use, all phones/profiles/radio ranges and long-term NAND retention remain untested. Keep backups and claims. Do not repeat the format to expand the test count.

## What to keep private

Retain all manifests, copy/error statuses, passive console logs, configuration and NAND captures privately. They may contain camera/phone identifiers, pairing keys and personal settings. Publish only sanitized model/firmware, tool version and status descriptions. The distributed assets contain no populated XML, captured NAND, recordings or vendor firmware image.
