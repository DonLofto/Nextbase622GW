# Diagnosis and recovery details

## Observed failure

One Nextbase 622GW running R13.3 showed a zero Bluetooth MAC, a fallback name ending in `000`, and no usable pairing from either of the owner's phones. Defaults/reset and an official firmware update had not restored Bluetooth. USB storage access worked on R13.3.

Early Linux snapshots showed `bsa_server` and the vendor Amazon application running, the Bluetooth UART owned by BSA, and a controller patch present. Those facts alone did not prove initialization or justify declaring a dead radio.

Later console captures, at approximately 75 and 90 seconds uptime, showed the decisive sequence:

1. Amazon connected to BSA and requested the controller configuration.
2. Reading `/tmp/FL0/bt_config.xml` failed; Amazon attempted normal default creation.
3. Opening the default XML for writing failed, producing an `Unable to Create` error.
4. BSA management closed and Amazon manager initialization aborted.

Static inspection of the shipped executable agreed with that sequence: absence of XML is normally recoverable; failure to create its defaults is fatal to this initialization path. Writing a guessed `config.xml` would not address the demonstrated failure.

`/tmp/FL0` was an `ambafs` mount backed by RTOS drive `a:`. It listed no files. The vendor `S51pref` script uses a writable marker on that drive; its fallback put `/pref` on tmpfs. Together these supported an inaccessible/unwritable internal configuration path. A mount labelled `rw` is not proof a file can actually be created. Later vendor reformatting restored stock operation, but did not establish why the prior filesystem state was lost or distinguish wear, an interrupted operation, translation state and other causes.

## Demonstrated recovery

The original direct test waited 20 seconds after startup, used the RTOS `t app linux_cmd` hook to run a shell script, copied any readable Bluetooth XML, and bind-mounted a fresh RAM directory over `/tmp/FL0`. It stopped the old Amazon process, restarted `/tmp/amazon`, and kept the existing BSA service running.

With writable RAM visible at the expected path, the vendor application generated its own configuration. RTOS reported the real Bluetooth MAC and `AMSG_EVENT_BT_BOOTED`. A Mac Classic inquiry found the matching camera, then logs showed phone RFCOMM/iAP activity. The owner confirmed the Nextbase app connected and could show the camera or recordings.

The original test used `bt-start-test.sh`. Its SHA256 was:

```text
b0e2afbedd470d4d87eeb47c813e3f5cb48d9b956e6ef5de63757be370db31a0
```

Raw captures and populated configuration remain private because they identify the camera and paired devices. They are not required to run this kit.

## Packaged operation

Version 0.2.0 keeps the temporary recovery as the normal double-click operation and adds a separate [advanced manual Drive A repair](internal-storage-repair.md). The temporary payload remains guarded and reboot-dependent; adding advanced assets does not make it an automatic repair installer.

The host tool validates `Model: 622GW` and `Firmware: R13.3` in `Nextbase.info`, checks the kit manifest, refuses conflicting hooks/update files, and stages verified payloads. It creates an ownership marker for safe cleanup. Recordings and unknown files are preserved.

The camera's root `autoexec.ash` sleeps **20000 milliseconds** and runs `/bin/sh /tmp/SD0/nb-bt-recover.sh`. RTOS output redirection is deliberately absent. The exact USB debug token is 32 ASCII bytes with no newline; its SHA256 is:

```text
2b19515c1ee1515adc54d58c62cac67679ad3493185cddfe92e5872a5a8527f3
```

This enables the USB console boot route used for the demonstrated start attempt. It is not an interactive repair console: input did not work in the tested single/dual console modes. The SD startup hook is what runs the recovery.

The script first emits one short newline-terminated acknowledgement to stdout, then returns immediately if its owned one-shot claim exists. Before its first card write it verifies the kit marker, installed files, exact USB token, runtime identities, known binary hashes, configuration failure and existing BSA. It then records ownership, captures private diagnostics and attempts the RAM overlay and exact-executable Amazon restart. It moves only its matching USB token into the result folder to avoid forcing the next cold boot into debug mode. No every-boot SD-backed configuration workaround is installed.

