# Nextbase 622GW Bluetooth recovery

**Bluetooth recovery for a Nextbase 622GW running R13.3 that cannot create its Bluetooth configuration.** The normal Mac/Windows launcher prepares a temporary RAM workaround. A separate [advanced manual procedure](docs/internal-storage-repair.md) documents the destructive internal Drive A repair tested on one affected camera.

Current release: **0.2.0**, archive `Nextbase622GW-recovery-0.2.0.zip`. Extract the entire matching release and verify its supplied checksums. The [temporary kit](recovery-kit/) and [advanced assets](advanced/internal-drive-a/) have separate manifests. No advanced operation is selected by either double-click launcher.

**The default temporary recovery lasts until the camera loses power or reboots.** It uses RAM for configuration; it does not repair internal storage. Pairing information created during that session can be lost at reboot. For another session, re-arm the card with the tool below.

The original RAM recovery script worked on the camera. These installers add compatibility checks and safer cleanup around that operation; **the guarded temporary package has not yet been boot-tested on a camera**. Separately, the vendor Drive A format restored stock configuration and app reconnection across full power-offs on that one unit, including an ordinary boot after all active hooks/tokens were removed. See [validation and technical notes](docs/technical-notes.md#validation).

The advanced procedure **erases Drive A files/settings**. It requires verified backups, a healthy SD filesystem, a working card reader, passive console evidence, and a successful two-boot harmless guard rehearsal. A zero Bluetooth MAC alone is insufficient reason to format. Read the complete [internal-storage repair guide](docs/internal-storage-repair.md) before copying any advanced file.

## Is this the right recovery?

The affected camera had all of these symptoms:

- Firmware **R13.3**, model **622GW**.
- No phone could find/connect to it during **Connected App → Setup phone**.
- Camera information showed Bluetooth MAC `00:00:00:00:00:00` and a fallback Bluetooth name ending in `000`.
- Internal logs showed Bluetooth configuration creation failing for `/tmp/FL0/bt_config.xml`.

The installer checks the model and firmware. The camera script also checks the known executable versions, the specific configuration error, and the running Bluetooth service before changing anything. A zero MAC alone does not establish this fault. Other models, firmware versions and Bluetooth faults are outside the tested scope.

## Recover Bluetooth

You need a Mac or Windows PC, the camera's microSD card, and preferably a card reader. Keep the camera on steady power during recovery. Save any recordings you need first.

1. **Download and extract the whole kit** onto your computer. For a GitHub source download, choose **Code → Download ZIP**, then extract it. Keep `recovery-kit`, `payload` and their files together; do not run from inside a ZIP.
2. **Stop recording, power off the camera, and put its microSD card in the reader.** Alternatively connect a USB data cable to the camera body's mini-USB port and choose **Firmware Update** to expose a writable card. The mount's USB port supplies power only. Do not add firmware files.
3. Open the extracted **`recovery-kit`** folder and run:

   | Computer | File to open |
   |---|---|
   | macOS | **Recover Bluetooth.command** |
   | Windows | **Recover Bluetooth.cmd** |

   The tool finds a compatible card, verifies the files, then copies the startup hook and recovery script. It refuses conflicting startup files or firmware update binaries. If it reports an error, follow that message; it has not granted permission to overwrite anything. No administrator access, Python, firmware download or permanent PowerShell policy change is required.
4. **Safely eject the card/drive.** If using a reader, return the card to the powered-off camera. If using the camera over USB, power it off and unplug it. Reconnect the camera to the computer through its body USB data port and turn it on, then **wait one minute**. The USB diagnostic trigger may skip the usual PC Connection menu on this boot. This is the connection used for the demonstrated recovery.
5. **Stop recording**, then choose **cog → Connected App → Setup phone → OK**. Open the Nextbase app and complete pairing. Confirm the app can show the camera or recordings. That is the success check.

Leave the camera powered for this session. An `ATTEMPT_COMPLETE` file only means the script finished its attempt; it does not prove pairing worked.

## After the session: remove or re-arm

After stopping recording, power off the camera and put its card in a reader again. The successful run normally moves its own USB trigger into its result folder, so a subsequent cold boot should offer the normal USB menu again. If it does not, use a card reader.

Open Terminal/PowerShell in the extracted kit folder and run the appropriate command. Substitute the actual card path or drive letter.

| Action | macOS | Windows PowerShell |
|---|---|---|
| Check card | `bash recovery-kit/prepare-macos.sh status /Volumes/NEXTBASE` | `powershell -NoProfile -ExecutionPolicy Bypass -File .\recovery-kit\prepare-windows.ps1 -Action Status -Volume E:\` |
| Remove startup files | `bash recovery-kit/prepare-macos.sh remove /Volumes/NEXTBASE` | `powershell -NoProfile -ExecutionPolicy Bypass -File .\recovery-kit\prepare-windows.ps1 -Action Remove -Volume E:\` |
| Prepare another session | `bash recovery-kit/prepare-macos.sh prepare /Volumes/NEXTBASE` | `powershell -NoProfile -ExecutionPolicy Bypass -File .\recovery-kit\prepare-windows.ps1 -Action Prepare -Volume E:\` |

For another recovery session, run **remove**, then **prepare**, safely eject, and repeat steps 4–5. You can omit the path if exactly one compatible card is connected. Remove keeps recordings and `nb-bt-recovery-*` result folders. It refuses to delete modified or unowned files.

To upgrade a card prepared with an older kit, remove it using that matching version's tool before preparing with 0.2.0. Ownership markers include the kit version; a different version is refused rather than overwritten. The temporary installer does not prepare or remove the advanced repair procedure.

If removing by hand, only remove the files this kit created: root `autoexec.ash`, `nb-bt-recover.sh`, `usb.console` if still present, `nb-bt-recovery-kit.txt`, and the directory `nb-bt-recovery.claimed`. Do not delete someone else's existing startup files. Safely eject afterward. Rebooting discards the RAM overlay.

## What was wrong, and what changes?

The vendor Bluetooth application successfully reached its Bluetooth service, then failed to create its default XML configuration on internal drive A, exposed to Linux as `/tmp/FL0`. It closed the service connection and aborted initialization. Later driver-returned main/OOB captures supported partial filesystem metadata and missing directory/data contents, and vendor reformatting restored stock operation. The original cause, translation-layer contribution and long-term hardware health remain unresolved.

We temporarily placed a fresh RAM directory over `/tmp/FL0` and restarted the vendor Amazon Bluetooth application. The application generated its own configuration, reported the real Bluetooth address, became discoverable and connected to the phone/app. No custom Bluetooth XML was needed.

The overlay covers the **whole Linux `/tmp/FL0` path**, so other Linux processes opening that path also see RAM for the session. The script copies any readable existing Bluetooth XML into RAM and saves private diagnostic copies on the card. It leaves the BSA service, radio firmware, UART and GPIO running. This default recovery does not flash firmware or intentionally write/format the underlying internal drive.

Further investigation preserved the driver-returned Drive A main/OOB data and found incomplete filesystem metadata. A separately reviewed, one-shot vendor `format a:` operation then allowed stock startup to recreate configuration. Existing app pairing reconnected after cold boots, including with no active diagnostic files. That result does not establish the original cause, long-term NAND health, an ECC-free physical backup or a tested restore route. The [advanced guide](docs/internal-storage-repair.md) includes those limits and the required checks.

## Troubleshooting

- **No card found:** use a reader, or the camera body's data port with **Firmware Update** selected. **Access Files** was read-only on the tested camera. Reseat a reader/card if it appears without a disk. If several compatible cards are mounted, pass the exact path as above.
- **Unsupported model/firmware:** stop. Do not edit out the check or install firmware solely to try this kit. Only the listed R13.3 build was investigated.
- **Existing hooks or firmware files:** inspect them first. This kit will not replace another `autoexec.ash`, debug trigger, previous investigation script or firmware update file. A previously armed copy of this kit should be removed with its removal command before preparation.
- **macOS will not open the launcher:** open Terminal in the extracted repository folder and run `bash recovery-kit/prepare-macos.sh prepare`. The command does the same preparation.
- **The next boot still has no Bluetooth:** wait the full minute, enter Setup phone and check the app. After powering off, use a reader to inspect `RESULT.txt` in the newest `nb-bt-recovery-N` directory. If no result directory was created, the startup hook did not run or preflight refused before any card writes. A console acknowledgement only confirms script entry; refusal diagnostics go to stderr. Refusal can also happen if the bounded console buffer no longer contains the known failure. Do not bypass the checks. The issue may differ from the one recovered here; repeated reboots do not prove otherwise.
- **The camera behaves unexpectedly:** power it off, remove this kit's startup files via a reader, safely eject, then boot normally. A reboot removes the temporary RAM configuration.

**Keep diagnostic folders private.** Logs and XML can contain Bluetooth addresses, paired-device identifiers and pairing keys. Do not attach them unredacted to a public GitHub issue. Useful public reports include model, firmware, host OS, installer error and the sanitized result status.

## Files and development

- [Agent execution instructions](CLAUDE.md) — the supported fix has already been researched; assistants should execute and verify the documented procedure rather than repeat reverse engineering.
- [`recovery-kit/`](recovery-kit/) — native launchers, preparation/removal tools, three camera payload files, SHA256 manifest.
- [Technical notes](docs/technical-notes.md) — diagnosis, exact operation, evidence limits and compatibility hashes.
- [Advanced internal-storage repair](docs/internal-storage-repair.md) — manual backup, harmless rehearsal, one explicit destructive operation and cold-boot validation; [inactive assets](advanced/internal-drive-a/).
- [Passive console reader](tools/capture_rtos.py) — Python 3/macOS-POSIX receive-only logging for the advanced procedure; native Windows capture is not validated.
- [`tests/`](tests/) — temporary-card and payload behavior tests; [`tools/build_release.py`](tools/build_release.py) creates an allowlisted release ZIP.

Run `python3 -m unittest discover -s tests -p 'test_*.py'`, and on Windows run `powershell -NoProfile -ExecutionPolicy Bypass -File tests/test_windows_installer.ps1`. Build a public ZIP with `python3 tools/build_release.py`; private investigation files are excluded by an explicit allowlist. See the CI workflow for platform checks.

Independent, community recovery tooling; not an official Nextbase release. Original code is provided under the [MIT license](LICENSE). Vendor firmware, vendor executables and populated pairing configuration are not distributed; the included advanced ARM reader is built from this project's source.