The acknowledgement introduced in 0.1.1 avoids an empty-output defect found in static inspection of the vendor `util_svc` RPC service: its first `fgets` return is unchecked, after which it copies an uninitialized stack buffer when a command produces no stdout. Quiet 0.1.0 no-op/refusal/attempt paths could reach that defect; no actual crash or hang from it was demonstrated. The payload writes a single bounded entry line before guards or diagnostic redirection. That response confirms entry only, not an attempt result or pairing success. Detailed output remains in private result files or on stderr; RPC stdout stays below the RTOS 511-byte display limit.

Results go to a new `nb-bt-recovery-N` directory on the card. Check `RESULT.txt`; `ATTEMPT_COMPLETE` records an attempted startup only. Discoverability and actual app access still need human verification.

Preflight refusals perform no card writes and therefore do not create a result directory or claim. Their diagnostic messages go to stderr; the RPC service captures stdout, so the entry acknowledgement alone does not expose the refusal reason. The console signature is deliberately conservative and can refuse if the relevant message has scrolled out of the bounded VCS buffer. An absent/changed debug token also causes a read-only refusal. The token is required to reproduce the demonstrated diagnostic boot route; file presence is not a general query of the current RTOS USB mode.

The RAM bind changes new Linux lookups for the entire `/tmp/FL0` path. Existing open descriptors can retain the old view; this is not an isolated per-process overlay. Reboot discards the overlay and new configuration. Pairing persistence for this RAM path is unproven, and pairing keys generated in RAM can be lost. The one-shot claim prevents rerunning the script on subsequent boots, including when exporting the card to a host. Re-arm deliberately through remove then prepare.

The temporary path performs no BSA clean-start, controller firmware replacement, UART read/baud change, GPIO reset, raw flash repair, formatting or firmware flashing. The advanced manual path below is a separate destructive operation with different prerequisites and files.

## Internal Drive A repair and cold-boot result

Pre-format read-only acquisition completed the selected DRIVE_A partition: 12,058,624 corrected-main bytes, the same number of requested-RAW main bytes, 753,664 requested-RAW OOB bytes, and 92 bad-block-query records. Status coverage, lengths and hashes were independently verified. The helper ran from a verified RAM copy and opened only the fixed read-only MTD node. This was partition acquisition, not a whole-chip or restorable backup. ECC activity during requested RAW acquisition leaves uncorrected physical fidelity unproven; active FTL mapping, translation data elsewhere and a working restore method were not established.

Only three main-area pages contained non-erased-looking data. They preserved MBR/BPB and partial FAT metadata; the expected directory/data and most FAT bytes read erased-looking. A direct FAT interpretation reproduced the misleading used/free count, but no named user file was recovered and no validated logical-volume reconstruction followed from that interpretation. Zero reported bad blocks and corrected reads did not certify future write/erase health.

Before a destructive attempt, the SD card's allocation-bitmap fault was corrected after verified file preservation, then a separate read-only filesystem check passed and preserved files were rehashed. The native one-shot claim was rehearsed over two cold boots: `NBFA01_DRYRUN`, then `NBFA01_SKIP`, followed by direct verification of the retained empty claim directory.

The exact separately reviewed format hook created the distinct `NBFA02.claimed` directory and called the vendor `format a:` once. The vendor returned `Drive 'A' format done.`. The next stock cold boot reported Bluetooth startup and `NBFA02_SKIP`, with no RAM recovery. The user paired through the app and confirmed camera/recordings access. On a later full power-off/cold boot, the read-only observer captured `/tmp/FL0` and `/pref` backed by `a:` AmbaFS, existing adapter and paired-device XML, and no RAM overlay; the existing app reconnected without Setup Phone or re-pairing. After all active hooks, scripts and console tokens were removed, a further ordinary cold boot again reconnected the existing app camera/recordings without pairing. This is evidence of retained pairing on one repaired unit across those cycles, not long-term reliability qualification.

Static inspection traces the normal formatter to A's logical sectors through NFTL partition 10. Its explicit callbacks do not select SD recordings, firmware or calibration. It replaces A filesystem metadata and can erase/program blocks through the FTL. Existing A files, hidden files, preferences, Wi-Fi/Bluetooth configuration and pairing state are not preserved by the operation. Shared low-level metadata/error paths and corrupted runtime state were not exhaustively bounded.

The formatter expects initialized working FTL geometry; it is not a demonstrated FTL rebuild or a remedy for unreadable geometry. It has no proven finite completion deadline or power-loss atomicity. Its 20-second delay does not quiesce Amazon/BSA or other application clients; the tested boot had ordinary firmware activity, and complete application isolation was not demonstrated. A successful return alone establishes neither durability nor pairing; the later cold boots and app tests supplied those postconditions. The [manual guide](internal-storage-repair.md) retains these limits and requires stopping after failure or missing evidence.

## Compatibility identities

Only the examined R13.3 build is accepted by the device preflight:

| File on camera | SHA256 |
|---|---|
| `/usr/bin/amazon_app` | `ea1ad4c2969abffee176364eef67e5df24b37598de18862ab5866eb86b64b054` |
| `/usr/bin/bsa_server` | `3fab6b79dc0becd8b4dd5f9c710989463661d6905f2e2e265d5a5377dea20747` |
| `/usr/local/bcmdhd/bt.hcd` | `093bd3c261df7809ab30c77ca2d8d7870f5db66622d86d6125a17fd7295f6e55` |

For provenance, the inspected firmware package `FW622GWA.bin` had SHA256 `d70a3e99380c7c4ad153ce86d428c1be6175fb25b830cfd231ec5c1290b4a1a3`. No firmware package is included or needed by the kit; that identity is not a recommendation to install it.

## Validation

| Area | Status |
|---|---|
| Original RAM bind + Amazon restart | Succeeded on one physical 622GW / R13.3 |
| Classic Bluetooth discovery | Independently observed on a Mac |
| iPhone / Nextbase app | Owner confirmed connection and camera/recordings visible |
| Packaged preflight and host tools | Newly implemented; automated fixture tests and independent review recorded in the repository |
| Packaged kit end to end on camera | Not yet boot-tested |
| Advanced vendor A format and stock startup | One separately approved invocation succeeded on the examined unit |
| Existing pairing after cold boots | User-confirmed app reconnection; stock AmbaFS/XML evidence, then hook-free ordinary-boot reconnection |
| Temporary RAM recovery surviving reboot | No; overlay is discarded |
| Android app, BLE advertising, other units/firmware | Not validated |
| Root cause, long-term NAND health and restore route | Unresolved / not validated |

Automated payload tests exercise controlled shell environments, not the physical radio or RTOS. Host tests use synthetic card directories and do not establish USB/controller compatibility. PowerShell runtime and Windows-specific test coverage are described by the CI workflow and actual run results; passing a portable PowerShell run is not a Windows hardware test.

Local **0.2.0** validation on 2026-10-25 passed **47 Python tests** on macOS: 16 native Bash 3.2 installer cases, 19 payload harness cases, four release cases, five advanced-asset cases and three passive-reader PTY cases. **37 Windows-installer fixture cases** passed under portable PowerShell 7.6.8 on macOS arm64. Shell syntax, payload/advanced manifests and source byte/hash checks passed. The payload harness covers attempts, refusals, owned no-ops and aborts with bounded nonempty RPC stdout; the reader tests exercise capture/no-transmit behavior through a pseudo-terminal. Independent source reviews covered host tools, payload, advanced assets, documentation and release generation. Native Windows PowerShell 5.1, Finder/CMD double-click UI and the guarded temporary package's camera boot remain untested. Advanced helper/backup/persistence operations were separately executed on the examined camera, with the limits above; that does not turn portable PowerShell or PTY tests into Windows/camera hardware tests. The GitHub workflow is included but has not been run remotely for this repository.

## Privacy and distribution

The public release builder uses an explicit allowlist for documentation, license, host tools, generic temporary payloads, tests and the inactive advanced assets. The advanced helper is project source and its reproducibly built ARM executable; vendor firmware/binaries and captured NAND/configuration data are not distributed. Separate manifests cover temporary payloads and advanced files. Original device information, logs, XML, pairing keys, recordings and private handoff notes remain excluded. Keep capture/result folders private rather than attaching them unredacted to public issues.
